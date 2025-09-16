from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
import logging
import re


logger = logging.getLogger(__name__)

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20, unique=True)
    otp = models.CharField(max_length=6, blank=True, null=True)

    def __str__(self):
        return self.user.username

class Card(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    card_data = models.JSONField(default=dict)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)
    slug = models.SlugField(max_length=150, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    text_color = models.CharField(max_length=20, default='#000000')
    created_at = models.DateTimeField(auto_now_add=True)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('view_card', args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.user.username)
        
        # Set text color based on background luminance
        def _hex_to_rgb(hex_color: str):
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 3:
                hex_color = ''.join(ch * 2 for ch in hex_color)
            try:
                return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            except ValueError:
                return None

        def _find_rgb(background_value: str):
            if not background_value:
                return None
            match = re.search(r'#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})', background_value)
            if match:
                return _hex_to_rgb(match.group(0))
            rgb_match = re.search(r'rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)', background_value)
            if rgb_match:
                return tuple(int(rgb_match.group(i)) for i in range(1, 4))
            return None

        background_value = self.card_data.get('background_style', '')
        rgb = _find_rgb(background_value)
        if rgb:
            luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
            self.text_color = '#FFFFFF' if luminance < 0.55 else '#333333'
        else:
            self.text_color = '#333333'

        super().save(*args, **kwargs) # Save once to get an ID for new objects

        # Generate QR code if it doesn't exist or needs update
        # NOTE: This logic runs after save. We need to call save again if qr_code is updated.
        # To avoid recursion, we check if the qr_code field is already set.
        
        try:
            from django.conf import settings
            import qrcode
            from io import BytesIO
            from django.core.files import File

            domain = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'
            qr_code_url = f"https://{domain}{self.get_absolute_url()}?qr=1"

            qr_img = qrcode.make(qr_code_url, box_size=10, border=4)
            buffer = BytesIO()
            qr_img.save(buffer, format='PNG')
            file_name = f'qr_code_{self.slug}.png'

            if not self.qr_code or self.qr_code.name != file_name:
                self.qr_code.save(file_name, File(buffer), save=False) # save=False to not trigger another save
                super().save(update_fields=['qr_code']) # Use update_fields to avoid recursion
        except Exception as exc:
            logger.warning("Skipping QR generation for card %s: %s", self.pk or self.slug, exc)


    def __str__(self):
        first_name = self.card_data.get('firstName', '')
        last_name = self.card_data.get('lastName', '')
        return f"{first_name} {last_name}".strip() or f"Card {self.id}"
