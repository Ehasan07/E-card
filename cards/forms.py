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
    birthday = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.DateInput(attrs={"type": "date"})
    )
    website = forms.URLField(required=False)
    notes = forms.CharField(widget=forms.Textarea, required=False)
    facebook = forms.URLField(required=False)
    whatsapp = forms.URLField(required=False)
    youtube = forms.URLField(required=False)
    instagram = forms.URLField(required=False)
    twitter = forms.URLField(required=False)
    linkedin = forms.URLField(required=False)
    background_style = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.HiddenInput()
    )

    class Meta:
        model = Card
        fields = ['avatar']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_classes = 'w-full px-4 py-3 rounded-lg border border-gray-200 focus:border-pink-400 focus:ring-2 focus:ring-pink-200 transition'
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.FileInput):
                widget.attrs.setdefault('class', 'w-full text-sm text-gray-700 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-pink-100 file:text-pink-600 hover:file:bg-pink-200 cursor-pointer')
            else:
                existing = widget.attrs.get('class', '')
                widget.attrs['class'] = f"{existing} {base_classes}".strip()
        self.fields['notes'].widget.attrs.setdefault('rows', 4)

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
