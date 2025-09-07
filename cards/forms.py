from django import forms
from .models import Card, Profile
from django.contrib.auth.models import User

class CardForm(forms.ModelForm):
    firstName = forms.CharField(max_length=100, required=True)
    lastName = forms.CharField(max_length=100, required=True)
    company = forms.CharField(max_length=100, required=False)
    jobTitle = forms.CharField(max_length=100, required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=20, required=False)
    address = forms.CharField(max_length=255, required=False)
    birthday = forms.CharField(max_length=100, required=False)
    website = forms.URLField(required=False)
    notes = forms.CharField(widget=forms.Textarea, required=False)
    facebook = forms.URLField(required=False)
    whatsapp = forms.URLField(required=False)
    youtube = forms.URLField(required=False)
    instagram = forms.URLField(required=False)
    twitter = forms.URLField(required=False)
    linkedin = forms.URLField(required=False)
    background_style = forms.CharField(max_length=255, required=False)

    class Meta:
        model = Card
        fields = ['avatar']

class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    class Meta:
        model = User
        fields = ('username', 'password', 'email')

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('phone_number',)

class OTPForm(forms.Form):
    otp = forms.CharField(max_length=6, widget=forms.TextInput(attrs={'placeholder': 'Enter 6-digit OTP'}))