import csv
import json
import logging
import re
import zipfile
import random
from decimal import Decimal
from functools import lru_cache
from io import BytesIO, StringIO

logger = logging.getLogger(__name__)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import Http404
from .forms import (
    UserForm,
    ProfileForm,
    ForgotPasswordForm,
    CardForm,
    BUSINESS_HIGHLIGHT_CHOICES,
    BusinessCardForm,
    COUNTRY_CHOICES,
    AdminCardLimitForm,
    FeedbackForm,
)
from .permissions import (
    is_premium,
    premium_required,
    themes_for_user,
    user_plan_tier,
)
from .models import (
    CardLifecycleLog,
    UserNotification,
    Payment,
    Card,
    Profile,
    DEFAULT_CARD_LIMIT,
    UpgradeRequest,
    SubscriptionPlan,
    Subscription,
    Feedback,
    CardChangeLog,
    CardInteraction,
    LeadCapture,
    CardTheme,
    Payment,
)
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse
import markdown
import os
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from datetime import timedelta

from openpyxl import Workbook


OTP_EXPIRY_MINUTES = 5
OTP_RATE_LIMIT_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
OTP_EMAIL_FROM = 'dss@dupno.com'


CARD_FORM_BY_TYPE = {
    Card.TYPE_PERSONAL: CardForm,
    Card.TYPE_BUSINESS: BusinessCardForm,
}


CARD_VARIANT_CONFIG = {
    Card.TYPE_PERSONAL: {
        'slug': Card.TYPE_PERSONAL,
        'page_title': 'Personal MY-Card',
        'badge': 'Builder mode',
        'heading': 'Craft your interactive identity',
        'subheading': 'Fill out the details on the left and tailor every section of your card.',
        'submit_label': 'Save card',
        'success_message': 'Card published! Share your new link right away.',
        'cta_label': 'Create personal card',
        'empty_cta': 'Start personal card',
    },
    Card.TYPE_BUSINESS: {
        'slug': Card.TYPE_BUSINESS,
        'page_title': 'Business MY-Card',
        'badge': 'Business builder',
        'heading': 'Launch your business presence',
        'subheading': 'Keep your brand details and callouts aligned for clients and partners.',
        'submit_label': 'Save business card',
        'success_message': 'Business card is live! Share it with your network.',
        'cta_label': 'Create business card',
        'empty_cta': 'Start business card',
    },
}


def _build_card_field_labels():
    excluded = {'avatar', 'logo', 'whatsapp_country', 'whatsapp_number', 'phone_country', 'phone_number'}
    labels: dict[str, str] = {}
    for form_cls in (CardForm, BusinessCardForm):
        for name, field in form_cls.base_fields.items():
            if name in excluded:
                continue
            label = field.label or name.replace('_', ' ').title()
            labels[name] = label

    # Manual overrides for fields that have special casing or hidden widgets
    overrides = {
        'firstName': 'First name',
        'lastName': 'Last name',
        'jobTitle': 'Job title',
        'logo_name': 'Logo / company name',
        'phone': 'Phone number',
        'whatsapp': 'WhatsApp link',
        'background_style': 'Background style',
    }
    labels.update(overrides)
    return labels


CARD_FIELD_LABELS = _build_card_field_labels()
CARD_TRACKED_CARD_KEYS = set(CARD_FIELD_LABELS.keys())


def _normalize_change_value(value):
    if value is None:
        return ''
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned[:180] + '…' if len(cleaned) > 181 else cleaned
    return str(value)


def _build_card_change_entries(old_data: dict, new_data: dict):
    if not isinstance(old_data, dict):
        old_data = {}
    if not isinstance(new_data, dict):
        new_data = {}

    entries = []
    for key in CARD_TRACKED_CARD_KEYS:
        before = _normalize_change_value(old_data.get(key))
        after = _normalize_change_value(new_data.get(key))
        if before == after:
            continue
        if not before and not after:
            continue
        entries.append({
            'field': key,
            'label': CARD_FIELD_LABELS.get(key, key.replace('_', ' ').title()),
            'before': before,
            'after': after,
        })
    return entries


def _summarize_change_entries(entries):
    if not entries:
        return ''
    labels = [entry['label'] for entry in entries]
    if len(labels) == 1:
        return f"Updated {labels[0]}"
    if len(labels) == 2:
        return f"Updated {labels[0]} and {labels[1]}"
    return f"Updated {', '.join(labels[:-1])}, and {labels[-1]}"


def _record_card_change(card: Card, user: User, entries: list[dict]):
    if not entries:
        return
    summary = _summarize_change_entries(entries)
    CardChangeLog.objects.create(
        card=card,
        user=user if user.is_authenticated else None,
        summary=summary,
        changes=entries,
    )


def _normalize_whatsapp_link(value: str) -> str:
    if not value:
        return ''
    value = value.strip()
    # Defensive: strip JavaScript "undefined" that leaked in from an older
    # editor build before the phone-picker fix
    value = value.replace('undefined', '')
    if value.startswith('http://') or value.startswith('https://'):
        # Also re-extract digits from the URL so a partly-corrupted URL still resolves
        m = re.search(r'wa\.me/(\+?\d+)', value)
        if m:
            digits = re.sub(r'\D', '', m.group(1))
            return f"https://wa.me/{digits}" if digits else ''
        return value
    digits = re.sub(r'\D', '', value.lstrip('+'))
    return f"https://wa.me/{digits}" if digits else ''


def _normalize_phone_number(value: str, default_code: str = '880') -> tuple[str, str]:
    if not value:
        return '', ''
    # Defensive: drop JS "undefined" leaked in by an older editor build
    cleaned = str(value).replace('undefined', '')
    digits = re.sub(r'\D', '', cleaned.lstrip('+'))
    if not digits:
        return '', ''

    match_code = ''
    for code, _label in sorted(COUNTRY_CHOICES, key=lambda item: len(item[0]), reverse=True):
        if digits.startswith(code):
            match_code = code
            break

    if not match_code:
        if not digits.startswith(default_code):
            digits = f"{default_code}{digits}"
        match_code = default_code

    remainder = digits[len(match_code):]
    display = f"+{match_code} {remainder}" if remainder else f"+{match_code}"
    return digits, display



def index(request):
    ctx = {'feedback_form': FeedbackForm()}
    ctx.update(_landing_demo_card_context(request))
    return render(request, 'cards/index.html', ctx)


def _landing_demo_card_context(request):
    """Load a real card to show as a live preview on the landing page.

    Slug is configurable via `LANDING_DEMO_CARD_SLUG`; falls back to the first
    active card so local dev works even without the demo user seeded.
    """
    demo_slug = getattr(settings, 'LANDING_DEMO_CARD_SLUG', 'shiplu07')
    card = (
        Card.objects.filter(slug=demo_slug, is_active=True).select_related('user').first()
        or Card.objects.filter(is_active=True).select_related('user').order_by('id').first()
    )
    if not card:
        return {}

    data = card.card_data or {}
    whatsapp_link = _normalize_whatsapp_link(data.get('whatsapp'))
    phone_digits, phone_display = _normalize_phone_number(data.get('phone'))
    phone_tel = f"+{phone_digits}" if phone_digits else ''

    social_priority = ['linkedin', 'instagram', 'twitter', 'facebook', 'youtube', 'github', 'tiktok', 'telegram']
    top_socials = []
    for key in social_priority:
        val = data.get(key)
        if val:
            top_socials.append({'net': key, 'url': val})
        if len(top_socials) == 5:
            break

    theme = None
    theme_slug = data.get('theme_slug')
    if theme_slug:
        theme = CardTheme.objects.filter(slug=theme_slug, is_active=True).first()

    public_slug = getattr(settings, 'LANDING_DEMO_PUBLIC_SLUG', 'shiplu07')
    public_base = getattr(settings, 'LANDING_DEMO_PUBLIC_BASE', 'https://mycard.dupno.com')
    demo_card_url = f'{public_base}/card/{public_slug}/'

    return {
        'demo_card': card,
        'demo_whatsapp_link': whatsapp_link,
        'demo_phone_display': phone_display,
        'demo_phone_tel': phone_tel,
        'demo_top_socials': top_socials,
        'demo_theme': theme,
        'demo_public_slug': public_slug,
        'demo_card_url': demo_card_url,
        'demo_physical_url': f'{public_base}/card/{public_slug}/physical/',
        'demo_public_qr_data_uri': _landing_demo_qr_data_uri(demo_card_url),
    }


@lru_cache(maxsize=8)
def _landing_demo_qr_data_uri(target_url: str) -> str:
    """PNG QR for the landing demo, encoded as a data URI so the template
    doesn't depend on any Card.qr_code file. Cached per URL."""
    try:
        import qrcode
        import base64
        from io import BytesIO

        img = qrcode.make(target_url, box_size=10, border=2)
        buf = BytesIO()
        img.save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception as exc:
        logger.warning("Landing QR generation failed for %s: %s", target_url, exc)
        return ''


@require_POST
def submit_feedback(request):
    form = FeedbackForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, 'Thanks for sharing your feedback — the team will take a look.')
        return redirect(f"{reverse('index')}#feedback")
    else:
        messages.error(request, 'Please fix the highlighted details before sending your feedback.')
    ctx = {'feedback_form': form, 'scroll_to_feedback': True}
    ctx.update(_landing_demo_card_context(request))
    return render(request, 'cards/index.html', ctx, status=400)


