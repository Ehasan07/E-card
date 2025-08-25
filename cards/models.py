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
    unique_slug = models.SlugField(unique=True)
    text_color = models.CharField(max_length=20, default='#000000')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.unique_slug:
            # Use first name and last name from card_data for slug
            first_name = self.card_data.get('firstName', '')
            last_name = self.card_data.get('lastName', '')
            full_name = f"{first_name} {last_name}".strip()
            if full_name:
                self.unique_slug = slugify(full_name) + "-" + str(uuid.uuid4())[:8]
            else:
                self.unique_slug = str(uuid.uuid4())[:8] # Fallback if no name is provided
        super().save(*args, **kwargs)

    def __str__(self):
        first_name = self.card_data.get('firstName', '')
        last_name = self.card_data.get('lastName', '')
        return f"{first_name} {last_name}".strip() or f"Card {self.id}"