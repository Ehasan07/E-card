"""Daily tick that runs the card-lifecycle state machine.

Set to run once a day (systemd timer or plain cron). Idempotent — safe to
run multiple times per day. Each state change is recorded on the card
itself and a `CardLifecycleLog` row is created; the owner also gets a
`UserNotification`.

Cadence:
- 30 days before trial/paid expiry → warning inbox message
-  7 days before                    → second warning
-  1 day  before                    → final warning
- On expiry date                    → deactivate + log + inbox
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from cards.models import Card, CardLifecycleLog, UserNotification


WARNING_STAGES = [
    # (days_before_expiry, stage_number, log_action_key, inbox_kind_key)
    (30, 1, 'warning_30d', 'renewal_warning'),
    (7,  2, 'warning_7d',  'renewal_warning'),
    (1,  3, 'warning_1d',  'renewal_warning'),
]


class Command(BaseCommand):
    help = "Advance the card-lifecycle state machine (warnings + auto-deactivation)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would happen without persisting anything.',
        )
        parser.add_argument(
            '--now', type=str, default=None,
            help='Override the current time (ISO 8601). Useful in tests / backfills.',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        if options['now']:
            now = timezone.datetime.fromisoformat(options['now'])
            if timezone.is_naive(now):
                now = timezone.make_aware(now)

        dry = options['dry_run']
        stats = {'warnings': 0, 'expired': 0, 'skipped': 0}

        active_cards = (
            Card.objects
            .select_related('user', 'user__profile')
            .filter(lifecycle_status__in=[Card.STATUS_TRIAL, Card.STATUS_ACTIVE_PAID, Card.STATUS_EXPIRING_SOON])
        )

        for card in active_cards:
            effective_expiry = _effective_expiry(card)
            if effective_expiry is None:
                stats['skipped'] += 1
                continue

            # --- Expiry ---
            if effective_expiry <= now:
                if not dry:
                    _deactivate(card, now)
                stats['expired'] += 1
                continue

            # --- Warnings ---
            days_left = (effective_expiry - now).days
            for days_before, stage, action_key, kind_key in WARNING_STAGES:
                if days_left <= days_before and card.last_warning_stage < stage:
                    if not dry:
                        _send_warning(card, stage, days_before, action_key, kind_key)
                    stats['warnings'] += 1
                    break  # send at most one stage per tick

        self.stdout.write(self.style.SUCCESS(
            f"tick done · warnings={stats['warnings']} "
            f"expired={stats['expired']} skipped={stats['skipped']} "
            f"{'(dry-run)' if dry else ''}"
        ))


def _effective_expiry(card):
    """The date this card actually goes offline.

    Priority order:
      1. If the owner has an active yearly subscription (Profile.subscription_paid_until)
         that's later than trial_ends_at, use that (one-payment-covers-all).
      2. Otherwise the card's trial_ends_at.
    """
    profile = getattr(card.user, 'profile', None)
    sub_until = getattr(profile, 'subscription_paid_until', None) if profile else None
    trial_end = card.trial_ends_at

    if sub_until and trial_end:
        return max(sub_until, trial_end)
    return sub_until or trial_end


def _send_warning(card, stage, days_before, action_key, kind_key):
    from django.urls import reverse

    action_map = {
        'warning_30d': CardLifecycleLog.ACTION_WARNING_30D,
        'warning_7d':  CardLifecycleLog.ACTION_WARNING_7D,
        'warning_1d':  CardLifecycleLog.ACTION_WARNING_1D,
    }

    CardLifecycleLog.objects.create(
        card=card,
        action=action_map[action_key],
        actor=CardLifecycleLog.ACTOR_SYSTEM,
        notes=f"{days_before}-day warning delivered.",
    )

    subject = f"Your card '{card.slug}' expires in {days_before} day{'s' if days_before != 1 else ''}"
    body = (
        f"Your public card https://mycard.dupno.com/card/{card.slug} will go offline "
        f"in {days_before} day{'s' if days_before != 1 else ''}. Renew now to keep it live — "
        f"see the reactivation page for pricing and payment options."
    )
    action_url = reverse('reactivate_card', args=[card.slug])

    UserNotification.objects.create(
        user=card.user,
        card=card,
        kind=UserNotification.KIND_RENEWAL_WARNING,
        subject=subject,
        body=body,
        action_url=action_url,
    )

    Card.objects.filter(pk=card.pk).update(
        last_warning_stage=stage,
        lifecycle_status=Card.STATUS_EXPIRING_SOON,
    )


def _deactivate(card, now):
    from django.urls import reverse

    reason = (
        'trial_ended'
        if card.lifecycle_status == Card.STATUS_TRIAL
        else 'subscription_lapsed'
    )

    Card.objects.filter(pk=card.pk).update(
        is_active=False,
        lifecycle_status=Card.STATUS_EXPIRED,
        deactivated_at=now,
        deactivation_reason=reason,
    )

    CardLifecycleLog.objects.create(
        card=card,
        action=(
            CardLifecycleLog.ACTION_TRIAL_ENDED
            if reason == 'trial_ended'
            else CardLifecycleLog.ACTION_DEACTIVATED
        ),
        actor=CardLifecycleLog.ACTOR_SYSTEM,
        notes=f"Auto-deactivated by cron. Reason: {reason}.",
    )

    subject = f"Your card '{card.slug}' is now offline"
    body = (
        f"Your public card https://mycard.dupno.com/card/{card.slug} has been taken offline "
        f"because the trial or paid period ended. Reactivate any time — see your dashboard "
        f"for pricing and payment options."
    )
    UserNotification.objects.create(
        user=card.user,
        card=card,
        kind=UserNotification.KIND_CARD_OFFLINE,
        subject=subject,
        body=body,
        action_url=reverse('reactivate_card', args=[card.slug]),
    )