def register(request):
    if request.method == 'POST':
        user_form = UserForm(request.POST)
        profile_form = ProfileForm(request.POST)
        if user_form.is_valid() and profile_form.is_valid():
            try:
                with transaction.atomic():
                    user = user_form.save(commit=False)
                    raw_password = user_form.cleaned_data['password']
                    user.set_password(raw_password)
                    user.email = user.email.lower()
                    user.save()

                    profile = profile_form.save(commit=False)
                    profile.user = user
                    if not profile.card_limit:
                        profile.card_limit = DEFAULT_CARD_LIMIT
                    profile.save()

                # Fire-and-forget welcome email — never block registration on it
                try:
                    _send_welcome_email(user)
                except Exception as exc:
                    logger.warning("Welcome email dispatch failed: %s", exc)

                login(request, user)
                messages.success(request, 'Welcome aboard! Your studio is ready for its first card.')
                next_url = (request.GET.get('next') or request.POST.get('next') or '').strip()
                return redirect(next_url or 'dashboard')
            except Exception as exc:
                messages.error(request, 'We could not create your account right now. Please try again.')
                user_form.add_error(None, 'Unexpected error while creating your account. If this persists, contact support.')
        else:
            messages.error(request, 'Please review the highlighted details before continuing.')
    else:
        user_form = UserForm()
        profile_form = ProfileForm()

    return render(request, 'cards/register.html', {
        'user_form': user_form,
        'profile_form': profile_form
    })

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = (request.GET.get('next') or request.POST.get('next') or '').strip()
            return redirect(next_url or 'dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'cards/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard(request):
    change_log_qs = CardChangeLog.objects.order_by('-created_at')
    cards_qs = (
        Card.objects.filter(user=request.user)
        .order_by('-updated_at', '-created_at')
        .prefetch_related(Prefetch('change_logs', queryset=change_log_qs, to_attr='recent_logs'))
    )
    cards = list(cards_qs)
    for card in cards:
        if not hasattr(card, 'recent_logs'):
            card.recent_logs = []

    latest_update_card = cards[0] if cards else None
    latest_update = latest_update_card.updated_at if latest_update_card else None
    latest_update_log = None
    if latest_update_card and getattr(latest_update_card, 'recent_logs', None):
        latest_update_log = latest_update_card.recent_logs[0]

    profile = getattr(request.user, 'profile', None)
    card_limit = getattr(profile, 'card_limit', DEFAULT_CARD_LIMIT)
    total_cards = len(cards)
    remaining_cards = max(card_limit - total_cards, 0)

    # Real analytics across all of the user's cards
    interactions_qs = CardInteraction.objects.filter(card__user=request.user)
    total_views = interactions_qs.filter(kind=CardInteraction.KIND_VIEW).count()
    total_saves = interactions_qs.filter(kind=CardInteraction.KIND_SAVE).count()
    new_leads = LeadCapture.objects.filter(card__user=request.user, status=LeadCapture.STATUS_NEW).count()

    context = {
        'cards': cards,
        'card_limit': card_limit,
        'cards_remaining': remaining_cards,
        'at_card_limit': remaining_cards == 0,
        'latest_update': latest_update,
        'latest_update_log': latest_update_log,
        'total_views': total_views,
        'total_saves': total_saves,
        'new_leads': new_leads,
        'first_card_slug': cards[0].slug if cards else '',
    }
    return render(request, 'cards/dashboard.html', context)


@login_required
def user_messages(request):
    profile = getattr(request.user, 'profile', None)
    current_limit = getattr(profile, 'card_limit', DEFAULT_CARD_LIMIT)

    user_cards = Card.objects.filter(user=request.user).order_by('-created_at')
    pending_requests = UpgradeRequest.objects.filter(user=request.user, status=UpgradeRequest.STATUS_PENDING)
    responded_requests = UpgradeRequest.objects.filter(user=request.user).exclude(status=UpgradeRequest.STATUS_PENDING)

    offline_cards = list(user_cards.filter(is_active=False))
    pending_card_ids = set(
        pending_requests.filter(card__isnull=False).values_list('card_id', flat=True)
    )

    upgrade_history = UpgradeRequest.objects.filter(user=request.user).select_related('card').order_by('-created_at')

    context = {
        'current_cards': user_cards.count(),
        'current_limit': current_limit,
        'pending_upgrade_count': pending_requests.count(),
        'responded_messages_count': responded_requests.count(),
        'offline_cards': offline_cards,
        'pending_card_ids': pending_card_ids,
        'upgrade_requests': upgrade_history,
    }
    return render(request, 'cards/user_messages.html', context)


@login_required
@require_POST
def request_card_limit_increase(request):
    profile = getattr(request.user, 'profile', None)
    current_limit = getattr(profile, 'card_limit', DEFAULT_CARD_LIMIT)

    desired_limit_raw = request.POST.get('desired_limit', '').strip()
    note = (request.POST.get('note') or '').strip()

    try:
        desired_limit = int(desired_limit_raw)
    except (TypeError, ValueError):
        messages.error(request, 'Enter a valid number for your desired limit.')
        return redirect('user_messages')

    if desired_limit <= current_limit:
        messages.info(request, 'Your requested limit is already covered by your current plan.')
        return redirect('user_messages')

    existing_pending = UpgradeRequest.objects.filter(
        user=request.user,
        status=UpgradeRequest.STATUS_PENDING,
        card__isnull=True,
        requested_plan='card_limit_increase'
    ).exists()

    if existing_pending:
        messages.info(request, 'You already have a limit request in review. We will be in touch soon.')
        return redirect('user_messages')

    details = f"Requested limit: {desired_limit}"
    if note:
        details = f"{details}\n\nNotes:\n{note}"

    UpgradeRequest.objects.create(
        user=request.user,
        card=None,
        requested_plan='card_limit_increase',
        message=details
    )

    messages.success(request, 'Thanks! Our team will review your request shortly.')
    return redirect('user_messages')

@login_required
def create_card(request):
    return _handle_card_creation(request, Card.TYPE_PERSONAL)


@login_required
def create_business_card(request):
    return _handle_card_creation(request, Card.TYPE_BUSINESS)


def start_free(request, card_type):
    """One-step onboarding: card-type popup on the landing sends users here.

    - Authenticated users → normal create-card flow (skips signup block).
    - Anonymous users → same create-card page BUT with an inline
      username/email/password block. On POST we create the User + Profile
      + Card in one atomic transaction, then auto-login and redirect to
      the public card. No 'go register first, then come back' bounce."""
    if card_type == 'business':
        chosen_type = Card.TYPE_BUSINESS
    else:
        chosen_type = Card.TYPE_PERSONAL

    if request.user.is_authenticated:
        return _handle_card_creation(request, chosen_type)

    return _handle_anonymous_onboard(request, chosen_type)


def _handle_anonymous_onboard(request, card_type: str):
    """Anonymous variant of the card builder. Renders create_card.html
    with the signup block visible and creates user + card together."""
    variant = CARD_VARIANT_CONFIG.get(card_type, CARD_VARIANT_CONFIG[Card.TYPE_PERSONAL])
    form_class = CARD_FORM_BY_TYPE.get(card_type, CardForm)

    signup_form = UserForm(request.POST or None)
    form = form_class(request.POST or None, request.FILES or None)

    if request.method == 'POST':
        card_ok = form.is_valid()
        signup_ok = signup_form.is_valid()
        if card_ok and signup_ok:
            try:
                with transaction.atomic():
                    user = signup_form.save(commit=False)
                    user.set_password(signup_form.cleaned_data['password'])
                    user.email = user.email.lower()
                    user.save()

                    profile, _ = Profile.objects.get_or_create(user=user)
                    if not profile.card_limit:
                        profile.card_limit = DEFAULT_CARD_LIMIT
                        profile.save(update_fields=['card_limit'])

                    card = form.save(commit=False)
                    card.user = user
                    card.card_type = card_type
                    card.card_data = _extract_card_form_payload(form)
                    theme_slug = _sanitize_theme_slug(
                        user, (request.POST.get('theme_slug') or '').strip()[:60]
                    )
                    if theme_slug:
                        card.card_data['theme_slug'] = theme_slug
                    card.save()

                try:
                    _send_welcome_email(user)
                except Exception as exc:
                    logger.warning("Welcome email dispatch failed: %s", exc)

                login(request, user)
                messages.success(request, variant['success_message'])
                return redirect('view_card', slug=card.slug)
            except Exception as exc:
                logger.exception("Anonymous onboard failed: %s", exc)
                messages.error(request, 'We could not save your card right now. Please try again.')
        else:
            messages.error(request, 'Fix the highlighted details so we can create your card.')

    context = {
        'form': form,
        'signup_form': signup_form,
        'show_signup_block': True,
        'card_limit': DEFAULT_CARD_LIMIT,
        'cards_remaining': DEFAULT_CARD_LIMIT,
        'builder_variant': variant,
        'themes': themes_for_user(list(CardTheme.objects.filter(is_active=True)), None),
        'feature_ai': settings.FEATURE_AI,
    }
    return render(request, 'cards/create_card.html', context)


def _handle_card_creation(request, card_type: str):
    profile = getattr(request.user, 'profile', None)
    card_limit = getattr(profile, 'card_limit', DEFAULT_CARD_LIMIT)
    total_cards = Card.objects.filter(user=request.user).count()
    remaining_cards = card_limit - total_cards

    variant = CARD_VARIANT_CONFIG.get(card_type, CARD_VARIANT_CONFIG[Card.TYPE_PERSONAL])
    form_class = CARD_FORM_BY_TYPE.get(card_type, CardForm)

    if remaining_cards <= 0:
        first_card = Card.objects.filter(user=request.user).order_by('created_at').first()

        # Free-plan users are locked to their single card. Route them to
        # pricing so they can upgrade rather than to a dead-end.
        if not is_premium(request.user):
            messages.info(
                request,
                'Your free plan allows one card. Upgrade to Pro to create more.',
            )
            return redirect(reverse('pricing') + '?locked=extra_cards')

        if first_card and card_limit == DEFAULT_CARD_LIMIT:
            messages.info(request, 'Your plan allows one card. We opened the editor for your existing card.')
            return redirect('edit_card', slug=first_card.slug)

        messages.warning(request, 'You have reached your card limit. Ask an administrator to extend your allowance.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = form_class(request.POST, request.FILES)
        if form.is_valid():
            card = form.save(commit=False)
            card.user = request.user
            card.card_type = card_type
            card.card_data = _extract_card_form_payload(form)
            theme_slug = _sanitize_theme_slug(request.user, (request.POST.get('theme_slug') or '').strip()[:60])
            if theme_slug:
                card.card_data['theme_slug'] = theme_slug
            card.save()

            messages.success(request, variant['success_message'])
            return redirect('view_card', slug=card.slug)
        messages.error(request, 'Fix the highlighted details so we can create your card.')
    else:
        form = form_class()

    context = {
        'form': form,
        'card_limit': card_limit,
        'cards_remaining': remaining_cards,
        'builder_variant': variant,
        'themes': themes_for_user(list(CardTheme.objects.filter(is_active=True)), request.user),
        'feature_ai': settings.FEATURE_AI,
    }
    return render(request, 'cards/create_card.html', context)

@login_required
def edit_card(request, slug):
    card = get_object_or_404(Card, slug=slug, user=request.user)

    if not card.is_active:
        messages.info(request, 'This card is currently offline. Any updates will be live once an admin reactivates it.')

    profile = getattr(request.user, 'profile', None)
    card_limit = getattr(profile, 'card_limit', DEFAULT_CARD_LIMIT)
    total_cards = Card.objects.filter(user=request.user).count()
    remaining_cards = max(card_limit - total_cards, 0)

    form_class = CARD_FORM_BY_TYPE.get(card.card_type, CardForm)
    builder_variant = CARD_VARIANT_CONFIG.get(card.card_type, CARD_VARIANT_CONFIG[Card.TYPE_PERSONAL])

    slug_error = None

    if request.method == 'POST':
        form = form_class(request.POST, request.FILES, instance=card)

        # One-time custom public URL. Applied before form.save() so the
        # updated slug lands in the same DB write. Free users are locked
        # out entirely — they keep the auto-generated slug.
        requested_slug = (request.POST.get('custom_slug') or '').strip().lower()
        if requested_slug and requested_slug != card.slug:
            if not is_premium(request.user):
                slug_error = 'Custom public URLs are a Pro feature. Upgrade to unlock URL customisation.'
                messages.info(request, slug_error)
            else:
                slug_error = _apply_custom_slug(card, requested_slug)
                if slug_error:
                    messages.error(request, slug_error)

        if slug_error is None and form.is_valid():
            previous_card_data = _card_initial_data(card)
            previous_avatar = card.avatar.name if card.avatar else ''
            previous_logo = card.logo.name if card.logo else ''

            _apply_card_form_updates(card, form)
            theme_slug = _sanitize_theme_slug(request.user, (request.POST.get('theme_slug') or '').strip()[:60])
            if theme_slug:
                card.card_data['theme_slug'] = theme_slug
            saved_card = form.save()  # This re-triggers the model's save method, updating QR code etc.

            current_card_data = saved_card.card_data if isinstance(saved_card.card_data, dict) else {}
            change_entries = _build_card_change_entries(previous_card_data, current_card_data)

            if 'avatar' in form.changed_data:
                change_entries.append({
                    'field': 'avatar',
                    'label': 'Avatar image',
                    'before': previous_avatar or 'None',
                    'after': saved_card.avatar.name if saved_card.avatar else 'Removed',
                })
            if 'logo' in form.changed_data:
                change_entries.append({
                    'field': 'logo',
                    'label': 'Logo image',
                    'before': previous_logo or 'None',
                    'after': saved_card.logo.name if saved_card.logo else 'Removed',
                })

            _record_card_change(saved_card, request.user, change_entries)

            return redirect(card.get_absolute_url())
    else:
        # Pre-populate form with existing data
        initial_data = _card_initial_data(card)
        form = form_class(instance=card, initial=initial_data)

    context = {
        'form': form,
        'card': card,
        'card_limit': card_limit,
        'cards_remaining': remaining_cards,
        'builder_variant': builder_variant,
        'themes': themes_for_user(list(CardTheme.objects.filter(is_active=True)), request.user),
        'feature_ai': settings.FEATURE_AI,
        'slug_error': slug_error,
    }
    return render(request, 'cards/create_card.html', context)


# Slugs that must never be handed to a card because they collide with
# existing top-level routes or generic words a scanner might mistake.
_RESERVED_CARD_SLUGS = {
    'admin', 'my-admin', 'api', 'card', 'cards', 'dashboard', 'edit',
    'create', 'login', 'logout', 'register', 'signup', 'signin', 'reset',
    'password', 'documentation', 'docs', 'faq', 'feedback', 'pricing',
    'physical', 'analytics', 'leads', 'set-language', 'static', 'media',
    'about', 'help', 'support', 'settings', 'account', 'privacy', 'terms',
    'test', 'null', 'undefined', 'shiplu07',
}


def _sanitize_theme_slug(user, theme_slug: str) -> str:
    """Reject premium theme picks for free users. Silent — the picker
    already renders a locked badge, so we don't need a flash message."""
    if not theme_slug:
        return ''
    theme = CardTheme.objects.filter(slug=theme_slug, is_active=True).first()
    if not theme:
        return ''
    if theme.is_premium and not is_premium(user):
        return ''
    return theme_slug


def _apply_custom_slug(card, requested: str) -> str | None:
    """Apply a user-requested public URL to *card*.

    Returns None on success (card is mutated in-place) or a human-readable
    error message the caller should surface to the user. The change is
    one-shot: once `slug_customized` is True the user is locked out.
    """
    if card.slug_customized:
        return 'This card URL was already customised once and cannot be changed again.'

    cleaned = re.sub(r'[^a-z0-9-]+', '-', requested.lower()).strip('-')
    cleaned = re.sub(r'-{2,}', '-', cleaned)[:60]

    if len(cleaned) < 3:
        return 'Public URL must be at least 3 characters — letters, numbers, or hyphens only.'
    if cleaned in _RESERVED_CARD_SLUGS:
        return f'"{cleaned}" is reserved. Please choose a different URL.'
    if Card.objects.exclude(pk=card.pk).filter(slug=cleaned).exists():
        return f'The URL "{cleaned}" is already taken by another card. Try a more unique variation.'

    card.slug = cleaned
    card.slug_customized = True
    return None


@user_passes_test(lambda u: u.is_superuser, login_url='/my-admin/login/')
def admin_edit_card(request, slug):
    card = get_object_or_404(Card, slug=slug)

    form_class = CARD_FORM_BY_TYPE.get(card.card_type, CardForm)
    builder_variant = CARD_VARIANT_CONFIG.get(card.card_type, CARD_VARIANT_CONFIG[Card.TYPE_PERSONAL])

    if request.method == 'POST':
        form = form_class(request.POST, request.FILES, instance=card)
        if form.is_valid():
            previous_card_data = _card_initial_data(card)
            previous_avatar = card.avatar.name if card.avatar else ''
            previous_logo = card.logo.name if card.logo else ''

            _apply_card_form_updates(card, form)
            saved_card = form.save()

            current_card_data = saved_card.card_data if isinstance(saved_card.card_data, dict) else {}
            change_entries = _build_card_change_entries(previous_card_data, current_card_data)

            if 'avatar' in form.changed_data:
                change_entries.append({
                    'field': 'avatar',
                    'label': 'Avatar image',
                    'before': previous_avatar or 'None',
                    'after': saved_card.avatar.name if saved_card.avatar else 'Removed',
                })
            if 'logo' in form.changed_data:
                change_entries.append({
                    'field': 'logo',
                    'label': 'Logo image',
                    'before': previous_logo or 'None',
                    'after': saved_card.logo.name if saved_card.logo else 'Removed',
                })

            _record_card_change(saved_card, request.user, change_entries)
            return redirect('admin_dashboard')
    else:
        initial_data = _card_initial_data(card)
        form = form_class(instance=card, initial=initial_data)

    return render(
        request,
        'cards/create_card.html',
        {
            'form': form,
            'card': card,
            'admin_edit': True,
            'builder_variant': builder_variant,
        }
    )

def view_card(request, slug):
    card = get_object_or_404(Card, slug=slug)
    is_owner = request.user.is_authenticated and request.user == card.user
    is_admin = request.user.is_authenticated and request.user.is_superuser

    from_qr = request.GET.get('qr') == '1'

    if not card.is_active and not is_admin:
        if is_owner:
            existing_request = UpgradeRequest.objects.filter(
                user=request.user,
                card=card,
                status=UpgradeRequest.STATUS_PENDING
            ).first()
            yearly = _yearly_price_for(card.user)
            context = {
                'card': card,
                'existing_request': existing_request,
                'is_owner': True,
                'yearly_price': yearly,
                'reactivation_fee': _reactivation_fee_for(card),
                'total_due': yearly + _reactivation_fee_for(card),
                'context_source': 'digital',
            }
            return render(request, 'cards/card_inactive.html', context)
        return render(request, 'cards/card_inactive_public.html', {'card': card}, status=200)

    # Track view interaction (once per session per card) and count total views
    if card.is_active and not is_owner and not is_admin:
        visited_cards = request.session.get('visited_cards', [])
        if card.slug not in visited_cards:
            visited_cards.append(card.slug)
            request.session['visited_cards'] = visited_cards
            try:
                CardInteraction.objects.create(
                    card=card,
                    kind=CardInteraction.KIND_VIEW,
                    session_id=(request.session.session_key or '')[:64],
                    referrer=request.META.get('HTTP_REFERER', '')[:255],
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                )
            except Exception as exc:
                logger.warning("Skipping view tracking for card %s: %s", card.slug, exc)

    profile_views = card.interactions.filter(kind=CardInteraction.KIND_VIEW).count()

    # The QR code URL is now generated in the model, but we pass it for consistency
    # Note: The model-generated QR already has ?qr=1.
    qr_code_url = request.build_absolute_uri(card.get_absolute_url()) + "?qr=1"

    whatsapp_link = _normalize_whatsapp_link(card.card_data.get('whatsapp'))
    phone_digits, phone_display = _normalize_phone_number(card.card_data.get('phone'))
    phone_tel = f"+{phone_digits}" if phone_digits else ''

    # Resolve theme (if any) so the template can paint accent + text colors
    theme = None
    theme_slug = (card.card_data or {}).get('theme_slug')
    if theme_slug:
        theme = CardTheme.objects.filter(slug=theme_slug, is_active=True).first()

    context = {
        'card': card,
        'is_owner': is_owner,
        'is_admin_viewer': is_admin,
        'show_guest_cta': not is_owner and not is_admin,
        'from_qr': from_qr,
        'qr_code_url': qr_code_url,
        'whatsapp_link': whatsapp_link,
        'phone_digits': phone_digits,
        'phone_display': phone_display,
        'phone_tel': phone_tel,
        'profile_views': profile_views,
        'business_highlight': _resolve_business_highlight(card, phone_display, phone_tel),
        'theme': theme,
    }
    return render(request, 'cards/view_card.html', context)

def admin_login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user.is_superuser:
                login(request, user)
                return redirect('admin_dashboard')
            else:
                form.add_error(None, "You do not have permission to access the admin dashboard.")
    else:
        form = AuthenticationForm(request)
    return render(request, 'cards/admin_login.html', {'form': form})

@user_passes_test(lambda u: u.is_superuser, login_url='/my-admin/login/')
def admin_dashboard(request):
    users = (
        User.objects.select_related('profile')
        .annotate(
            card_count=Count('card'),
            personal_count=Count('card', filter=Q(card__card_type=Card.TYPE_PERSONAL)),
            business_count=Count('card', filter=Q(card__card_type=Card.TYPE_BUSINESS)),
        )
        .order_by('-date_joined')
    )
    cards = Card.objects.select_related('user', 'user__profile').order_by('-created_at')
    feedback_entries = list(Feedback.objects.all()[:8])
    feedback_total = Feedback.objects.count()

    user_records = []
    for user in users:
        profile = getattr(user, 'profile', None)
        card_limit = getattr(profile, 'card_limit', DEFAULT_CARD_LIMIT)
        card_limit_form = AdminCardLimitForm(initial={'card_limit': card_limit}, auto_id=f'id_user_{user.id}_%s')
        user_cards = list(user.card_set.order_by('created_at'))
        primary_card_slug = user_cards[0].slug if user_cards else None
        user_records.append({
            'instance': user,
            'id': user.id,
            'name': (user.get_full_name() or '').strip() or user.username,
            'email': user.email or '',
            'phone': _get_user_phone(user),
            'registered': user.date_joined,
            'is_active': user.is_active,
            'status_label': 'Active' if user.is_active else 'Inactive',
            'card_limit': card_limit,
            'card_count': user.card_count,
            'personal_count': user.personal_count,
            'business_count': user.business_count,
            'card_limit_form': card_limit_form,
            'primary_card_slug': primary_card_slug,
            'cards': user_cards,
            'has_live_card':    any(c.is_active for c in user_cards),
            'has_offline_card': any(not c.is_active for c in user_cards),
        })

    pending_requests = UpgradeRequest.objects.filter(status=UpgradeRequest.STATUS_PENDING)

    # ---- Platform metrics (Sprint 3-era CardInteraction rollup) ----
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    total_views = CardInteraction.objects.filter(kind=CardInteraction.KIND_VIEW).count()
    total_leads = LeadCapture.objects.count()
    new_leads = LeadCapture.objects.filter(status=LeadCapture.STATUS_NEW).count()
    users_this_week = User.objects.filter(date_joined__gte=week_ago).count()
    cards_this_week = Card.objects.filter(created_at__gte=week_ago).count()
    personal_cards = cards.filter(card_type=Card.TYPE_PERSONAL).count()
    business_cards = cards.filter(card_type=Card.TYPE_BUSINESS).count()

    # ---- Top performing cards (by views) ----
    top_cards_qs = (
        cards.annotate(view_count=Count('interactions', filter=Q(interactions__kind=CardInteraction.KIND_VIEW)))
        .order_by('-view_count')[:6]
    )

    # ---- Recent activity feed ----
    recent_activity = (
        CardInteraction.objects.select_related('card', 'card__user')
        .order_by('-created_at')[:12]
    )

    context = {
        'total_users': len(user_records),
        'total_cards': cards.count(),
        'personal_cards': personal_cards,
        'business_cards': business_cards,
        'total_views': total_views,
        'total_leads': total_leads,
        'new_leads': new_leads,
        'users_this_week': users_this_week,
        'cards_this_week': cards_this_week,
        'all_cards': cards,
        'all_users': user_records,
        'pending_request_count': pending_requests.count(),
        'feedback_entries': feedback_entries,
        'feedback_count': feedback_total,
        'top_cards': top_cards_qs,
        'recent_activity': recent_activity,
    }
    return render(request, 'cards/admin_dashboard.html', context)


@user_passes_test(lambda u: u.is_superuser, login_url='/my-admin/login/')
def admin_set_card_limit(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)

    if request.method != 'POST':
        return redirect('admin_dashboard')

    form = AdminCardLimitForm(request.POST)
    if form.is_valid():
        new_limit = form.cleaned_data['card_limit']
        try:
            profile = target_user.profile
        except Profile.DoesNotExist:
            messages.error(request, 'This user does not have a profile yet, so we cannot update their limit.')
        else:
            existing_cards = target_user.card_set.count()
            profile.card_limit = new_limit
            profile.save(update_fields=['card_limit'])
            if new_limit < existing_cards:
                messages.warning(
                    request,
                    f"Limit updated to {new_limit}, but the user already has {existing_cards} cards. They will need to archive cards before creating new ones."
                )
            else:
                messages.success(request, f'Card limit for {target_user.username} updated to {new_limit}.')
    else:
        error_text = ', '.join(form.errors.get('card_limit', [])) or 'Enter a valid limit to continue.'
        messages.error(request, error_text)

    return redirect('admin_dashboard')


@user_passes_test(lambda u: u.is_superuser, login_url='/my-admin/login/')
def admin_toggle_card_status(request, slug):
    card = get_object_or_404(Card, slug=slug)

    if request.method == 'POST':
        card.is_active = not card.is_active
        card.save(update_fields=['is_active'])
        if card.is_active:
            UpgradeRequest.objects.filter(card=card, status=UpgradeRequest.STATUS_PENDING).update(
                status=UpgradeRequest.STATUS_APPROVED,
                responded_at=timezone.now(),
                handled_by=request.user,
                admin_notes='Approved via quick toggle'
            )
        state = 'active' if card.is_active else 'offline'
        messages.success(request, f'Card “{card.slug}” is now {state}.')

    return redirect('admin_dashboard')


@login_required
@require_POST
def request_upgrade(request, slug):
    card = get_object_or_404(Card, slug=slug, user=request.user)

    if card.is_active:
        messages.info(request, 'This card is already active.')
        return redirect(card.get_absolute_url())

    existing_request = UpgradeRequest.objects.filter(
        user=request.user,
        card=card,
        status=UpgradeRequest.STATUS_PENDING
    ).first()
    if existing_request:
        messages.info(request, 'We already have your request on file. Our concierge team will follow up shortly.')
        return redirect(card.get_absolute_url())

    requested_plan = request.POST.get('plan') or 'monthly_upgrade'
    user_note = request.POST.get('note', '').strip()

    UpgradeRequest.objects.create(
        user=request.user,
        card=card,
        requested_plan=requested_plan,
        message=user_note
    )

    messages.success(request, 'Upgrade request sent. Our team will reach out within 1 business day.')
    return redirect(card.get_absolute_url())


@user_passes_test(lambda u: u.is_superuser, login_url='/my-admin/login/')
def admin_messages(request):
    upgrade_requests = UpgradeRequest.objects.select_related('user', 'card').order_by('-created_at')
    available_plans = SubscriptionPlan.objects.filter(is_active=True)
    return render(request, 'cards/admin_messages.html', {
        'upgrade_requests': upgrade_requests,
        'available_plans': available_plans,
    })


@user_passes_test(lambda u: u.is_superuser, login_url='/my-admin/login/')
@require_POST
def admin_handle_upgrade(request, request_id, action):
    upgrade_request = get_object_or_404(UpgradeRequest, pk=request_id)

    if upgrade_request.status != UpgradeRequest.STATUS_PENDING:
        messages.info(request, 'This request has already been handled.')
        return redirect('admin_messages')

    admin_notes = request.POST.get('admin_notes', '').strip()
    card_limit_raw = request.POST.get('card_limit')
    reactivate = request.POST.get('reactivate_card') == 'on'

    if action == 'approve':
        profile = getattr(upgrade_request.user, 'profile', None)
        if profile and card_limit_raw:
            try:
                new_limit = int(card_limit_raw)
            except (TypeError, ValueError):
                messages.error(request, 'Include a valid number for the new allowance.')
                return redirect('admin_messages')
            profile.card_limit = max(DEFAULT_CARD_LIMIT, new_limit)
            profile.save(update_fields=['card_limit'])

        if reactivate and upgrade_request.card:
            upgrade_request.card.is_active = True
            upgrade_request.card.save(update_fields=['is_active'])

        upgrade_request.mark(UpgradeRequest.STATUS_APPROVED, request.user, admin_notes)
        messages.success(request, f'Upgrade approved for {upgrade_request.user.username}.')

    elif action == 'reject':
        upgrade_request.mark(UpgradeRequest.STATUS_REJECTED, request.user, admin_notes)
        messages.info(request, f'Upgrade request rejected for {upgrade_request.user.username}.')
    else:
        messages.error(request, 'Unsupported action.')

    return redirect('admin_messages')


@user_passes_test(lambda u: u.is_superuser, login_url='/my-admin/login/')
def delete_user_admin(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)

    if request.method == 'POST':
        if target_user == request.user:
            messages.error(request, 'You cannot delete your own admin account while logged in.')
        else:
            target_user.delete()
            messages.success(request, f'User “{target_user.username}” has been removed.')

    return redirect('admin_dashboard')


@user_passes_test(lambda u: u.is_superuser)
def delete_card_admin(request, slug):
    card = get_object_or_404(Card, slug=slug)
    card.delete()
    messages.success(request, f'Card “{slug}” was removed from the workspace.')
    return redirect('admin_dashboard')


CARD_EXPORT_HEADERS = ['ID', 'Name', 'Email', 'Phone', 'Slug', 'Created Date']
USER_EXPORT_HEADERS = ['User ID', 'Full Name', 'Email', 'Phone', 'Registered Date', 'Status']


def _collect_card_data_keys(cards):
    keys = set()
    for card in cards:
        data = card.card_data if isinstance(card.card_data, dict) else {}
        keys.update(data.keys())
    return sorted(keys)


def _format_card_data_value(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _get_user_phone(user):
    try:
        return user.profile.phone_number or ''
    except (Profile.DoesNotExist, AttributeError):
        return ''


def _card_initial_data(card):
    if isinstance(card.card_data, dict):
        return card.card_data.copy()
    return {}


def _apply_card_form_updates(card, form):
    if not isinstance(card.card_data, dict):
        card.card_data = {}

    excluded_keys = {'avatar', 'logo', 'whatsapp_country', 'whatsapp_number', 'phone_country', 'phone_number'}
    for key, value in form.cleaned_data.items():
        if key in excluded_keys:
            continue
        if value:
            card.card_data[key] = value
        elif key in card.card_data:
            card.card_data[key] = value


def _extract_card_form_payload(form):
    excluded_keys = {'avatar', 'logo', 'whatsapp_country', 'whatsapp_number', 'phone_country', 'phone_number'}
    payload = {}
    for key, value in form.cleaned_data.items():
        if key in excluded_keys:
            continue
        payload[key] = value
    return payload


def _resolve_business_highlight(card: Card, phone_display: str, phone_tel: str):
    if card.card_type != Card.TYPE_BUSINESS:
        return None

    card_data = card.card_data if isinstance(card.card_data, dict) else {}
    choice = (card_data.get('extra_highlight') or '').strip()
    content = (card_data.get('extra_highlight_content') or '').strip()
    if not choice:
        return None

    choice = choice.lower()

    if choice == 'phone':
        number_source = content or card_data.get('phone') or phone_display
        digits, display = _normalize_phone_number(number_source)
        if not digits and phone_display:
            digits = re.sub(r'\D', '', phone_tel)
            display = phone_display
        if not digits:
            return None
        return {
            'type': 'phone',
            'icon': 'phone',
            'label': 'Call us directly',
            'value': display,
            'link': f'tel:+{digits}' if digits else '',
            'copy_value': f'+{digits}' if digits else '',
        }

    if choice == 'website':
        website = content or card_data.get('website')
        if not website:
            return None
        display = re.sub(r'^https?://', '', website).rstrip('/')
        return {
            'type': 'website',
            'icon': 'globe',
            'label': 'Visit our website',
            'value': display,
            'link': website,
            'copy_value': website,
        }

    if choice == 'email':
        email = content or card_data.get('email')
        if not email:
            return None
        return {
            'type': 'email',
            'icon': 'mail',
            'label': 'Email our team',
            'value': email,
            'link': f'mailto:{email}',
            'copy_value': email,
        }

    if choice == 'photo':
        image = card.logo or card.avatar
        if not image:
            return None
        return {
            'type': 'photo',
            'icon': 'image',
            'label': 'Brand highlight',
            'media_url': image.url,
            'media_alt': content or card.card_data.get('logo_name') or 'Featured brand asset',
        }

    return None


def _build_card_row(card: Card, extra_keys):
    card_data = card.card_data or {}
    user = card.user

    name = (
        f"{card_data.get('firstName', '')} {card_data.get('lastName', '')}".strip()
        or user.get_full_name()
        or user.username
    )

    phone = card_data.get('phone') or getattr(getattr(user, 'profile', None), 'phone_number', '')
    created = card.created_at.strftime('%Y-%m-%d %H:%M:%S') if card.created_at else ''

    base_row = [
        str(user.id),
        name,
        user.email or '',
        phone or '',
        card.slug or '',
        created,
    ]

    if isinstance(card_data, dict):
        data_values = [_format_card_data_value(card_data.get(key)) for key in extra_keys]
    else:
        data_values = ['' for _ in extra_keys]

    return base_row + data_values


def _build_user_row(user):
    full_name = user.get_full_name() or user.username
    phone = _get_user_phone(user)
    registered = user.date_joined.strftime('%Y-%m-%d %H:%M:%S') if user.date_joined else ''
    status = 'Active' if user.is_active else 'Inactive'
    return [
        str(user.id),
        full_name,
        user.email or '',
        phone,
        registered,
        status,
    ]


def _superuser_only(request):
    return request.user.is_authenticated and request.user.is_superuser


def export_cards_csv(request):
    if not _superuser_only(request):
        return HttpResponse('Unauthorized', status=401)

    users = list(User.objects.select_related('profile').order_by('id'))
    cards = list(Card.objects.select_related('user', 'user__profile').order_by('id'))
    card_data_keys = _collect_card_data_keys(cards)
    headers = CARD_EXPORT_HEADERS + card_data_keys

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        users_buffer = StringIO()
        users_writer = csv.writer(users_buffer)
        users_writer.writerow(USER_EXPORT_HEADERS)
        for user in users:
            users_writer.writerow(_build_user_row(user))
        archive.writestr('users.csv', users_buffer.getvalue())

        cards_buffer = StringIO()
        cards_writer = csv.writer(cards_buffer)
        cards_writer.writerow(headers)
        for card in cards:
            cards_writer.writerow(_build_card_row(card, card_data_keys))
        archive.writestr('cards.csv', cards_buffer.getvalue())

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="dashboard_csv_exports.zip"'
    return response


def export_cards_excel(request):
    if not _superuser_only(request):
        return HttpResponse('Unauthorized', status=401)

    users = list(User.objects.select_related('profile').order_by('id'))
    cards = list(Card.objects.select_related('user', 'user__profile').order_by('id'))
    card_data_keys = _collect_card_data_keys(cards)
    card_headers = CARD_EXPORT_HEADERS + card_data_keys

    wb = Workbook()
    users_ws = wb.active
    users_ws.title = 'Users'
    users_ws.append(USER_EXPORT_HEADERS)
    for user in users:
        users_ws.append(_build_user_row(user))

    cards_ws = wb.create_sheet(title='Cards')
    cards_ws.append(card_headers)
    for card in cards:
        cards_ws.append(_build_card_row(card, card_data_keys))

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="dashboard.xlsx"'
    wb.save(response)
    return response

def documentation_view(request):
    readme_path = os.path.join(settings.BASE_DIR, 'README.md')
    try:
        with open(readme_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        html_content = markdown.markdown(markdown_content)
    except FileNotFoundError:
        html_content = "<h1>README.md not found</h1>"
    return render(request, 'cards/documentation.html', {'html_content': html_content})

def _mask_email(email: str) -> str:
    """Mask an email like Google does: 'sh•••••••3@gmail.com'."""
    if not email or '@' not in email:
        return ''
    local, domain = email.rsplit('@', 1)
    if len(local) <= 3:
        masked_local = local[0] + '•' * max(len(local) - 1, 1)
    else:
        masked_local = local[:2] + '•' * (len(local) - 3) + local[-1]
    return f'{masked_local}@{domain}'


def _send_otp_email(*, to_email: str, to_name: str, otp: str) -> tuple[bool, str]:
    """Fire off an OTP email via ZeptoMail. Returns (ok, message)."""
    import urllib.request
    import urllib.error

    if not settings.ZEPTOMAIL_TOKEN:
        return False, 'Email OTP not configured on this server.'

    html_body = f"""
    <div style="font-family: 'Bai Jamjuree', 'Inter', system-ui, sans-serif; background:#05060B; padding:32px; color:#F2F4F8;">
      <div style="max-width:520px; margin:0 auto; background:#0B0D14; border:1px solid rgba(255,255,255,0.08); border-radius:20px; padding:32px 28px;">
        <div style="display:inline-flex; align-items:center; gap:8px; margin-bottom:16px;">
          <div style="width:32px; height:32px; border-radius:8px; background:linear-gradient(135deg,#7CFFB2,#38E1FF);"></div>
          <span style="font-family:'Bai Jamjuree', sans-serif; font-weight:700; color:#F2F4F8; font-size:1.1rem;">MY-Card</span>
        </div>
        <h1 style="font-family:'Bai Jamjuree', sans-serif; font-size:1.4rem; margin:0 0 12px; color:#F2F4F8;">Password reset code</h1>
        <p style="color:#A6ADBB; line-height:1.55; margin:0 0 24px;">
          Hi {to_name or 'there'}, use the code below to reset your MY-Card password. It expires in 10 minutes.
        </p>
        <div style="text-align:center; padding:20px; background:#12141C; border:1px solid rgba(124,255,178,0.35); border-radius:14px; margin-bottom:24px;">
          <div style="font-family:'JetBrains Mono', monospace; font-size:2.6rem; font-weight:700; letter-spacing:0.4em; color:#7CFFB2;">{otp}</div>
        </div>
        <p style="color:#6B7280; font-size:0.85rem; line-height:1.5; margin:0;">
          Didn't request this? You can safely ignore this email — nothing will change until the code is used.
        </p>
        <hr style="border:none; border-top:1px solid rgba(255,255,255,0.06); margin:24px 0;">
        <p style="color:#6B7280; font-size:0.75rem; margin:0;">
          Sent by MY-Card · Digital identity, done right.
        </p>
      </div>
    </div>
    """

    payload = json.dumps({
        'from': {'address': settings.ZEPTOMAIL_FROM_ADDRESS, 'name': settings.ZEPTOMAIL_FROM_NAME},
        'to': [{'email_address': {'address': to_email, 'name': to_name or ''}}],
        'subject': f'{otp} is your MY-Card password reset code',
        'htmlbody': html_body,
    }).encode('utf-8')

    req = urllib.request.Request(
        settings.ZEPTOMAIL_URL,
        data=payload,
        headers={
            'accept': 'application/json',
            'content-type': 'application/json',
            'authorization': settings.ZEPTOMAIL_TOKEN,
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            logger.info("ZeptoMail response: %s", body[:200])
            return True, 'sent'
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode('utf-8', errors='replace')
        except Exception:
            err_body = str(e)
        logger.warning("ZeptoMail HTTPError: %s - %s", e.code, err_body[:200])
        return False, f'Email service returned {e.code}'
    except Exception as exc:
        logger.warning("ZeptoMail send failed: %s", exc)
        return False, 'Email service unavailable'


def _make_otp() -> str:
    """6-digit numeric OTP."""
    return f'{random.randint(0, 999999):06d}'


def _send_zepto_html(*, to_email: str, to_name: str, subject: str, html_body: str) -> tuple[bool, str]:
    """Generic ZeptoMail HTML sender used by welcome / receipts / OTP."""
    import urllib.request
    import urllib.error

    if not settings.ZEPTOMAIL_TOKEN:
        return False, 'Email service not configured on this server.'

    payload = json.dumps({
        'from': {'address': settings.ZEPTOMAIL_FROM_ADDRESS, 'name': settings.ZEPTOMAIL_FROM_NAME},
        'to': [{'email_address': {'address': to_email, 'name': to_name or ''}}],
        'subject': subject,
        'htmlbody': html_body,
    }).encode('utf-8')

    req = urllib.request.Request(
        settings.ZEPTOMAIL_URL,
        data=payload,
        headers={
            'accept': 'application/json',
            'content-type': 'application/json',
            'authorization': settings.ZEPTOMAIL_TOKEN,
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
            return True, 'sent'
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode('utf-8', errors='replace')
        except Exception:
            err_body = str(e)
        logger.warning("ZeptoMail HTTPError %s: %s", e.code, err_body[:200])
        return False, f'Email service returned {e.code}'
    except Exception as exc:
        logger.warning("ZeptoMail send failed: %s", exc)
        return False, 'Email service unavailable'


def _send_welcome_email(user):
    """Fire off a welcome email when a user completes registration."""
    email = (user.email or '').strip()
    if not email:
        return
    name = user.get_full_name() or user.username

    html_body = f"""
    <div style="font-family: 'Bai Jamjuree', 'Inter', system-ui, sans-serif; background:#05060B; padding:32px; color:#F2F4F8;">
      <div style="max-width:520px; margin:0 auto; background:#0B0D14; border:1px solid rgba(255,255,255,0.08); border-radius:20px; padding:32px 28px;">
        <div style="display:inline-flex; align-items:center; gap:8px; margin-bottom:16px;">
          <div style="width:32px; height:32px; border-radius:8px; background:linear-gradient(135deg,#7CFFB2,#38E1FF);"></div>
          <span style="font-weight:700; color:#F2F4F8; font-size:1.1rem;">MY-Card</span>
        </div>
        <h1 style="font-size:1.4rem; margin:0 0 12px; color:#F2F4F8;">Welcome, {name}! 🎉</h1>
        <p style="color:#A6ADBB; line-height:1.6; margin:0 0 20px;">
          Your MY-Card account is live. You can now build a stunning digital business card,
          share it via QR, print a physical version, and track who's engaging in real time.
        </p>
        <div style="text-align:center; margin: 24px 0;">
          <a href="https://mycard.dupno.com/dashboard/" style="display:inline-block; padding:12px 28px; background:linear-gradient(135deg,#7CFFB2,#38E1FF); color:#05060B; text-decoration:none; border-radius:99px; font-weight:700;">
            Build your first card →
          </a>
        </div>
        <div style="background:#12141C; border-radius:12px; padding:16px; margin: 20px 0;">
          <p style="margin:0 0 8px; color:#F2F4F8; font-weight:600;">What you can do next:</p>
          <ul style="margin:0; padding-left:20px; color:#A6ADBB; line-height:1.7;">
            <li>Pick a curated theme (14 designs, 10 premium)</li>
            <li>Add your socials, contact, and bio</li>
            <li>Share via QR, WhatsApp, or a printed physical card</li>
            <li>Track views, clicks, and lead form submissions</li>
          </ul>
        </div>
        <hr style="border:none; border-top:1px solid rgba(255,255,255,0.06); margin:24px 0;">
        <p style="color:#6B7280; font-size:0.75rem; margin:0;">
          Sent by MY-Card · Digital identity, done right.<br>
          Questions? Just reply to this email — a real person reads it.
        </p>
      </div>
    </div>
    """

    try:
        ok, msg = _send_zepto_html(
            to_email=email,
            to_name=name,
            subject='Welcome to MY-Card 🎉',
            html_body=html_body,
        )
        if ok:
            logger.info("Welcome email SENT to %s", email)
        else:
            logger.warning("Welcome email NOT sent to %s: %s", email, msg)
    except Exception as exc:
        logger.warning("Welcome email failed for %s: %s", email, exc)


def forgot_password(request):
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email_or_phone = form.cleaned_data['email_or_phone'].strip()
            from django.db.models import Q

            query = Q(email__iexact=email_or_phone)
            digits = re.sub(r'\D', '', email_or_phone.lstrip('+'))
            if digits:
                variants = {digits}
                stripped = digits.lstrip('0')
                if stripped:
                    variants.add(stripped)
                    variants.add('0' + stripped)
                for code, _label in COUNTRY_CHOICES:
                    if digits.startswith(code) and len(digits) > len(code):
                        rest = digits[len(code):]
                        variants.add(rest)
                        rest_stripped = rest.lstrip('0')
                        if rest_stripped:
                            variants.add(rest_stripped)
                            variants.add('0' + rest_stripped)
                            variants.add(code + rest_stripped)
                query |= Q(profile__phone_number__in=variants)

            user = User.objects.filter(query).distinct().first()

            # Rate limit: max PW_RESET_MAX_PER_DAY resets per user per rolling day
            if user and user.email:
                profile = getattr(user, 'profile', None)
                today = timezone.now().date()
                if profile and profile.password_reset_day == today and \
                        profile.password_reset_count >= settings.PW_RESET_MAX_PER_DAY:
                    form.add_error(None,
                        f"You've already requested a password reset {settings.PW_RESET_MAX_PER_DAY} times today. "
                        "Please try again tomorrow, or contact support if you're locked out.")
                else:
                    if profile:
                        if profile.password_reset_day != today:
                            profile.password_reset_day = today
                            profile.password_reset_count = 0
                        profile.password_reset_count += 1
                        profile.save(update_fields=['password_reset_day', 'password_reset_count'])
                    _start_password_reset_otp(request, user)
                    return redirect('verify_otp')

            elif user and not user.email:
                form.add_error(None, "This account has no email on file. Please contact support to reset your password.")
            else:
                form.add_error(None, "If this email or phone number exists in our system, we've sent a code.")
    else:
        form = ForgotPasswordForm()
    return render(request, 'cards/forgot_password.html', {'form': form})


def _start_password_reset_otp(request, user):
    """Generate + persist an OTP for this user, then email it. Sets up the session."""
    otp = _make_otp()
    profile = getattr(user, 'profile', None)
    if profile is None:
        return
    profile.otp = make_password(otp)
    profile.otp_expires_at = timezone.now() + timedelta(seconds=settings.PW_RESET_OTP_TTL_SECONDS)
    profile.otp_requested_at = timezone.now()
    profile.otp_attempts = 0
    profile.save(update_fields=['otp', 'otp_expires_at', 'otp_requested_at', 'otp_attempts'])

    if request.user.is_authenticated:
        logout(request)

    request.session['password_reset_user_id'] = user.id
    request.session['otp_pending'] = True
    request.session['otp_verified'] = False

    ok, _msg = _send_otp_email(to_email=user.email, to_name=user.get_full_name() or user.username, otp=otp)
    if not ok:
        # Still let the flow continue — user can see the code in server logs when debugging
        logger.warning("Failed to send OTP email to %s (user %s)", user.email, user.username)


def verify_otp(request):
    user_id = request.session.get('password_reset_user_id')
    if not user_id or not request.session.get('otp_pending'):
        return redirect('forgot_password')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        request.session.pop('password_reset_user_id', None)
        return redirect('forgot_password')

    profile = getattr(user, 'profile', None)
    if profile is None or not profile.otp:
        request.session.pop('otp_pending', None)
        return redirect('forgot_password')

    masked_email = _mask_email(user.email)
    resend_available_in = 0
    if profile.otp_requested_at:
        elapsed = (timezone.now() - profile.otp_requested_at).total_seconds()
        resend_available_in = max(0, int(settings.PW_RESET_OTP_RESEND_COOLDOWN - elapsed))

    if request.method == 'POST':
        # Resend flow
        if request.POST.get('resend') == '1':
            if resend_available_in > 0:
                messages.info(request, f'Please wait {resend_available_in}s before requesting a new code.')
            else:
                _start_password_reset_otp(request, user)
                messages.success(request, f'A new code has been sent to {masked_email}.')
            return redirect('verify_otp')

        # Verify flow
        entered = (request.POST.get('otp') or '').strip()
        entered = re.sub(r'\D', '', entered)[:6]

        if not entered or len(entered) != 6:
            messages.error(request, 'Enter the 6-digit code from your email.')
            return redirect('verify_otp')

        if profile.otp_expires_at and profile.otp_expires_at < timezone.now():
            messages.error(request, 'This code has expired. Request a new one.')
            profile.otp = ''
            profile.save(update_fields=['otp'])
            return redirect('verify_otp')

        if profile.otp_attempts >= settings.PW_RESET_OTP_MAX_ATTEMPTS:
            messages.error(request, 'Too many attempts. Request a new code.')
            profile.otp = ''
            profile.save(update_fields=['otp'])
            return redirect('verify_otp')

        if check_password(entered, profile.otp):
            profile.otp = ''
            profile.otp_expires_at = None
            profile.otp_attempts = 0
            profile.save(update_fields=['otp', 'otp_expires_at', 'otp_attempts'])
            request.session['otp_verified'] = True
            request.session.pop('otp_pending', None)
            return redirect('reset_password')
        else:
            profile.otp_attempts += 1
            profile.save(update_fields=['otp_attempts'])
            remaining = max(0, settings.PW_RESET_OTP_MAX_ATTEMPTS - profile.otp_attempts)
            messages.error(request, f'Incorrect code. {remaining} attempt(s) left.')
            return redirect('verify_otp')

    return render(request, 'cards/verify_otp.html', {
        'masked_email': masked_email,
        'resend_available_in': resend_available_in,
    })

def reset_password(request):
    user_id = request.session.get('password_reset_user_id')
    if not user_id:
        return redirect('forgot_password')

    # If email OTP is configured, block reset until the code has been verified
    if settings.FEATURE_EMAIL_OTP and not request.session.get('otp_verified'):
        return redirect('verify_otp')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        request.session.pop('password_reset_user_id', None)
        return redirect('forgot_password')

    if request.method == 'POST':
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            request.session.pop('password_reset_user_id', None)
            request.session.pop('otp_verified', None)
            request.session.pop('otp_pending', None)
            # Auto-login and send them straight to their dashboard
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
            messages.success(request, 'Your password has been reset. Welcome back!')
            return redirect('dashboard')
    else:
        form = SetPasswordForm(user)

    return render(request, 'cards/reset_password.html', {
        'form': form,
        # Passed to the template so a hidden username field can hint the
        # browser's credential manager to remember it against the right account
        'reset_username': user.username,
    })


# ============================================================================
# Sprint 3: Analytics + Lead capture + vCard + Wallet
# ============================================================================

@csrf_exempt
@require_POST
def track_interaction(request):
    """Lightweight AJAX tracker. Called by view_card JS on link taps."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)

    slug = payload.get('slug') or ''
    kind = payload.get('kind') or ''
    target = (payload.get('target') or '')[:120]

    allowed_kinds = {c[0] for c in CardInteraction.KIND_CHOICES}
    if kind not in allowed_kinds:
        return HttpResponse(status=400)

    try:
        card = Card.objects.get(slug=slug, is_active=True)
    except Card.DoesNotExist:
        return HttpResponse(status=404)

    # Ignore owner's own clicks so analytics reflect real traffic
    if request.user.is_authenticated and request.user == card.user:
        return HttpResponse(status=204)

    try:
        CardInteraction.objects.create(
            card=card,
            kind=kind,
            target=target,
            session_id=(request.session.session_key or '')[:64],
            referrer=request.META.get('HTTP_REFERER', '')[:255],
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
        )
    except Exception as exc:
        logger.warning("Track interaction failed for %s/%s: %s", slug, kind, exc)
        return HttpResponse(status=500)

    return HttpResponse(status=204)


@require_POST
def submit_lead(request, slug):
    """Public: visitor submits contact form on a card."""
    card = get_object_or_404(Card, slug=slug, is_active=True)

    name = (request.POST.get('name') or '').strip()[:150]
    email = (request.POST.get('email') or '').strip()[:254]
    phone = (request.POST.get('phone') or '').strip()[:30]
    message = (request.POST.get('message') or '').strip()

    if not name or (not email and not phone):
        messages.error(request, 'Please share your name and at least one contact detail.')
        return redirect('view_card', slug=slug)

    lead = LeadCapture.objects.create(
        card=card,
        name=name,
        email=email,
        phone=phone,
        message=message,
        utm_source=(request.POST.get('utm_source') or '')[:80],
    )

    # Track interaction
    try:
        CardInteraction.objects.create(
            card=card,
            kind=CardInteraction.KIND_LEAD,
            target='lead_form',
            session_id=(request.session.session_key or '')[:64],
        )
    except Exception:
        pass

    # Email the card owner (best-effort)
    try:
        owner_email = getattr(card.user, 'email', '') or ''
        if owner_email:
            subject = f"New lead from your MY-Card: {name}"
            body = (
                f"You just received a new lead through your card '{card.slug}'.\n\n"
                f"Name:    {name}\n"
                f"Email:   {email or '—'}\n"
                f"Phone:   {phone or '—'}\n"
                f"Message: {message or '—'}\n\n"
                f"Reply directly to this email or open your inbox: "
                f"{request.build_absolute_uri(reverse('leads_inbox'))}"
            )
            send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [owner_email],
                fail_silently=True,
                reply_to=[email] if email else None,
            )
    except Exception as exc:
        logger.warning("Lead email delivery failed: %s", exc)

    messages.success(request, 'Thanks — your message was delivered.')
    return redirect('view_card', slug=slug)


@login_required
def leads_inbox(request):
    """Card owner's inbox of all leads across their cards."""
    cards = Card.objects.filter(user=request.user)
    leads_qs = (
        LeadCapture.objects.filter(card__user=request.user)
        .select_related('card')
        .order_by('-created_at')
    )

    status_filter = request.GET.get('status') or ''
    if status_filter in {c[0] for c in LeadCapture.STATUS_CHOICES}:
        leads_qs = leads_qs.filter(status=status_filter)

    new_count = LeadCapture.objects.filter(card__user=request.user, status=LeadCapture.STATUS_NEW).count()

    return render(request, 'cards/leads_inbox.html', {
        'leads': leads_qs,
        'cards': cards,
        'status_filter': status_filter,
        'new_count': new_count,
        'status_choices': LeadCapture.STATUS_CHOICES,
    })


@login_required
@require_POST
def lead_update_status(request, lead_id):
    lead = get_object_or_404(LeadCapture, id=lead_id, card__user=request.user)
    new_status = request.POST.get('status') or ''
    if new_status in {c[0] for c in LeadCapture.STATUS_CHOICES}:
        lead.status = new_status
        lead.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Lead marked as {lead.get_status_display().lower()}.')
    return redirect('leads_inbox')


def physical_card(request, slug):
    """Printable ID-1 sized physical card (front + back) with QR.

    When the card is inactive we branch:
      - Owner: show the offline / reactivate screen (same one the digital
        view uses) so they know they need to pay before printing.
      - Anyone else: show the public 'card unavailable' screen.
    """
    card = get_object_or_404(Card, slug=slug)
    is_owner = request.user.is_authenticated and request.user == card.user
    is_admin = request.user.is_authenticated and request.user.is_superuser

    if not card.is_active and not is_admin:
        if is_owner:
            existing_request = UpgradeRequest.objects.filter(
                user=request.user,
                card=card,
                status=UpgradeRequest.STATUS_PENDING,
            ).first()
            return render(request, 'cards/card_inactive.html', {
                'card': card,
                'existing_request': existing_request,
                'is_owner': True,
                'yearly_price': _yearly_price_for(card.user),
                'reactivation_fee': _reactivation_fee_for(card),
                'total_due': _yearly_price_for(card.user) + _reactivation_fee_for(card),
                'context_source': 'physical',
            })
        return render(request, 'cards/card_inactive_public.html', {'card': card}, status=200)

    whatsapp_link = _normalize_whatsapp_link(card.card_data.get('whatsapp'))
    phone_digits, phone_display = _normalize_phone_number(card.card_data.get('phone'))
    phone_tel = f"+{phone_digits}" if phone_digits else ''

    # Pick top 3 social handles for the back (in a fixed priority order)
    social_priority = ['linkedin', 'instagram', 'twitter', 'facebook', 'youtube', 'github', 'tiktok']
    top_socials = []
    for key in social_priority:
        val = (card.card_data or {}).get(key)
        if val:
            top_socials.append({'net': key, 'url': val})
        if len(top_socials) == 3:
            break

    theme = None
    theme_slug = (card.card_data or {}).get('theme_slug')
    if theme_slug:
        theme = CardTheme.objects.filter(slug=theme_slug, is_active=True).first()

    return render(request, 'cards/physical_card.html', {
        'card': card,
        'whatsapp_link': whatsapp_link,
        'phone_display': phone_display,
        'phone_tel': phone_tel,
        'top_socials': top_socials,
        'theme': theme,
    })


def download_vcard(request, slug):
    """Serve a .vcf file so any contacts app can save the details."""
    card = get_object_or_404(Card, slug=slug, is_active=True)
    d = card.card_data or {}

    first = (d.get('firstName') or '').strip()
    last = (d.get('lastName') or '').strip()
    company = (d.get('company') or '').strip()
    title = (d.get('jobTitle') or '').strip()
    email = (d.get('email') or '').strip()
    website = (d.get('website') or '').strip()
    phone = (d.get('phone') or '').strip()
    address = (d.get('address') or '').strip()
    notes = (d.get('notes') or '').strip().replace('\n', '\\n')

    lines = ['BEGIN:VCARD', 'VERSION:3.0']
    if first or last:
        lines.append(f'N:{last};{first};;;')
        lines.append(f'FN:{(first + " " + last).strip()}')
    if company: lines.append(f'ORG:{company}')
    if title:   lines.append(f'TITLE:{title}')
    if phone:
        tel = phone if phone.startswith('+') else f'+{phone}'
        lines.append(f'TEL;TYPE=CELL:{tel}')
    if email:   lines.append(f'EMAIL;TYPE=INTERNET:{email}')
    if website: lines.append(f'URL:{website}')
    if address: lines.append(f'ADR:;;{address};;;;')
    if notes:   lines.append(f'NOTE:{notes}')
    lines.append('END:VCARD')

    # Track save unless owner
    if not (request.user.is_authenticated and request.user == card.user):
        try:
            CardInteraction.objects.create(
                card=card,
                kind=CardInteraction.KIND_SAVE,
                target='vcard',
                session_id=(request.session.session_key or '')[:64],
            )
        except Exception:
            pass

    filename = f'{(first or "contact")}-{(last or "card")}.vcf'.replace(' ', '_')
    response = HttpResponse('\n'.join(lines), content_type='text/vcard; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def card_analytics(request, slug):
    """Per-card analytics dashboard (owner only)."""
    card = get_object_or_404(Card, slug=slug, user=request.user)
    now = timezone.now()

    # Free users see 7 days; premium users see the full 90-day window.
    analytics_is_capped = not is_premium(request.user)
    window_days = 7 if analytics_is_capped else 90
    since = now - timedelta(days=window_days)

    qs = card.interactions.filter(created_at__gte=since)

    # Daily view sparkline for the window
    daily = {}
    for iv in qs.filter(kind=CardInteraction.KIND_VIEW):
        day = iv.created_at.date().isoformat()
        daily[day] = daily.get(day, 0) + 1

    # Fill zeros so the chart has continuous points
    sparkline_len = min(window_days, 30)
    sparkline = []
    for i in range(sparkline_len):
        d = (now - timedelta(days=sparkline_len - 1 - i)).date().isoformat()
        sparkline.append({'date': d, 'count': daily.get(d, 0)})

    # Top clicked targets
    top_clicks_qs = (
        qs.filter(kind=CardInteraction.KIND_CLICK)
        .values('target')
        .annotate(n=Count('id'))
        .order_by('-n')[:12]
    )
    top_clicks = list(top_clicks_qs)

    # Split clicks into "social platforms" vs "contact channels" for the
    # drill-down analytics panel.
    SOCIAL_TARGETS = {
        'facebook', 'instagram', 'linkedin', 'twitter', 'x', 'youtube',
        'tiktok', 'whatsapp', 'telegram', 'discord', 'twitch', 'pinterest',
        'snapchat', 'reddit', 'medium', 'github', 'behance', 'dribbble',
        'threads', 'mastodon',
    }
    CONTACT_TARGETS = {'email', 'phone', 'website', 'wa', 'sms'}

    social_clicks = []
    contact_clicks = []
    other_clicks = []
    for row in top_clicks:
        t = (row.get('target') or '').lower()
        if t in SOCIAL_TARGETS:
            social_clicks.append(row)
        elif t in CONTACT_TARGETS:
            contact_clicks.append(row)
        else:
            other_clicks.append(row)

    social_top = sorted(social_clicks, key=lambda r: -r['n'])[:6]
    social_total = sum(r['n'] for r in social_clicks) or 0
    for row in social_top:
        row['pct'] = round((row['n'] / social_total * 100), 1) if social_total else 0

    # Overall totals
    totals = {
        'views':  qs.filter(kind=CardInteraction.KIND_VIEW).count(),
        'clicks': qs.filter(kind=CardInteraction.KIND_CLICK).count(),
        'saves':  qs.filter(kind=CardInteraction.KIND_SAVE).count(),
        'leads':  qs.filter(kind=CardInteraction.KIND_LEAD).count(),
    }

    return render(request, 'cards/card_analytics.html', {
        'card': card,
        'sparkline_json': json.dumps(sparkline),
        'top_clicks': top_clicks,
        'social_top': social_top,
        'social_total': social_total,
        'contact_clicks': contact_clicks,
        'other_clicks': other_clicks,
        'totals': totals,
        'analytics_is_capped': analytics_is_capped,
        'analytics_window_days': window_days,
    })


# ============================================================================
# Sprint 4: Payments (Stripe + bKash) — checkout scaffolds behind env flags
# ============================================================================

PLANS = [
    dict(
        slug='free',
        name='Free',
        price_bdt=0,
        price_usd=1,
        cards=1,
        billing='12 months free, then ৳120 / year (international: $1/year + reactivation fee)',
        features=[
            '12 months free — no payment required',
            '1 personal card + auto-generated URL',
            'QR + shareable link',
            'Wallet pass + vCard',
            '7-day analytics',
            '5 leads / month',
            'Yearly renewal ৳120 (no reactivation penalty)',
            'International: $1 / year + reactivation charge',
        ],
        cta='Start free for 12 months',
        featured=False,
    ),
    dict(
        slug='pro',
        name='Pro',
        price_bdt=500,
        price_usd=5,
        cards=5,
        billing='৳500 / year — paid upfront, no free trial',
        features=[
            'Paid upfront — ৳500 / year (no free trial)',
            'Up to 5 cards',
            'Custom public URL',
            'All 14 themes + AI bio',
            'Full 90-day analytics',
            'Unlimited leads',
            'Zero watermark',
            'Priority support',
        ],
        cta='Upgrade to Pro — ৳500 / year',
        featured=True,
    ),
    dict(
        slug='lifetime',
        name='Lifetime',
        price_bdt=5000,
        price_usd=50,
        cards=5,
        billing='৳5000 one-time — no renewals, ever',
        features=[
            'One payment, forever access',
            'Up to 5 cards (personal or business)',
            'Every card stays online for life',
            'Custom public URL on each card',
            'All 14 themes + AI bio',
            'Full 90-day analytics',
            'Unlimited leads',
            'Zero watermark',
            'Priority support',
            'All future features included',
        ],
        cta='Buy Lifetime — ৳5000 once',
        featured=False,
    ),
]


def pricing(request):
    return render(request, 'cards/pricing.html', {
        'plans': PLANS,
        'feature_payments': settings.FEATURE_PAYMENTS,
    })


@login_required
@require_POST
def pricing_checkout(request, plan):
    """Initiate a checkout for the given plan slug.

    When Stripe/bKash are unconfigured we fall back to creating a manual
    upgrade request that the admin can approve — this keeps the flow
    working in dev without any external credentials.
    """
    valid_slugs = {p['slug'] for p in PLANS}
    if plan not in valid_slugs or plan == 'free':
        return redirect('pricing')

    plan_info = next(p for p in PLANS if p['slug'] == plan)
    country = (getattr(request.user.profile, 'phone_number', '') or '').lstrip('+')
    prefers_bdt = country.startswith('880') or country.startswith('0')
    amount = plan_info['price_bdt'] if prefers_bdt else plan_info['price_usd']
    currency = 'BDT' if prefers_bdt else 'USD'

    if settings.FEATURE_PAYMENTS and settings.STRIPE_SECRET_KEY and not prefers_bdt:
        # Stripe checkout would go here — deferred until keys provisioned.
        # For now we record a pending Payment and inform the user.
        Payment.objects.create(
            user=request.user,
            gateway=Payment.GATEWAY_STRIPE,
            amount=amount,
            currency=currency,
            status=Payment.STATUS_PENDING,
            raw_payload={'plan': plan},
        )
        messages.info(request, 'Stripe checkout is coming shortly — we saved your intent and will email you.')
        return redirect('dashboard')

    if settings.FEATURE_PAYMENTS and settings.BKASH_APP_KEY and prefers_bdt:
        Payment.objects.create(
            user=request.user,
            gateway=Payment.GATEWAY_BKASH,
            amount=amount,
            currency=currency,
            status=Payment.STATUS_PENDING,
            raw_payload={'plan': plan},
        )
        messages.info(request, 'bKash checkout is coming shortly — we saved your intent and will email you.')
        return redirect('dashboard')

    # Manual fallback: file an UpgradeRequest so the admin can approve
    UpgradeRequest.objects.create(
        user=request.user,
        card=None,
        requested_plan=f'plan:{plan}',
        message=f'Requested {plan_info["name"]} tier via the pricing page.',
    )
    Payment.objects.create(
        user=request.user,
        gateway=Payment.GATEWAY_MANUAL,
        amount=amount,
        currency=currency,
        status=Payment.STATUS_PENDING,
        raw_payload={'plan': plan},
    )
    messages.success(
        request,
        f'Thanks — your {plan_info["name"]} upgrade request was received. An admin will confirm shortly.',
    )
    return redirect('user_messages')


# ============================================================================
# Sprint 4: AI bio assistant — feature-flagged behind AI_PROVIDER env var
# ============================================================================

@login_required
@require_POST
def ai_bio(request):
    """Return AI-generated bio suggestions given a name / role / company.

    When AI_PROVIDER + AI_API_KEY are not configured we return a graceful
    503 so the UI can hide the button. When they are configured, we call
    the provider (Anthropic by default) and return three variants.
    """
    if not settings.FEATURE_AI:
        return JsonResponse(
            {'error': 'AI is not configured on this server yet.'},
            status=503,
        )

    # AI bio is a Pro-only feature.
    if not is_premium(request.user):
        return JsonResponse({
            'error': 'AI bio suggestions are a Pro feature. Upgrade to unlock.',
            'locked': True,
            'upgrade_url': reverse('pricing') + '?locked=ai_bio',
        }, status=402)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)

    first = (payload.get('firstName') or '').strip()[:100]
    last = (payload.get('lastName') or '').strip()[:100]
    role = (payload.get('jobTitle') or '').strip()[:120]
    company = (payload.get('company') or '').strip()[:120]

    if not (first or last or role):
        return JsonResponse({'error': 'Provide at least a name or role.'}, status=400)

    prompt = (
        "Write three distinct short professional bios (max 220 characters each) "
        f"for a digital business card. Name: {first} {last}. Role: {role or 'Not specified'}. "
        f"Company: {company or 'Independent'}. Return JSON with the shape "
        '{"bios": ["...", "...", "..."]} and nothing else.'
    )

    try:
        provider = settings.AI_PROVIDER.lower()
        if provider == 'anthropic':
            import urllib.request
            req = urllib.request.Request(
                'https://api.anthropic.com/v1/messages',
                data=json.dumps({
                    'model': settings.AI_MODEL,
                    'max_tokens': 512,
                    'messages': [{'role': 'user', 'content': prompt}],
                }).encode('utf-8'),
                headers={
                    'x-api-key': settings.AI_API_KEY,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            text = ''.join(block.get('text', '') for block in data.get('content', []))
        else:
            return JsonResponse({'error': f"Unsupported AI provider: {provider}"}, status=503)

        # Try to extract JSON, tolerate small formatting noise
        m = re.search(r'\{[\s\S]*\}', text)
        if not m:
            return JsonResponse({'bios': [text.strip()[:220]]})
        parsed = json.loads(m.group(0))
        bios = [str(b).strip()[:220] for b in parsed.get('bios', []) if str(b).strip()]
        return JsonResponse({'bios': bios[:3]})
    except Exception as exc:
        logger.warning("AI bio failed: %s", exc)
        return JsonResponse({'error': 'AI provider is unavailable right now.'}, status=502)


# ============================================================================
# Card lifecycle — trial expiry, reactivation, admin control
# ============================================================================

def _yearly_price_for(user) -> int:
    """Return the yearly-subscription price for `user` in BDT."""
    return (
        settings.CARD_YEARLY_PRICE_PRO
        if is_premium(user)
        else settings.CARD_YEARLY_PRICE_FREE
    )


def _reactivation_fee_for(card) -> int:
    """Reactivation fee is always ৳0 — international SaaS convention. To
    come back online after a lapse the owner just pays the yearly rate,
    same as a fresh subscription. Kept as a helper so templates can call
    it without knowing the policy."""
    return settings.CARD_REACTIVATION_FEE


@login_required
def reactivate_card(request, slug):
    """Card owner requests to bring an offline card back online.

    Payment is deferred (bKash integration lands later). For now we file
    an UpgradeRequest that the admin approves manually — same manual-fallback
    pattern used by pricing_checkout. The user also gets a notification
    once the admin marks it approved.
    """
    card = get_object_or_404(Card, slug=slug, user=request.user)

    yearly = _yearly_price_for(request.user)
    reactivation_fee = _reactivation_fee_for(card)
    total = yearly + reactivation_fee
    # `is_early_renewal` = card is still online; the owner is paying ahead
    # of the expiry date, so no reactivation fee applies.
    is_early_renewal = reactivation_fee == 0

    already_pending = UpgradeRequest.objects.filter(
        user=request.user,
        card=card,
        status=UpgradeRequest.STATUS_PENDING,
        requested_plan__startswith='reactivate:',
    ).first()

    if request.method == 'POST':
        if already_pending:
            messages.info(request, 'You already have a pending reactivation request.')
            return redirect('reactivate_card', slug=slug)

        note = (request.POST.get('note') or '').strip()[:2000]
        UpgradeRequest.objects.create(
            user=request.user,
            card=card,
            requested_plan=f'reactivate:card:{card.slug}',
            message=(
                f"Card reactivation request from {request.user.username}. "
                f"Card: {card.slug}. Yearly: {yearly} BDT + Reactivation fee: "
                f"{reactivation_fee} BDT = {total} BDT.\n\n"
                f"Note from user: {note or '—'}"
            ),
        )

        CardLifecycleLog.objects.create(
            card=card,
            action=CardLifecycleLog.ACTION_ADMIN_OVERRIDE,
            actor=CardLifecycleLog.ACTOR_USER,
            actor_user=request.user,
            notes=f"User filed reactivation request (total {total} BDT).",
        )

        messages.success(
            request,
            'Your reactivation request has been sent to the admin. '
            'You will get an inbox notification the moment it is approved.',
        )
        return redirect('reactivate_card', slug=slug)

    logs = card.lifecycle_logs.all()[:20]
    return render(request, 'cards/reactivate_card.html', {
        'card': card,
        'yearly_price': yearly,
        'reactivation_fee': reactivation_fee,
        'total_due': total,
        'is_premium_user': is_premium(request.user),
        'is_early_renewal': is_early_renewal,
        'already_pending': already_pending,
        'logs': logs,
    })


@login_required
def user_inbox(request):
    """Owner-facing inbox of platform notifications (card offline/online,
    renewal reminders, etc.)."""
    notifications = request.user.notifications.select_related('card').all()[:100]
    unread_count = request.user.notifications.filter(is_read=False).count()
    return render(request, 'cards/user_inbox.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    note = get_object_or_404(UserNotification, id=notification_id, user=request.user)
    if not note.is_read:
        note.is_read = True
        note.save(update_fields=['is_read'])

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.http import JsonResponse
        return JsonResponse({
            'ok': True,
            'id': note.id,
            'is_read': note.is_read,
            'action_url': note.action_url or '',
        })

    if note.action_url:
        return redirect(note.action_url)
    return redirect('user_inbox')


@user_passes_test(lambda u: u.is_superuser, login_url='/my-admin/login/')
def admin_lifecycle(request):
    """Admin control surface for card lifecycle — see every card's trial /
    paid-until / offline state and manually override any of them."""
    status_filter = (request.GET.get('status') or '').strip()

    cards_qs = (
        Card.objects
        .select_related('user', 'user__profile')
        .order_by('-updated_at')
    )
    if status_filter and status_filter in {c[0] for c in Card.LIFECYCLE_CHOICES}:
        cards_qs = cards_qs.filter(lifecycle_status=status_filter)

    logs = (
        CardLifecycleLog.objects
        .select_related('card', 'actor_user')
        .order_by('-created_at')[:50]
    )

    now = timezone.now()
    counts = {
        'total':          Card.objects.count(),
        'trial':          Card.objects.filter(lifecycle_status=Card.STATUS_TRIAL).count(),
        'active_paid':    Card.objects.filter(lifecycle_status=Card.STATUS_ACTIVE_PAID).count(),
        'expiring_soon':  Card.objects.filter(lifecycle_status=Card.STATUS_EXPIRING_SOON).count(),
        'expired':        Card.objects.filter(lifecycle_status=Card.STATUS_EXPIRED).count(),
        'admin_disabled': Card.objects.filter(lifecycle_status=Card.STATUS_ADMIN_DISABLED).count(),
    }

    return render(request, 'cards/admin_lifecycle.html', {
        'cards': cards_qs[:200],
        'logs': logs,
        'now': now,
        'counts': counts,
        'status_filter': status_filter,
        'status_choices': Card.LIFECYCLE_CHOICES,
    })


@user_passes_test(lambda u: u.is_superuser, login_url='/my-admin/login/')
@require_POST
def admin_lifecycle_action(request, slug, action):
    """Admin action on a specific card:
       - activate    → bring card online, mark active_paid until +1 year
       - deactivate  → take card offline, mark admin_disabled
       - extend      → push trial_ends_at forward by N days (form field 'days')
       - reset_trial → set trial_ends_at to now + 12 months
    """
    card = get_object_or_404(Card, slug=slug)
    now = timezone.now()
    note_extra = (request.POST.get('note') or '').strip()[:500]

    if action == 'activate':
        card.is_active = True
        card.lifecycle_status = Card.STATUS_ACTIVE_PAID
        card.deactivated_at = None
        card.deactivation_reason = ''
        card.last_warning_stage = 0
        # Bump the *user's* subscription_paid_until by 1 year — Q5: one
        # payment covers all cards under the owner.
        profile = getattr(card.user, 'profile', None)
        if profile:
            profile.subscription_paid_until = max(
                profile.subscription_paid_until or now,
                now,
            ) + timezone.timedelta(days=365)
            profile.save(update_fields=['subscription_paid_until'])
        card.save(update_fields=[
            'is_active', 'lifecycle_status', 'deactivated_at',
            'deactivation_reason', 'last_warning_stage',
        ])
        _log_admin(card, request.user, CardLifecycleLog.ACTION_REACTIVATED,
                   f"Admin marked reactivated. {note_extra}")
        _notify_user(card, UserNotification.KIND_CARD_ONLINE,
                     f"Your card '{card.slug}' is back online",
                     f"Admin has reactivated your card. It stays live until "
                     f"{profile.subscription_paid_until:%Y-%m-%d} if a paid period is active.")
        messages.success(request, 'Card reactivated and yearly period extended.')

    elif action == 'deactivate':
        card.is_active = False
        card.lifecycle_status = Card.STATUS_ADMIN_DISABLED
        card.deactivated_at = now
        card.deactivation_reason = 'admin_disabled'
        card.save(update_fields=[
            'is_active', 'lifecycle_status', 'deactivated_at', 'deactivation_reason',
        ])
        _log_admin(card, request.user, CardLifecycleLog.ACTION_ADMIN_OVERRIDE,
                   f"Admin manually deactivated. {note_extra}")
        _notify_user(card, UserNotification.KIND_CARD_OFFLINE,
                     f"Your card '{card.slug}' has been taken offline",
                     f"Admin has taken your card offline. Reason: {note_extra or 'unspecified'}. "
                     f"Contact support if you need clarification.")
        messages.success(request, 'Card deactivated.')

    elif action == 'extend':
        try:
            days = max(1, min(730, int(request.POST.get('days') or 30)))
        except ValueError:
            days = 30
        base = card.trial_ends_at or now
        card.trial_ends_at = max(base, now) + timezone.timedelta(days=days)
        card.last_warning_stage = 0
        if card.lifecycle_status == Card.STATUS_EXPIRING_SOON:
            card.lifecycle_status = Card.STATUS_TRIAL
        card.save(update_fields=['trial_ends_at', 'last_warning_stage', 'lifecycle_status'])
        _log_admin(card, request.user, CardLifecycleLog.ACTION_ADMIN_OVERRIDE,
                   f"Admin extended trial by {days} days. {note_extra}")
        messages.success(request, f'Trial extended by {days} days.')

    elif action == 'reset_trial':
        months = settings.CARD_TRIAL_MONTHS
        card.trial_ends_at = now + timezone.timedelta(days=months * 30)
        card.last_warning_stage = 0
        card.lifecycle_status = Card.STATUS_TRIAL
        card.is_active = True
        card.deactivated_at = None
        card.deactivation_reason = ''
        card.save(update_fields=[
            'trial_ends_at', 'last_warning_stage', 'lifecycle_status',
            'is_active', 'deactivated_at', 'deactivation_reason',
        ])
        _log_admin(card, request.user, CardLifecycleLog.ACTION_ADMIN_OVERRIDE,
                   f"Admin reset trial to {months} months. {note_extra}")
        messages.success(request, f'Trial reset to {months} months from now.')

    else:
        messages.error(request, f'Unknown lifecycle action: {action}')

    return redirect(request.META.get('HTTP_REFERER') or reverse('admin_lifecycle'))


def _log_admin(card, admin_user, action, notes):
    CardLifecycleLog.objects.create(
        card=card,
        action=action,
        actor=CardLifecycleLog.ACTOR_ADMIN,
        actor_user=admin_user,
        notes=notes,
    )


def _notify_user(card, kind, subject, body, action_url=''):
    UserNotification.objects.create(
        user=card.user,
        card=card,
        kind=kind,
        subject=subject,
        body=body,
        action_url=action_url,
    )


# ============================================================================
# bKash Recurring Payment — scaffolding
# ============================================================================
# These endpoints are wired but intentionally minimal: sandbox credentials
# haven't been provisioned yet, so the initiate view flashes an info
# message and the webhook view accepts + logs the payload without
# advancing any subscription state. Once BKASH_APP_KEY is set the real
# gateway.py client is called instead.
#
# URL layout:
#   POST /pay/bkash/initiate/  → owner clicks "Pay via bKash" from
#                                 reactivate / pricing / dashboard.
#   GET  /pay/bkash/return/    → bKash redirects the customer here
#                                 after wallet+OTP+PIN. We call the
#                                 Query API to confirm, then flip the
#                                 Payment row + Profile.subscription_
#                                 paid_until + card.lifecycle_status.
#   POST /pay/bkash/webhook/   → bKash pushes 4 notification types:
#                                 SUBSCRIPTION / PAYMENT / REFUND /
#                                 CANCEL. Verify signature, then apply.

def _bkash_ready() -> bool:
    return bool(getattr(settings, 'FEATURE_BKASH', False))


def _bkash_mock_mode() -> bool:
    """Mock mode kicks in when either BKASH_MODE=mock is set explicitly
    or the sandbox credentials haven't been provisioned yet. It lets us
    exercise the full customer journey (redirect, wallet, OTP, PIN,
    return, webhook) without a live bKash API — the app pretends to be
    bKash internally."""
    mode = (getattr(settings, 'BKASH_MODE', '') or '').lower()
    if mode == 'mock':
        return True
    if mode == 'live':
        return False
    return not bool(
        getattr(settings, 'BKASH_APP_KEY', '')
        and getattr(settings, 'BKASH_MERCHANT_SHORT_CODE', '')
    )


_BKASH_SANDBOX_WALLETS = {
    '01770618575': '12121',
    '01929918378': '12121',
    '01770618576': '21212',
    '01877722345': '13131',
    '01619777282': '21212',
    '01619777283': '13131',
}
_BKASH_SANDBOX_OTP = '123456'


@login_required
def bkash_initiate(request, plan=None):
    """Kick off a bKash subscription for the current user.

    Accepts either a POST body with a `plan` field (from a form on the
    pricing page) OR a GET request that carries the plan in the URL
    path — used by the anonymous flow: landing → register?next=… →
    /pay/bkash/start/<plan>/. Both call the same code path."""
    from .gateways import bkash
    from datetime import date

    plan = (plan or request.POST.get('plan') or request.GET.get('plan') or '').strip()
    is_pro_upgrade = plan == 'pro'
    is_lifetime = plan == 'lifetime'
    if is_lifetime:
        amount = settings.CARD_LIFETIME_PRICE
    elif is_pro_upgrade:
        amount = settings.CARD_YEARLY_PRICE_PRO
    else:
        amount = _yearly_price_for(request.user)
    yearly = amount  # kept for downstream naming compatibility

    subscription_request_id = bkash.new_subscription_request_id()
    start_date = date.today()
    # Lifetime is a one-shot payment — set a far-future expiry so the
    # subscription doesn't recur. Yearly/pro still uses the normal
    # 2-year window that bKash caps subscriptions at.
    if is_lifetime:
        expiry_date = bkash.suggested_expiry_date(start=start_date, years=2)
    else:
        expiry_date = bkash.suggested_expiry_date(start=start_date, years=2)

    Payment.objects.create(
        user=request.user,
        gateway=Payment.GATEWAY_BKASH,
        amount=amount,
        currency='BDT',
        status=Payment.STATUS_PENDING,
        bkash_subscription_request_id=subscription_request_id,
        raw_payload={'plan': plan, 'amount': amount, 'lifetime': is_lifetime},
    )

    # --- MOCK MODE ---
    # No live bKash credentials on file → send the user to our own
    # simulator page that behaves like bKash's consent screen. Uses
    # the six sandbox wallet numbers + OTP '123456'.
    if _bkash_mock_mode():
        return redirect('bkash_mock_checkout', request_id=subscription_request_id)

    # --- LIVE / SANDBOX MODE ---
    try:
        client = bkash.BkashClient()
        result = client.create_subscription(
            subscription_request_id=subscription_request_id,
            amount=yearly,
            start_date=start_date,
            expiry_date=expiry_date,
            frequency='CALENDAR_YEAR',
            subscription_type='WITH_PAYMENT',
            first_payment_amount=yearly,
            subscription_reference=f'{request.user.username[:70]}',
        )
    except bkash.BkashError as exc:
        logger.warning("bKash create_subscription failed: %s", exc)
        messages.error(request, 'Could not reach bKash right now. Please try again in a minute.')
        return redirect('pricing')

    redirect_url = result.get('redirectURL')
    if not redirect_url:
        messages.error(request, 'bKash did not return a redirect URL.')
        return redirect('pricing')

    return redirect(redirect_url)


@login_required
def bkash_mock_checkout(request, request_id):
    """Local simulator of the bKash secure payment page.

    Behaves like the real bKash intent screen: shows subscription
    details, prompts for wallet / OTP / PIN using the sandbox test
    values, and on success grants the subscription + redirects to the
    return page just like production would.
    """
    payment = get_object_or_404(
        Payment,
        bkash_subscription_request_id=request_id,
        user=request.user,
    )

    error = None

    if request.method == 'POST':
        step = request.POST.get('step') or ''
        wallet = (request.POST.get('wallet') or '').strip()
        otp    = (request.POST.get('otp') or '').strip()
        pin    = (request.POST.get('pin') or '').strip()

        if step == 'consent':
            # Nothing to validate — just move to wallet entry via GET
            return redirect(request.path + '?step=wallet')

        if step == 'wallet':
            if wallet not in _BKASH_SANDBOX_WALLETS:
                error = 'Unknown wallet. Try one of the sandbox test numbers.'
            else:
                return redirect(f'{request.path}?step=otp&wallet={wallet}')

        if step == 'otp':
            if otp != _BKASH_SANDBOX_OTP:
                error = 'Invalid OTP. The sandbox OTP is 123456.'
            else:
                return redirect(f'{request.path}?step=pin&wallet={wallet}')

        if step == 'pin':
            expected_pin = _BKASH_SANDBOX_WALLETS.get(wallet)
            if not expected_pin or pin != expected_pin:
                error = 'Incorrect PIN for that wallet.'
            else:
                # Success: mark payment succeeded + grant subscription
                payment.bkash_subscription_id = f'MOCK-{payment.pk}'
                payment.bkash_payment_id = f'MOCKPAY-{payment.pk}'
                payment.bkash_trx_id = f'MOCKTRX-{payment.pk}'
                payment.bkash_payer_msisdn = wallet
                payment.status = Payment.STATUS_SUCCESS
                payment.raw_payload = {
                    **(payment.raw_payload or {}),
                    'mock': True,
                    'mock_wallet': wallet,
                }
                payment.save()
                _grant_subscription(payment)
                return redirect(
                    f"{reverse('bkash_return')}?subscriptionRequestId={payment.bkash_subscription_request_id}&status=SUCCEEDED"
                )

    step = request.GET.get('step') or 'consent'
    wallet = request.GET.get('wallet') or ''

    from datetime import date, timedelta
    today = date.today()
    return render(request, 'cards/bkash_mock_checkout.html', {
        'payment': payment,
        'step': step,
        'wallet': wallet,
        'error': error,
        'sandbox_wallets': _BKASH_SANDBOX_WALLETS,
        'sandbox_otp': _BKASH_SANDBOX_OTP,
        'today_iso': today.strftime('%Y-%m-%d'),
        'next_year_iso': (today + timedelta(days=365)).strftime('%Y-%m-%d'),
        'expiry_iso': (today + timedelta(days=730)).strftime('%Y-%m-%d'),
    })


def bkash_return(request):
    """Landing page after bKash sends the customer back."""
    subscription_request_id = (request.GET.get('subscriptionRequestId') or '').strip()

    payment = (
        Payment.objects
        .filter(bkash_subscription_request_id=subscription_request_id)
        .first()
        if subscription_request_id else None
    )

    context = {
        'payment': payment,
        'subscription_request_id': subscription_request_id,
        'bkash_ready': _bkash_ready(),
    }

    # If mock mode is active, `status` comes from the mock checkout query
    # string. Otherwise (real sandbox / live), call the mandatory Query
    # API — bKash Note-3 says the merchant must not rely solely on the
    # webhook arriving on time.
    if _bkash_mock_mode():
        context['status'] = (request.GET.get('status') or 'SUCCEEDED').upper()
        context['is_mock'] = True
    elif _bkash_ready() and payment:
        from .gateways import bkash
        try:
            info = bkash.BkashClient().query_by_request_id(subscription_request_id)
            _apply_subscription_query(payment, info)
            context['status'] = info.get('status')
        except bkash.BkashError as exc:
            logger.warning("bKash query on return failed: %s", exc)
            context['status'] = 'unknown'
    else:
        context['status'] = 'pending'

    return render(request, 'cards/bkash_return.html', context)


@csrf_exempt
@require_POST
def bkash_webhook(request):
    """Endpoint bKash POSTs to for SUBSCRIPTION / PAYMENT / REFUND / CANCEL.

    Signature verification is enforced when BKASH_WEBHOOK_KEY is set.
    Body is stored on the Payment row for auditability.
    """
    from .gateways import bkash

    signature = request.headers.get('X-Signature', '') or request.headers.get('signature', '')
    event_type = request.headers.get('Type', '') or request.headers.get('type', '')

    if _bkash_ready() and settings.BKASH_WEBHOOK_KEY:
        if not bkash.verify_signature(payload=request.body, signature_header=signature):
            logger.warning("bKash webhook signature mismatch (type=%s)", event_type)
            return HttpResponse(status=401)

    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)

    logger.info("bKash webhook received: type=%s data=%s", event_type, data)

    subscription_request_id = (data.get('subscriptionRequestId') or '').strip()
    payment = (
        Payment.objects
        .filter(bkash_subscription_request_id=subscription_request_id)
        .first()
        if subscription_request_id else None
    )

    if payment:
        _apply_webhook_event(payment, event_type.upper(), data)
    else:
        logger.warning("bKash webhook for unknown subscription_request_id=%s", subscription_request_id)

    return HttpResponse(status=200)


def _apply_subscription_query(payment: Payment, info: dict):
    """Update a Payment row from a query API response (query_by_request_id)."""
    payment.bkash_subscription_id = str(info.get('id') or payment.bkash_subscription_id)
    payment.bkash_payer_msisdn = info.get('payer') or payment.bkash_payer_msisdn
    if info.get('nextPaymentDate'):
        payment.bkash_next_payment_date = info['nextPaymentDate']
    if info.get('expiryDate'):
        payment.bkash_expiry_date = info['expiryDate']

    status = (info.get('status') or '').upper()
    if status == 'SUCCEEDED':
        payment.status = Payment.STATUS_SUCCESS
        _grant_subscription(payment)
    elif status == 'FAILED':
        payment.status = Payment.STATUS_FAILED
    elif status == 'CANCELLED':
        payment.status = Payment.STATUS_REFUNDED

    payment.raw_payload = {**(payment.raw_payload or {}), 'last_query': info}
    payment.save()


def _apply_webhook_event(payment: Payment, event_type: str, data: dict):
    payment.raw_payload = {
        **(payment.raw_payload or {}),
        f'webhook_{event_type.lower()}': data,
    }

    if event_type == 'SUBSCRIPTION':
        status = (data.get('subscriptionStatus') or '').upper()
        payment.bkash_subscription_id = str(data.get('subscriptionId') or payment.bkash_subscription_id)
        if status == 'SUCCEEDED':
            payment.status = Payment.STATUS_SUCCESS
            _grant_subscription(payment)
        elif status == 'FAILED':
            payment.status = Payment.STATUS_FAILED
        elif status == 'CANCELLED':
            payment.status = Payment.STATUS_REFUNDED
            _mark_subscription_cancelled(payment)

    elif event_type == 'PAYMENT':
        payment.bkash_payment_id = str(data.get('paymentId') or payment.bkash_payment_id)
        payment.bkash_trx_id = data.get('trxId') or payment.bkash_trx_id
        if data.get('nextPaymentDate'):
            payment.bkash_next_payment_date = data['nextPaymentDate']
        status = (data.get('paymentStatus') or '').upper()
        if status in {'SUCCEEDED_PAYMENT', 'RE_SUCCEEDED_PAYMENT'}:
            payment.status = Payment.STATUS_SUCCESS
            _grant_subscription(payment)

    elif event_type == 'REFUND':
        payment.status = Payment.STATUS_REFUNDED

    payment.save()


def _grant_subscription(payment: Payment):
    """Grant paid access on the payer's account.

    - Yearly / Pro: extend `Profile.subscription_paid_until` by 1 year.
    - Lifetime:     set `subscription_paid_until` to year 9999 (effective
                    permanent) and bump `Profile.card_limit` to the
                    lifetime allowance so the user unlocks 5 cards.

    Then reactivate every card the payer owns."""
    from django.utils import timezone
    from datetime import datetime, timezone as _tz

    profile = getattr(payment.user, 'profile', None)
    if not profile:
        return

    now = timezone.now()
    is_lifetime = bool((payment.raw_payload or {}).get('lifetime'))

    if is_lifetime:
        # 9999-01-01 UTC — the card lifecycle tick will never mark this
        # as expiring. Cheaper than a boolean field.
        profile.subscription_paid_until = datetime(9999, 1, 1, tzinfo=_tz.utc)
        # Unlock the 5-card allowance so create_card lets them add more.
        if profile.card_limit < settings.CARD_LIFETIME_CARD_LIMIT:
            profile.card_limit = settings.CARD_LIFETIME_CARD_LIMIT
        profile.save(update_fields=['subscription_paid_until', 'card_limit'])
    else:
        base = profile.subscription_paid_until or now
        # Yearly renewal never shortens an already-longer paid window.
        if base.year < 9999:
            profile.subscription_paid_until = max(base, now) + timezone.timedelta(days=365)
            profile.save(update_fields=['subscription_paid_until'])

    # Reactivate every card owned by the payer that had gone offline.
    Card.objects.filter(
        user=payment.user,
        is_active=False,
    ).update(
        is_active=True,
        lifecycle_status=Card.STATUS_ACTIVE_PAID,
        deactivated_at=None,
        deactivation_reason='',
        last_warning_stage=0,
    )
    Card.objects.filter(
        user=payment.user,
        is_active=True,
    ).update(
        lifecycle_status=Card.STATUS_ACTIVE_PAID,
        last_warning_stage=0,
    )

    for card in Card.objects.filter(user=payment.user):
        CardLifecycleLog.objects.create(
            card=card,
            action=CardLifecycleLog.ACTION_RENEWED,
            actor=CardLifecycleLog.ACTOR_USER,
            actor_user=payment.user,
            notes=(
                f'bKash lifetime success. All cards online forever.'
                if is_lifetime else
                f'bKash subscription success. Paid until {profile.subscription_paid_until:%Y-%m-%d}.'
            ),
        )

    receipt_url = reverse('payment_receipt', args=[payment.pk])
    if is_lifetime:
        subject = 'Lifetime plan activated — every card online forever'
        body = (
            f'Thank you for buying the Lifetime plan. All of your cards '
            f'stay online for the lifetime of the account, and you can '
            f'add up to {settings.CARD_LIFETIME_CARD_LIMIT} cards. '
            f'View / print your receipt: {receipt_url}'
        )
    else:
        subject = 'Payment received — every card active for another year'
        body = (
            f'Your yearly subscription is live until '
            f'{profile.subscription_paid_until:%Y-%m-%d}. '
            f'All of your cards are online. '
            f'View / print your receipt: {receipt_url}'
        )
    UserNotification.objects.create(
        user=payment.user,
        kind=UserNotification.KIND_PAYMENT_RECEIVED,
        subject=subject,
        body=body,
        action_url=receipt_url,
    )


def bkash_journey_mockup(request):
    """6-step Merchant User Journey for the bKash S-2 milestone.

    Public URL — not linked from any nav — so bKash reviewers can open
    it directly to validate the customer flow."""
    return render(request, 'cards/bkash_journey_mockup.html')


def _invoice_number(payment: Payment) -> str:
    return f"MYC-INV-{payment.created_at:%Y%m%d}-{payment.pk:06d}"


@login_required
def payment_history(request):
    payments = (
        Payment.objects
        .filter(user=request.user)
        .order_by('-created_at')
    )
    profile = getattr(request.user, 'profile', None)
    return render(request, 'cards/payment_history.html', {
        'active': 'billing',
        'payments': [
            {
                'obj': p,
                'invoice': _invoice_number(p),
            }
            for p in payments
        ],
        'paid_until': profile.subscription_paid_until if profile else None,
    })


@login_required
def payment_receipt(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id, user=request.user)
    return render(request, 'cards/payment_receipt.html', {
        'payment': payment,
        'invoice': _invoice_number(payment),
        'is_admin_view': False,
    })


def _staff_required(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
def admin_payments(request):
    if not _staff_required(request.user):
        return redirect('dashboard')

    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()
    gateway = (request.GET.get('gateway') or '').strip()

    qs = Payment.objects.select_related('user', 'plan').order_by('-created_at')
    if q:
        qs = qs.filter(
            Q(user__username__icontains=q) |
            Q(user__email__icontains=q) |
            Q(bkash_payer_msisdn__icontains=q) |
            Q(bkash_trx_id__icontains=q) |
            Q(bkash_subscription_request_id__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    if gateway:
        qs = qs.filter(gateway=gateway)

    payments = list(qs[:500])
    total_success = sum(
        (p.amount for p in payments if p.status == Payment.STATUS_SUCCESS),
        Decimal('0'),
    )

    rows = [{'obj': p, 'invoice': _invoice_number(p)} for p in payments]

    return render(request, 'cards/admin_payments.html', {
        'active': 'payments',
        'payments': rows,
        'total_success': total_success,
        'q': q,
        'status': status,
        'gateway': gateway,
        'status_choices': Payment.STATUS_CHOICES,
        'gateway_choices': Payment.GATEWAY_CHOICES,
    })


@login_required
def admin_payment_receipt(request, payment_id):
    if not _staff_required(request.user):
        return redirect('dashboard')
    payment = get_object_or_404(Payment, pk=payment_id)
    return render(request, 'cards/payment_receipt.html', {
        'payment': payment,
        'invoice': _invoice_number(payment),
        'is_admin_view': True,
    })


def _mark_subscription_cancelled(payment: Payment):
    """Q6(A): mark cancelled immediately but keep cards active until the
    paid_until date. The lifecycle tick will take them offline naturally
    when that date passes."""
    UserNotification.objects.create(
        user=payment.user,
        kind=UserNotification.KIND_ADMIN_ACTION,
        subject='Subscription cancelled',
        body=(
            'Your bKash subscription has been cancelled. Your cards stay '
            'online until the current paid period ends; after that they '
            'will go offline unless you resubscribe.'
        ),
    )
