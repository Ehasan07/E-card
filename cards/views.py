from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from .forms import UserForm, ProfileForm, OTPForm
from .models import Card, Profile
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse_lazy
import json
import markdown
import os
import qrcode
from io import BytesIO
from django.core.files import File
from django.urls import reverse
import random

def index(request):
    return render(request, 'cards/index.html')

def register(request):
    if request.method == 'POST':
        user_form = UserForm(request.POST)
        profile_form = ProfileForm(request.POST)
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
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
    cards = Card.objects.filter(user=request.user)
    gradients = [
        'linear-gradient(to right, #ff8177 0%, #ff867a 0%, #ff8c7f 21%, #f99185 52%, #cf556c 78%, #b12a5b 100%)',
        'linear-gradient(to right, #c2e9fb, #a1c4fd)',
        'linear-gradient(to right, #d4fc79, #96e6a1)',
        'linear-gradient(to right, #fbc2eb, #a6c1ee)'
    ]
    
    # Assign a gradient and animation delay to each card
    for i, card in enumerate(cards):
        card.background_gradient = gradients[i % len(gradients)]
        card.animation_delay = f"{i * 0.1}s"

    return render(request, 'cards/dashboard.html', {'cards': cards})

@login_required
def create_card(request):
    if request.method == 'POST':
        card_data = {
            'firstName': request.POST.get('firstName'),
            'lastName': request.POST.get('lastName'),
            'company': request.POST.get('company'),
            'jobTitle': request.POST.get('jobTitle'),
            'email': request.POST.get('email'),
            'phone': request.POST.get('phone'),
            'address': request.POST.get('address'),
            'birthday': request.POST.get('birthday'),
            'website': request.POST.get('website'),
            'notes': request.POST.get('notes'),
            'facebook': request.POST.get('facebook'),
            'whatsapp': request.POST.get('whatsapp'),
            'youtube': request.POST.get('youtube'),
            'instagram': request.POST.get('instagram'),
            'twitter': request.POST.get('twitter'),
            'linkedin': request.POST.get('linkedin'),
            'background_style': request.POST.get('background_style'),
        }
        card = Card(user=request.user, card_data=card_data)
        dark_backgrounds = ['Graphite', 'Deep Ocean']
        if any(dark_bg in card_data['background_style'] for dark_bg in dark_backgrounds):
            card.text_color = '#FFFFFF'
        else:
            card.text_color = '#333333'

        if 'avatar' in request.FILES:
            card.avatar = request.FILES['avatar']
        card.save()

        # Generate QR code
        qr_code_data = request.build_absolute_uri(reverse('view_card', args=[card.unique_slug]))
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_code_data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        filename = f'qr_code_{card.unique_slug}.png'
        card.qr_code.save(filename, File(buffer), save=True)

        return redirect('view_card', unique_slug=card.unique_slug)
    return render(request, 'cards/create_card.html')

@login_required
def edit_card(request, unique_slug):
    card = get_object_or_404(Card, unique_slug=unique_slug, user=request.user)
    if request.method == 'POST':
        card.card_data = {
            'firstName': request.POST.get('firstName'),
            'lastName': request.POST.get('lastName'),
            'company': request.POST.get('company'),
            'jobTitle': request.POST.get('jobTitle'),
            'email': request.POST.get('email'),
            'phone': request.POST.get('phone'),
            'address': request.POST.get('address'),
            'birthday': request.POST.get('birthday'),
            'website': request.POST.get('website'),
            'notes': request.POST.get('notes'),
            'facebook': request.POST.get('facebook'),
            'whatsapp': request.POST.get('whatsapp'),
            'youtube': request.POST.get('youtube'),
            'instagram': request.POST.get('instagram'),
            'twitter': request.POST.get('twitter'),
            'linkedin': request.POST.get('linkedin'),
            'background_style': request.POST.get('background_style'),
        }
        dark_backgrounds = ['Graphite', 'Deep Ocean']
        if any(dark_bg in card_data['background_style'] for dark_bg in dark_backgrounds):
            card.text_color = '#FFFFFF'
        else:
            card.text_color = '#333333'

        if 'avatar' in request.FILES:
            card.avatar = request.FILES['avatar']
        card.save()

        # Generate QR code
        qr_code_data = request.build_absolute_uri(reverse('view_card', args=[card.unique_slug]))
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_code_data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        filename = f'qr_code_{card.unique_slug}.png'
        card.qr_code.save(filename, File(buffer), save=True)

        return redirect('view_card', unique_slug=card.unique_slug)
    return render(request, 'cards/create_card.html', {'card': card})

