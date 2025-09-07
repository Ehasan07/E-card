from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
import uuid

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
    unique_slug = models.SlugField(unique=True, null=True, blank=True) # Temporary for migration
    text_color = models.CharField(max_length=20, default='#000000')
    created_at = models.DateTimeField(auto_now_add=True)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('view_card', args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.user.username)
        
        # Set text color based on background
        dark_backgrounds = ['Graphite', 'Deep Ocean']
        if any(dark_bg in self.card_data.get('background_style', '') for dark_bg in dark_backgrounds):
            self.text_color = '#FFFFFF'
        else:
            self.text_color = '#333333'

        super().save(*args, **kwargs) # Save once to get an ID for new objects

        # Generate QR code if it doesn't exist or needs update
        # NOTE: This logic runs after save. We need to call save again if qr_code is updated.
        # To avoid recursion, we check if the qr_code field is already set.
        
        from django.urls import reverse
        from django.conf import settings
        import qrcode
        from io import BytesIO
        from django.core.files import File

        # Build the absolute URL. We can't use a request object here.
        # This assumes the site is served over HTTPS.
        domain = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'
        qr_code_url = f"https://{domain}{self.get_absolute_url()}?qr=1"

        # Create the QR code image
        qr_img = qrcode.make(qr_code_url, box_size=10, border=4)
        
        buffer = BytesIO()
        qr_img.save(buffer, format='PNG')
        file_name = f'qr_code_{self.slug}.png'
        
        # Check if the generated QR is different from the existing one
        # to prevent infinite save loop
        if not self.qr_code or self.qr_code.name != file_name:
             self.qr_code.save(file_name, File(buffer), save=False) # save=False to not trigger another save
             super().save(update_fields=['qr_code']) # Use update_fields to avoid recursion


    def __str__(self):
        first_name = self.card_data.get('firstName', '')
        last_name = self.card_data.get('lastName', '')
        return f"{first_name} {last_name}".strip() or f"Card {self.id}"