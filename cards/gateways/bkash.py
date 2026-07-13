"""bKash Recurring Payment (RPP) gateway client.

Docs: bKash Recurring Payment Integration Guide v2.1.2.
Sandbox base URL: https://gateway.sbrecurring.pay.bka.sh
Live base URL:    provisioned by bKash after UAT go-live.

Design notes:
* Every method returns a plain dict (parsed JSON body). Errors are raised
  as ``BkashError`` with the HTTP status + bKash error code so callers
  can log / branch.
* HTTP timeout is 30s per bKash's requirement (Note-1 of the doc).
* Webhook signature verification is a top-level ``verify_signature``
  helper (not a class method) because the incoming signature is decoded
  before we know which Payment row it maps to.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import uuid
from datetime import date, timedelta
from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

BKASH_API_TIMEOUT_SECONDS = 30


class BkashError(Exception):
    """Raised for any non-2xx response from bKash or a transport failure."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.body = body


class BkashClient:
    """Thin, synchronous wrapper around the bKash RPP v1 endpoints we use."""

    def __init__(self):
        self.base_url = settings.BKASH_BASE_URL.rstrip('/')
        self.app_key = settings.BKASH_APP_KEY
        self.merchant_short_code = settings.BKASH_MERCHANT_SHORT_CODE
        self.service_id = settings.BKASH_SERVICE_ID
        self.redirect_url = settings.BKASH_REDIRECT_URL

    # ---------- HTTP helpers ----------

    def _headers(self, *, channel: str = 'Merchant WEB') -> dict[str, str]:
        return {
            'version': 'v1.0',
            'channelId': channel,
            'timeStamp': timezone.now().isoformat().replace('+00:00', 'Z'),
            'x-api-key': self.app_key,
            'Content-Type': 'application/json',
        }

    def _request(self, method: str, path: str, *, json_body: dict | None = None) -> dict:
        url = f'{self.base_url}{path}'
        try:
            resp = requests.request(
                method,
                url,
                headers=self._headers(),
                json=json_body,
                timeout=BKASH_API_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise BkashError(f'bKash transport error: {exc}') from exc

        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {'raw': resp.text}

        if not resp.ok:
            raise BkashError(
                f'bKash {resp.status_code} at {path}: {body}',
                status=resp.status_code,
                code=(body.get('errorCode') if isinstance(body, dict) else None),
                body=body,
            )
        return body

    # ---------- Subscription lifecycle ----------

    def create_subscription(
        self,
        *,
        subscription_request_id: str,
        amount: float,
        start_date: date,
        expiry_date: date,
        frequency: str = 'CALENDAR_YEAR',
        subscription_type: str = 'WITH_PAYMENT',
        first_payment_amount: float | None = None,
        payer_msisdn: str = '',
        subscription_reference: str = '',
    ) -> dict:
        """Kick off a subscription. Response includes a redirectURL the
        customer must be sent to for wallet + OTP + PIN + consent."""

        body: dict[str, Any] = {
            'subscriptionRequestId': subscription_request_id,
            'serviceId': int(self.service_id),
            'redirectUrl': self.redirect_url,
            'paymentType': 'FIXED',
            'subscriptionType': subscription_type,
            'amount': amount,
            'currency': 'BDT',
            'frequency': frequency,
            'startDate': start_date.isoformat(),
            'expiryDate': expiry_date.isoformat(),
            'payerType': 'CUSTOMER',
            'payer': payer_msisdn or None,
            'subscriptionReference': subscription_reference[:80] or subscription_request_id[:80],
            'firstPaymentIncludedInCycle': True,
            'maxCapRequired': False,
        }
        if subscription_type == 'WITH_PAYMENT' and first_payment_amount is not None:
            body['firstPaymentAmount'] = first_payment_amount
        if self.merchant_short_code:
            body['merchantShortCode'] = self.merchant_short_code

        return self._request('POST', '/gateway/api/subscription', json_body=body)

    def query_by_request_id(self, subscription_request_id: str) -> dict:
        return self._request('GET', f'/gateway/api/subscriptions/request-id/{subscription_request_id}')

    def query_by_subscription_id(self, subscription_id: str) -> dict:
        return self._request('GET', f'/gateway/api/subscriptions/{subscription_id}')

    def payments_by_subscription_id(self, subscription_id: str) -> list[dict]:
        result = self._request('GET', f'/gateway/api/subscription/payment/bySubscriptionId/{subscription_id}')
        return result if isinstance(result, list) else result.get('content', [])

    def payment_by_id(self, payment_id: str) -> dict:
        return self._request('GET', f'/gateway/api/subscription/payment/{payment_id}')

    def cancel_subscription(self, subscription_id: str, *, reason: str = 'user_requested') -> dict:
        return self._request(
            'DELETE',
            f'/gateway/api/subscriptions/{subscription_id}?reason={reason}',
        )

    def refund_payment(self, payment_id: str, amount: float) -> dict:
        return self._request(
            'POST',
            '/gateway/api/subscription/payment/refund',
            json_body={'paymentId': int(payment_id), 'amount': amount},
        )


# ---------- Webhook signature verification ----------

def verify_signature(*, payload: bytes, signature_header: str, api_key: str | None = None) -> bool:
    """Verify a bKash webhook payload against its ``X-Signature`` header.

    Follows the algorithm in the integration guide:
      1. Base64-URL decode the signature header.
      2. Base64-URL decode the api_key (webhook signing key).
      3. HMAC-SHA256(payload, key=decoded_api_key).
      4. Constant-time compare digest with signature.
    """
    key = api_key or settings.BKASH_WEBHOOK_KEY
    if not key or not signature_header:
        return False
    try:
        signature = base64.urlsafe_b64decode(_pad_b64(signature_header))
        secret = base64.urlsafe_b64decode(_pad_b64(key))
    except (ValueError, TypeError):
        logger.warning("bKash webhook signature decode failed")
        return False
    digest = hmac.new(secret, payload, hashlib.sha256).digest()
    return hmac.compare_digest(digest, signature)


def _pad_b64(value: str) -> str:
    """Base64URL sometimes ships without ``=`` padding. Add it back."""
    return value + '=' * (-len(value) % 4)


# ---------- Convenience helpers ----------

def new_subscription_request_id(prefix: str = 'MYC') -> str:
    """Unique idempotency ID for one subscription request."""
    return f'{prefix}-{uuid.uuid4().hex[:16]}-{int(timezone.now().timestamp())}'


def suggested_expiry_date(*, start: date | None = None, years: int = 2) -> date:
    """bKash's max subscription lifetime is 2 years from start."""
    start = start or timezone.now().date()
    return start + timedelta(days=365 * years)