def view_card(request, unique_slug):
    card = Card.objects.get(unique_slug=unique_slug)
    return render(request, 'cards/view_card.html', {'card': card})

def admin_login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None and user.is_superuser:
                login(request, user)
                return redirect('admin_dashboard')
            else:
                # If user is not a superuser or authentication fails
                form.add_error(None, "Invalid login credentials or you are not an administrator.")
        
    else:
        form = AuthenticationForm()
    return render(request, 'cards/admin_login.html', {'form': form})

@user_passes_test(lambda u: u.is_superuser)
def admin_dashboard(request):
    total_users = User.objects.count()
    total_cards = Card.objects.count()
    all_cards = Card.objects.all()
    return render(request, 'cards/admin_dashboard.html', {
        'total_users': total_users,
        'total_cards': total_cards,
        'all_cards': all_cards
    })

@user_passes_test(lambda u: u.is_superuser)
def delete_card_admin(request, unique_slug):
    card = Card.objects.get(unique_slug=unique_slug)
    card.delete()
    return redirect('admin_dashboard')

def documentation_view(request):
    readme_path = os.path.join(settings.BASE_DIR, 'README.md')
    with open(readme_path, 'r', encoding='utf-8') as f:
        markdown_content = f.read()
    html_content = markdown.markdown(markdown_content)
    return render(request, 'cards/documentation.html', {'html_content': html_content})

def password_reset_request_otp(request):
    if request.method == 'POST':
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email)
                profile = Profile.objects.get(user=user)

                # Generate OTP
                otp = str(random.randint(100000, 999999))
                profile.otp = otp
                profile.save()

                # Send OTP via email
                subject = 'Your Password Reset OTP'
                html_message = render_to_string('cards/password_reset_otp_email.html', {'otp': otp, 'user': user})
                plain_message = strip_tags(html_message)
                from_email = settings.EMAIL_HOST_USER if hasattr(settings, 'EMAIL_HOST_USER') else 'webmaster@localhost'
                send_mail(subject, plain_message, from_email, [email], html_message=html_message)

                # TODO: Implement SMS sending for OTP if phone_number is available
                # For now, we'll just proceed with email

                request.session['password_reset_user_id'] = user.id
                return redirect('password_reset_verify_otp')
            except (User.DoesNotExist, Profile.DoesNotExist):
                form.add_error('email', 'No user found with that email address.')
    else:
        form = PasswordResetForm()
    return render(request, 'cards/password_reset_form.html', {'form': form})

def password_reset_verify_otp(request):
    if 'password_reset_user_id' not in request.session:
        return redirect('password_reset_request_otp')

    user = get_object_or_404(User, id=request.session['password_reset_user_id'])
    profile = get_object_or_404(Profile, user=user)

    if request.method == 'POST':
        form = OTPForm(request.POST)
        if form.is_valid():
            if form.cleaned_data['otp'] == profile.otp:
                # OTP is valid, clear it and redirect to password reset confirm
                profile.otp = None
                profile.save()
                # Django's built-in password reset confirm view expects uidb64 and token
                # We need to generate these manually or use a custom password reset flow
                # For simplicity, we'll redirect to a custom password set view for now
                # In a real application, you'd use Django's built-in password reset mechanism
                # after successful OTP verification.
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
