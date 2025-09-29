import csv
import json
import re
import zipfile
import random
from io import BytesIO, StringIO

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count
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
from .models import (
    Card,
    Profile,
    DEFAULT_CARD_LIMIT,
    UpgradeRequest,
    SubscriptionPlan,
    Subscription,
    Feedback,
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
from django.http import HttpResponse
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from django.views.decorators.http import require_POST

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


def _normalize_whatsapp_link(value: str) -> str:
    if not value:
        return ''
    value = value.strip()
    if value.startswith('http://') or value.startswith('https://'):
        return value
    digits = re.sub(r'\D', '', value.lstrip('+'))
    return f"https://wa.me/{digits}" if digits else ''


def _normalize_phone_number(value: str, default_code: str = '880') -> tuple[str, str]:
    if not value:
        return '', ''
    digits = re.sub(r'\D', '', str(value).lstrip('+'))
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
    return render(request, 'cards/index.html', {
        'feedback_form': FeedbackForm()
    })


@require_POST
def submit_feedback(request):
    form = FeedbackForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, 'Thanks for sharing your feedback — the team will take a look.')
        return redirect(f"{reverse('index')}#feedback")
    else:
        messages.error(request, 'Please fix the highlighted details before sending your feedback.')
    return render(request, 'cards/index.html', {
        'feedback_form': form,
        'scroll_to_feedback': True,
    }, status=400)


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

                login(request, user)
                messages.success(request, 'Welcome aboard! Your studio is ready for its first card.')
                return redirect('dashboard')
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
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'cards/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard(request):
    cards_qs = Card.objects.filter(user=request.user).order_by('-created_at')
    cards = list(cards_qs)

    profile = getattr(request.user, 'profile', None)
    card_limit = getattr(profile, 'card_limit', DEFAULT_CARD_LIMIT)
    total_cards = len(cards)
    remaining_cards = max(card_limit - total_cards, 0)

    context = {
        'cards': cards,
        'card_limit': card_limit,
        'cards_remaining': remaining_cards,
        'at_card_limit': remaining_cards == 0,
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


def _handle_card_creation(request, card_type: str):
    profile = getattr(request.user, 'profile', None)
    card_limit = getattr(profile, 'card_limit', DEFAULT_CARD_LIMIT)
    total_cards = Card.objects.filter(user=request.user).count()
    remaining_cards = card_limit - total_cards

    variant = CARD_VARIANT_CONFIG.get(card_type, CARD_VARIANT_CONFIG[Card.TYPE_PERSONAL])
    form_class = CARD_FORM_BY_TYPE.get(card_type, CardForm)

    if remaining_cards <= 0:
        first_card = Card.objects.filter(user=request.user).order_by('created_at').first()
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

    if request.method == 'POST':
        form = form_class(request.POST, request.FILES, instance=card)
        if form.is_valid():
            _apply_card_form_updates(card, form)
            form.save() # This re-triggers the model's save method, updating QR code etc.

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
    }
    return render(request, 'cards/create_card.html', context)


@user_passes_test(lambda u: u.is_superuser, login_url='/my-admin/login/')
def admin_edit_card(request, slug):
    card = get_object_or_404(Card, slug=slug)

    form_class = CARD_FORM_BY_TYPE.get(card.card_type, CardForm)
    builder_variant = CARD_VARIANT_CONFIG.get(card.card_type, CARD_VARIANT_CONFIG[Card.TYPE_PERSONAL])

    if request.method == 'POST':
        form = form_class(request.POST, request.FILES, instance=card)
        if form.is_valid():
            _apply_card_form_updates(card, form)
            form.save()
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
            context = {
                'card': card,
                'existing_request': existing_request,
                'is_owner': True,
            }
            return render(request, 'cards/card_inactive.html', context)
        return render(request, 'cards/card_inactive_public.html', {'card': card}, status=200)

    visited_cards = request.session.get('visited_cards', [])
    if card.is_active and card.slug not in visited_cards:
        visited_cards.append(card.slug)
        request.session['visited_cards'] = visited_cards
        current_count = card.card_data.get('unique_views') or 0
        try:
            current_count = int(current_count)
        except (TypeError, ValueError):
            current_count = 0
        card.card_data['unique_views'] = current_count + 1
        card.save(update_fields=['card_data'])

    profile_views = card.card_data.get('unique_views') or 0
    try:
        profile_views = int(profile_views)
    except (TypeError, ValueError):
        profile_views = 0

    # The QR code URL is now generated in the model, but we pass it for consistency
    # Note: The model-generated QR already has ?qr=1.
    qr_code_url = request.build_absolute_uri(card.get_absolute_url()) + "?qr=1"

    whatsapp_link = _normalize_whatsapp_link(card.card_data.get('whatsapp'))
    phone_digits, phone_display = _normalize_phone_number(card.card_data.get('phone'))
    phone_tel = f"+{phone_digits}" if phone_digits else ''

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
        .annotate(card_count=Count('card'))
        .order_by('-date_joined')
    )
    cards = Card.objects.select_related('user', 'user__profile').order_by('-created_at')
    feedback_entries = list(Feedback.objects.all())

    user_records = []
    for user in users:
        profile = getattr(user, 'profile', None)
        card_limit = getattr(profile, 'card_limit', DEFAULT_CARD_LIMIT)
        card_limit_form = AdminCardLimitForm(initial={'card_limit': card_limit}, auto_id=f'id_user_{user.id}_%s')
        primary_card_slug = (
            user.card_set.order_by('created_at').values_list('slug', flat=True).first()
        )
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
            'card_limit_form': card_limit_form,
            'primary_card_slug': primary_card_slug,
        })

    pending_requests = UpgradeRequest.objects.filter(status=UpgradeRequest.STATUS_PENDING)

    context = {
        'total_users': len(user_records),
        'total_cards': cards.count(),
        'all_cards': cards,
        'all_users': user_records,
        'pending_request_count': pending_requests.count(),
        'feedback_entries': feedback_entries,
        'feedback_count': len(feedback_entries),
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

def forgot_password(request):
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email_or_phone = form.cleaned_data['email_or_phone']
            from django.db.models import Q
            user = User.objects.filter(Q(email__iexact=email_or_phone) | Q(profile__phone_number=email_or_phone)).distinct().first()

            if user:
                request.session['password_reset_user_id'] = user.id
                if request.user.is_authenticated:
                    logout(request)
                return redirect('reset_password')
            else:
                form.add_error(None, "If this email or phone number exists in our system, you will be able to reset your password.")
    else:
        form = ForgotPasswordForm()
    return render(request, 'cards/forgot_password.html', {'form': form})

def reset_password(request):
    user_id = request.session.get('password_reset_user_id')
    if not user_id:
        return redirect('forgot_password')

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
            messages.success(request, 'Your password has been reset successfully. Please log in with your new password.')
            return redirect('login')
    else:
        form = SetPasswordForm(user)

    return render(request, 'cards/reset_password.html', {'form': form})
