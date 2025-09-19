from django import forms
from django.contrib.auth.models import User

from .models import Card, Profile

import re


COUNTRY_CHOICES = [
    ("1", "🇺🇸 +1"),
    ("7", "🇷🇺 +7"),
    ("20", "🇪🇬 +20"),
    ("27", "🇿🇦 +27"),
    ("30", "🇬🇷 +30"),
    ("31", "🇳🇱 +31"),
    ("32", "🇧🇪 +32"),
    ("33", "🇫🇷 +33"),
    ("34", "🇪🇸 +34"),
    ("39", "🇮🇹 +39"),
    ("44", "🇬🇧 +44"),
    ("49", "🇩🇪 +49"),
    ("52", "🇲🇽 +52"),
    ("55", "🇧🇷 +55"),
    ("60", "🇲🇾 +60"),
    ("61", "🇦🇺 +61"),
    ("62", "🇮🇩 +62"),
    ("63", "🇵🇭 +63"),
    ("64", "🇳🇿 +64"),
    ("65", "🇸🇬 +65"),
    ("66", "🇹🇭 +66"),
    ("81", "🇯🇵 +81"),
    ("82", "🇰🇷 +82"),
    ("84", "🇻🇳 +84"),
    ("86", "🇨🇳 +86"),
    ("90", "🇹🇷 +90"),
    ("91", "🇮🇳 +91"),
    ("92", "🇵🇰 +92"),
    ("94", "🇱🇰 +94"),
    ("213", "🇩🇿 +213"),
    ("234", "🇳🇬 +234"),
    ("254", "🇰🇪 +254"),
    ("256", "🇺🇬 +256"),
    ("352", "🇱🇺 +352"),
    ("380", "🇺🇦 +380"),
    ("420", "🇨🇿 +420"),
    ("507", "🇵🇦 +507"),
    ("593", "🇪🇨 +593"),
    ("598", "🇺🇾 +598"),
    ("880", "🇧🇩 +880"),
    ("971", "🇦🇪 +971"),
    ("972", "🇮🇱 +972"),
    ("974", "🇶🇦 +974"),
    ("975", "🇧🇹 +975"),
    ("976", "🇲🇳 +976"),
    ("977", "🇳🇵 +977"),
]

