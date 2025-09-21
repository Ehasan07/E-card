import csv
import json
import re
import zipfile
import random
from io import BytesIO, StringIO

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from .forms import UserForm, ProfileForm, ForgotPasswordForm, CardForm, COUNTRY_CHOICES
from .models import Card, Profile
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

from datetime import timedelta

from openpyxl import Workbook


OTP_EXPIRY_MINUTES = 5
OTP_RATE_LIMIT_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
OTP_EMAIL_FROM = 'dss@dupno.com'


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
    return render(request, 'cards/index.html')


def register(request):
    if request.method == 'POST':
        user_form = UserForm(request.POST)
        profile_form = ProfileForm(request.POST)
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save(commit=False)
            user.set_password(user.password)
            user.save()
            profile = profile_form.save(commit=False)
            profile.user = user
            profile.save()
            login(request, user)
            return redirect('dashboard')
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
    cards = Card.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'cards/dashboard.html', {'cards': cards})

@login_required
def create_card(request):
    # Check if user already has an active card
    existing_card = Card.objects.filter(user=request.user, is_active=True).first()
    if existing_card:
        messages.info(request, 'You already have a card. We opened the editor for you.')
        return redirect('edit_card', slug=existing_card.slug)

    if request.method == 'POST':
        form = CardForm(request.POST, request.FILES)
        if form.is_valid():
            excluded_keys = {'avatar', 'logo', 'whatsapp_country', 'whatsapp_number', 'phone_country', 'phone_number'}
            card_data = {key: value for key, value in form.cleaned_data.items() if key not in excluded_keys}
            
            card = form.save(commit=False)
            card.user = request.user
            card.card_data = card_data
            card.save() # This will also trigger the QR code generation in the model's save method

            return redirect(card.get_absolute_url())
    else:
        form = CardForm()
    
    # The create_card.html now needs to be a proper form template
    return render(request, 'cards/create_card.html', {'form': form})

@login_required
def edit_card(request, slug):
    card = get_object_or_404(Card, slug=slug, user=request.user, is_active=True)

    if request.method == 'POST':
        form = CardForm(request.POST, request.FILES, instance=card)
        if form.is_valid():
            _apply_card_form_updates(card, form)
            form.save() # This re-triggers the model's save method, updating QR code etc.

            return redirect(card.get_absolute_url())
    else:
        # Pre-populate form with existing data
        initial_data = _card_initial_data(card)
        form = CardForm(instance=card, initial=initial_data)

    return render(request, 'cards/create_card.html', {'form': form, 'card': card})


@user_passes_test(lambda u: u.is_superuser, login_url='/my-admin/login/')
def admin_edit_card(request, slug):
    card = get_object_or_404(Card, slug=slug)

    if request.method == 'POST':
        form = CardForm(request.POST, request.FILES, instance=card)
        if form.is_valid():
            _apply_card_form_updates(card, form)
            form.save()
            return redirect('admin_dashboard')
    else:
        initial_data = _card_initial_data(card)
        form = CardForm(instance=card, initial=initial_data)

    return render(request, 'cards/create_card.html', {'form': form, 'card': card, 'admin_edit': True})

def view_card(request, slug):
    card = get_object_or_404(Card, slug=slug, is_active=True)
    is_owner = request.user.is_authenticated and request.user == card.user
    is_admin = request.user.is_authenticated and request.user.is_superuser
    from_qr = request.GET.get('qr') == '1'

    visited_cards = request.session.get('visited_cards', [])
    if card.slug not in visited_cards:
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
    users = User.objects.select_related('profile').order_by('-date_joined')
    cards = Card.objects.select_related('user', 'user__profile').order_by('-created_at')
    user_records = []
    for user in users:
        user_records.append({
            'id': user.id,
            'name': (user.get_full_name() or '').strip() or user.username,
            'email': user.email or '',
            'phone': _get_user_phone(user),
            'registered': user.date_joined,
            'is_active': user.is_active,
            'status_label': 'Active' if user.is_active else 'Inactive',
        })

    context = {
        'total_users': len(user_records),
        'total_cards': cards.count(),
        'all_cards': cards,
        'all_users': user_records,
    }
    return render(request, 'cards/admin_dashboard.html', context)

@user_passes_test(lambda u: u.is_superuser)
def delete_card_admin(request, slug):
    card = get_object_or_404(Card, slug=slug)
    card.delete()
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
