from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.utils import timezone
import logging
import re


logger = logging.getLogger(__name__)

DEFAULT_CARD_LIMIT = 1


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20, unique=True)
    otp = models.CharField(max_length=128, blank=True, null=True)
    otp_expires_at = models.DateTimeField(blank=True, null=True)
    otp_requested_at = models.DateTimeField(blank=True, null=True)
    otp_attempts = models.PositiveSmallIntegerField(default=0)
    card_limit = models.PositiveIntegerField(default=DEFAULT_CARD_LIMIT)

    def __str__(self):
        return self.user.username

    def ensure_minimum_limit(self):
        """Guarantee the profile always has at least one allowed card."""
        if self.card_limit < DEFAULT_CARD_LIMIT:
            self.card_limit = DEFAULT_CARD_LIMIT
            self.save(update_fields=["card_limit"])

class Card(models.Model):
    TYPE_PERSONAL = 'personal'
    TYPE_BUSINESS = 'business'
    TYPE_CHOICES = [
        (TYPE_PERSONAL, 'Personal'),
        (TYPE_BUSINESS, 'Business'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    card_data = models.JSONField(default=dict)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True, null=True)
    slug = models.SlugField(max_length=150, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    text_color = models.CharField(max_length=20, default='#FFFFFF')
    card_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_PERSONAL)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('view_card', args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            base_value = self.card_data.get('firstName') or self.user.get_full_name() or self.user.username or 'card'
            base_slug = slugify(base_value) or 'card'
            slug_candidate = base_slug
            index = 2
            while Card.objects.exclude(pk=self.pk).filter(slug=slug_candidate).exists():
                slug_candidate = f"{base_slug}-{index}"
                index += 1
            self.slug = slug_candidate
        
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

        background_value = self.card_data.get('background_style')
        if not background_value:
            self.card_data['background_style'] = '#000000'
            background_value = '#000000'
        rgb = _find_rgb(background_value)
        if rgb:
            luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
            self.text_color = '#FFFFFF' if luminance < 0.55 else '#333333'
        else:
            self.text_color = '#FFFFFF'

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


class SubscriptionPlan(models.Model):
    BILLING_MONTHLY = 'monthly'
    BILLING_YEARLY = 'yearly'
    BILLING_CHOICES = [
        (BILLING_MONTHLY, 'Monthly'),
        (BILLING_YEARLY, 'Yearly'),
    ]

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CHOICES, default=BILLING_MONTHLY)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['price']

    def __str__(self):
        return f"{self.name} ({self.get_billing_cycle_display()})"


class Subscription(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACTIVE = 'active'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    current_period_end = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} → {self.plan} ({self.get_status_display()})"


class UpgradeRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='upgrade_requests')
    card = models.ForeignKey('Card', on_delete=models.SET_NULL, null=True, blank=True, related_name='upgrade_requests')
    requested_plan = models.CharField(max_length=120, default='monthly_plan')
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(blank=True, null=True)
    handled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='handled_upgrade_requests')
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def mark(self, status: str, admin_user: User | None = None, notes: str | None = None):
        if status not in dict(self.STATUS_CHOICES):
            raise ValueError('Unsupported status value')
        self.status = status
        self.responded_at = timezone.now()
        if admin_user:
            self.handled_by = admin_user
        if notes is not None:
            self.admin_notes = notes
        self.save(update_fields=['status', 'responded_at', 'handled_by', 'admin_notes'])

    def __str__(self):
        return f"UpgradeRequest({self.user}, {self.get_status_display()})"