class CardForm(forms.ModelForm):
    firstName = forms.CharField(max_length=100, required=True)
    lastName = forms.CharField(max_length=100, required=True)
    company = forms.CharField(max_length=100, required=False)
    jobTitle = forms.CharField(max_length=100, required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=20, required=False, widget=forms.HiddenInput())
    phone_country = forms.CharField(required=False, widget=forms.HiddenInput())
    phone_number = forms.CharField(required=False, max_length=20)
    address = forms.CharField(max_length=255, required=False)
    birthday = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.DateInput(attrs={"type": "date"})
    )
    website = forms.URLField(required=False)
    notes = forms.CharField(widget=forms.Textarea, required=False)
    facebook = forms.URLField(required=False)
    whatsapp = forms.CharField(required=False, widget=forms.HiddenInput())
    whatsapp_country = forms.CharField(required=False, widget=forms.HiddenInput())
    whatsapp_number = forms.CharField(required=False, max_length=20)
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
        self.initial_whatsapp = ''
        self.initial_phone = ''
        existing_whatsapp = self.initial.get('whatsapp') or ''
        existing_phone = self.initial.get('phone') or ''
        if not existing_whatsapp and self.instance.pk:
            existing_whatsapp = self.instance.card_data.get('whatsapp', '')
        if not existing_phone and self.instance.pk:
            existing_phone = self.instance.card_data.get('phone', '')

        if existing_whatsapp:
            self.initial_whatsapp = existing_whatsapp.strip()
            parsed_number = self.initial_whatsapp
            if parsed_number.startswith('https://wa.me/'):
                parsed_number = parsed_number[len('https://wa.me/'):]
            elif parsed_number.startswith('http://wa.me/'):
                parsed_number = parsed_number[len('http://wa.me/'):]
            parsed_number = parsed_number.lstrip('+')
            digits_only = re.sub(r'\D', '', parsed_number)
            self.initial['whatsapp'] = self.initial_whatsapp
            if digits_only:
                match_code = ''
                for code, _label in sorted(COUNTRY_CHOICES, key=lambda item: len(item[0]), reverse=True):
                    if digits_only.startswith(code):
                        match_code = code
                        break
                if match_code:
                    self.initial.setdefault('whatsapp_country', match_code)
                    self.initial.setdefault('whatsapp_number', digits_only[len(match_code):])
                else:
                    self.initial.setdefault('whatsapp_number', digits_only)

        if existing_phone:
            self.initial_phone = str(existing_phone).strip()
            digits_only_phone = re.sub(r'\D', '', self.initial_phone.lstrip('+'))
            if digits_only_phone:
                match_code = ''
                for code, _label in sorted(COUNTRY_CHOICES, key=lambda item: len(item[0]), reverse=True):
                    if digits_only_phone.startswith(code):
                        match_code = code
                        break
                if match_code:
                    remainder = digits_only_phone[len(match_code):]
                    self.initial.setdefault('phone_country', match_code)
                    self.initial.setdefault('phone_number', remainder)
                    digits_full = match_code + remainder
                else:
                    default_code = '880'
                    self.initial.setdefault('phone_country', default_code)
                    self.initial.setdefault('phone_number', digits_only_phone)
                    digits_full = digits_only_phone
                    if not digits_full.startswith(default_code):
                        digits_full = default_code + digits_only_phone
                self.initial_phone = digits_full
                self.initial['phone'] = digits_full
            else:
                self.initial['phone'] = ''
        else:
            self.initial['phone'] = self.initial.get('phone', '')

        self.initial.setdefault('phone_country', self.initial.get('phone_country') or '880')
        self.initial.setdefault('whatsapp_country', self.initial.get('whatsapp_country') or '880')
        
        select_classes = 'h-12 w-24 bg-white border border-gray-200 rounded-l-xl px-3 text-sm text-gray-700 focus:border-pink-400 focus:ring-2 focus:ring-pink-200 hover:bg-pink-50 transition'
        number_classes = 'h-12 flex-1 rounded-r-xl border border-l-0 border-gray-200 bg-white text-gray-700 text-sm px-4 focus:border-pink-400 focus:ring-2 focus:ring-pink-200 hover:bg-pink-50 transition'
        self.fields['whatsapp_country'].widget.attrs.update({'class': select_classes})
        self.fields['whatsapp_number'].widget.attrs.update({'class': number_classes, 'placeholder': 'WhatsApp number'})
        self.fields['whatsapp_number'].widget.attrs.setdefault('inputmode', 'numeric')
        self.fields['whatsapp_number'].widget.attrs.setdefault('pattern', '[0-9]*')

        self.fields['phone_country'].widget.attrs.update({'class': select_classes})
        self.fields['phone_number'].widget.attrs.update({'class': number_classes, 'placeholder': 'Phone number'})
        self.fields['phone_number'].widget.attrs.setdefault('inputmode', 'numeric')
        self.fields['phone_number'].widget.attrs.setdefault('pattern', '[0-9]*')
        self.fields['notes'].widget.attrs.setdefault('rows', 4)

    def clean(self):
        cleaned_data = super().clean()
        country_code = cleaned_data.get('whatsapp_country', '').strip()
        number_raw = cleaned_data.get('whatsapp_number', '') or ''
        number_digits = re.sub(r'\D', '', number_raw)

        if number_raw and not number_digits:
            self.add_error('whatsapp_number', 'Enter digits only for the WhatsApp number.')

        if number_digits and not country_code:
            self.add_error('whatsapp_country', 'Select a country code.')

        if number_digits and country_code:
            cleaned_data['whatsapp'] = f"https://wa.me/{country_code}{number_digits}"
        elif self.initial_whatsapp and not number_digits and not country_code:
            cleaned_data['whatsapp'] = self.initial_whatsapp
        else:
            cleaned_data['whatsapp'] = ''

        phone_country = cleaned_data.get('phone_country', '').strip()
        phone_raw = cleaned_data.get('phone_number', '') or ''
        phone_digits = re.sub(r'\D', '', phone_raw)

        if phone_raw and not phone_digits:
            self.add_error('phone_number', 'Enter digits only for the phone number.')

        if phone_digits and not phone_country:
            self.add_error('phone_country', 'Select a country code for the phone number.')

        if phone_digits and phone_country:
            cleaned_data['phone'] = f"{phone_country}{phone_digits}"
        elif self.initial_phone and 'phone_country' not in self.data and 'phone_number' not in self.data:
            cleaned_data['phone'] = self.initial_phone
        else:
            cleaned_data['phone'] = phone_digits

        return cleaned_data

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
