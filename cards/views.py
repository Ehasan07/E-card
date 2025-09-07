from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from .forms import UserForm, ProfileForm, OTPForm, CardForm
from .models import Card, Profile
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse
import markdown
import os
from django.contrib import messages


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
    return redirect('register')

@login_required
def dashboard(request):
    cards = Card.objects.filter(user=request.user, is_active=True)
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
            card_data = {key: value for key, value in form.cleaned_data.items() if key not in ['avatar']}
            
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
            # Update card_data from form
            card.card_data.update({key: value for key, value in form.cleaned_data.items() if key not in ['avatar']})
            
            # The form's save() will handle the avatar update
            form.save() # This re-triggers the model's save method, updating QR code etc.

            return redirect(card.get_absolute_url())
    else:
        # Pre-populate form with existing data
        initial_data = card.card_data.copy()
        form = CardForm(instance=card, initial=initial_data)

    return render(request, 'cards/create_card.html', {'form': form, 'card': card})

def view_card(request, slug):
    card = get_object_or_404(Card, slug=slug, is_active=True)
    is_owner = request.user.is_authenticated and request.user == card.user
    from_qr = request.GET.get('qr') == '1'
    
    # The QR code URL is now generated in the model, but we pass it for consistency
    # Note: The model-generated QR already has ?qr=1.
    qr_code_url = request.build_absolute_uri(card.get_absolute_url()) + "?qr=1"

    context = {
        'card': card,
        'is_owner': is_owner,
        'from_qr': from_qr,
        'qr_code_url': qr_code_url,
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

@user_passes_test(lambda u: u.is_superuser)
def admin_dashboard(request):
    total_users = User.objects.count()
    total_cards = Card.objects.count()
    all_cards = Card.objects.all().order_by('-created_at')
    context = {
        'total_users': total_users,
        'total_cards': total_cards,
        'all_cards': all_cards
    }
    return render(request, 'cards/admin_dashboard.html', context)

@user_passes_test(lambda u: u.is_superuser)
def delete_card_admin(request, slug):
    card = get_object_or_404(Card, slug=slug)
    card.delete()
    return redirect('admin_dashboard')

def documentation_view(request):
    readme_path = os.path.join(settings.BASE_DIR, 'README.md')
    try:
        with open(readme_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        html_content = markdown.markdown(markdown_content)
    except FileNotFoundError:
        html_content = "<h1>README.md not found</h1>"
    return render(request, 'cards/documentation.html', {'html_content': html_content})

# The password reset views remain complex and may need further review,
# but are left as-is to focus on the primary goals.
def password_reset_request_otp(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email)
                profile, _ = Profile.objects.get_or_create(user=user)

                import random
                otp = str(random.randint(100000, 999999))
                profile.otp = otp
                profile.save()

                subject = 'Your Password Reset OTP'
                html_message = render_to_string('cards/password_reset_otp_email.html', {'otp': otp, 'user': user})
                plain_message = strip_tags(html_message)
                from_email = settings.DEFAULT_FROM_EMAIL
                send_mail(subject, plain_message, from_email, [email], html_message=html_message)

                request.session['password_reset_user_id'] = user.id
                return redirect('password_reset_verify_otp')
            except User.DoesNotExist:
                form.add_error('email', 'No user found with that email address.')
    else:
        form = PasswordResetForm()
    return render(request, 'cards/password_reset_form.html', {'form': form})

def password_reset_verify_otp(request):
    user_id = request.session.get('password_reset_user_id')
    if not user_id:
        return redirect('password_reset_request_otp')

    user = get_object_or_404(User, id=user_id)
    profile = get_object_or_404(Profile, user=user)

    if request.method == 'POST':
        form = OTPForm(request.POST)
        if form.is_valid():
            if form.cleaned_data['otp'] == profile.otp:
                profile.otp = None
                profile.save()
                
                from django.contrib.auth.tokens import default_token_generator
                from django.utils.http import urlsafe_base64_encode
                from django.utils.encoding import force_bytes
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                
                return redirect('password_reset_confirm', uidb64=uid, token=token)
            else:
                form.add_error('otp', 'Invalid OTP.')
    else:
        form = OTPForm()
    return render(request, 'cards/password_reset_otp_form.html', {'form': form})