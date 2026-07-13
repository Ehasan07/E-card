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
    # Daily rate-limit for password reset requests
    password_reset_count = models.PositiveSmallIntegerField(default=0)
    password_reset_day = models.DateField(blank=True, null=True)
    card_limit = models.PositiveIntegerField(default=DEFAULT_CARD_LIMIT)
    # One-payment-covers-all: after the yearly subscription is charged, this
    # date bumps to +1 year and all of the user's cards stay active until it.
    subscription_paid_until = models.DateTimeField(blank=True, null=True)

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
    slug_customized = models.BooleanField(
        default=False,
        help_text="Set to True after the owner uses their one-time public-URL change.",
    )
    is_active = models.BooleanField(default=True)
    text_color = models.CharField(max_length=20, default='#FFFFFF')
    card_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_PERSONAL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Card lifecycle — every card gets a 12-month free trial from creation.
    # After trial, the yearly subscription payment covers all of the owner's
    # cards until Profile.subscription_paid_until. When that lapses (or the
    # trial ends without payment), the card is taken offline and the owner
    # must reactivate.
    STATUS_TRIAL           = 'trial'
    STATUS_ACTIVE_PAID     = 'active_paid'
    STATUS_EXPIRING_SOON   = 'expiring_soon'
    STATUS_EXPIRED         = 'expired'
    STATUS_ADMIN_DISABLED  = 'admin_disabled'
    LIFECYCLE_CHOICES = [
        (STATUS_TRIAL,          'Trial (first 12 months)'),
        (STATUS_ACTIVE_PAID,    'Paid'),
        (STATUS_EXPIRING_SOON,  'Expiring soon'),
        (STATUS_EXPIRED,        'Expired — offline'),
        (STATUS_ADMIN_DISABLED, 'Disabled by admin'),
    ]
    lifecycle_status = models.CharField(
        max_length=24,
        choices=LIFECYCLE_CHOICES,
        default=STATUS_TRIAL,
    )
    trial_ends_at = models.DateTimeField(blank=True, null=True)
    deactivated_at = models.DateTimeField(blank=True, null=True)
    deactivation_reason = models.CharField(max_length=64, blank=True)
    last_warning_stage = models.PositiveSmallIntegerField(
        default=0,
        help_text="Highest warning stage already sent (30/7/1 → 1/2/3). Prevents re-sending.",
    )

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('view_card', args=[self.slug])

    def save(self, *args, **kwargs):
        # First-save: stamp the 12-month trial clock from creation time.
        if not self.pk and not self.trial_ends_at:
            from django.conf import settings as dj_settings
            months = getattr(dj_settings, 'CARD_TRIAL_MONTHS', 12)
            self.trial_ends_at = timezone.now() + timezone.timedelta(days=months * 30)

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


class CardChangeLog(models.Model):
    card = models.ForeignKey('Card', on_delete=models.CASCADE, related_name='change_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='card_change_logs')
    summary = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        if self.summary:
            return f"{self.card} · {self.summary}"
        return f"{self.card} · {self.created_at:%Y-%m-%d %H:%M}"


class Feedback(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback from {self.name}"


class CardInteraction(models.Model):
    KIND_VIEW   = 'view'
    KIND_CLICK  = 'click'
    KIND_SAVE   = 'save'
    KIND_WALLET = 'wallet'
    KIND_LEAD   = 'lead'
    KIND_CHOICES = [
        (KIND_VIEW,   'View'),
        (KIND_CLICK,  'Click'),
        (KIND_SAVE,   'Save contact'),
        (KIND_WALLET, 'Wallet add'),
        (KIND_LEAD,   'Lead submitted'),
    ]

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='interactions')
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    target = models.CharField(max_length=120, blank=True)  # e.g. 'linkedin', 'phone', 'email'
    session_id = models.CharField(max_length=64, blank=True)
    country = models.CharField(max_length=2, blank=True)   # ISO alpha-2 when available
    referrer = models.CharField(max_length=255, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['card', 'kind', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.card} · {self.created_at:%Y-%m-%d %H:%M}"


class CardTheme(models.Model):
    """Curated visual themes card owners can pick in the editor."""
    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    background = models.CharField(max_length=500)         # CSS gradient / color
    accent_color = models.CharField(max_length=20, default='#7CFFB2')
    text_color = models.CharField(max_length=20, default='#FFFFFF')
    is_premium = models.BooleanField(default=False)       # Pro-only themes
    sort_order = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class Payment(models.Model):
    """Records both Stripe and bKash transactions in one uniform shape."""
    GATEWAY_STRIPE = 'stripe'
    GATEWAY_BKASH = 'bkash'
    GATEWAY_MANUAL = 'manual'
    GATEWAY_CHOICES = [
        (GATEWAY_STRIPE, 'Stripe'),
        (GATEWAY_BKASH, 'bKash'),
        (GATEWAY_MANUAL, 'Manual'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_REFUNDED = 'refunded'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_REFUNDED, 'Refunded'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES, default=GATEWAY_MANUAL)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default='BDT')
    txn_id = models.CharField(max_length=120, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ---- bKash recurring-payment fields ---------------------------------
    # These are populated as the subscription progresses through the bKash
    # lifecycle (Create → Verified → Payment success → Cancel/Refund).
    # All optional so the same Payment row is reused for other gateways.
    bkash_subscription_request_id = models.CharField(max_length=120, blank=True, db_index=True)
    bkash_subscription_id = models.CharField(max_length=64, blank=True, db_index=True)
    bkash_payment_id = models.CharField(max_length=64, blank=True, db_index=True)
    bkash_trx_id = models.CharField(max_length=64, blank=True, db_index=True)
    bkash_payer_msisdn = models.CharField(max_length=20, blank=True)
    bkash_next_payment_date = models.DateField(null=True, blank=True)
    bkash_expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'status', 'created_at'])]

    def __str__(self):
        return f"{self.get_gateway_display()} · {self.amount} {self.currency} · {self.get_status_display()}"


class LeadCapture(models.Model):
    STATUS_NEW      = 'new'
    STATUS_REPLIED  = 'replied'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [
        (STATUS_NEW,      'New'),
        (STATUS_REPLIED,  'Replied'),
        (STATUS_ARCHIVED, 'Archived'),
    ]

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='leads')
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    message = models.TextField(blank=True)
    utm_source = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_NEW)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['card', 'status', 'created_at']),
        ]

    def __str__(self):
        return f"Lead from {self.name} for {self.card}"

    @property
    def preferred_contact(self):
        return self.email or self.phone or ''


class CardLifecycleLog(models.Model):
    """Audit trail for every automatic or manual lifecycle event on a card.

    The admin dashboard uses this to explain WHY a card went offline, and
    when the owner reactivated, extended, or renewed it. `actor='system'`
    rows come from the daily tick; `actor='admin'` from the control
    surface; `actor='user'` from reactivation/renewal actions.
    """
    ACTION_TRIAL_STARTED   = 'trial_started'
    ACTION_WARNING_30D     = 'warning_30d'
    ACTION_WARNING_7D      = 'warning_7d'
    ACTION_WARNING_1D      = 'warning_1d'
    ACTION_EXPIRING_SOON   = 'expiring_soon'
    ACTION_TRIAL_ENDED     = 'trial_ended'
    ACTION_DEACTIVATED     = 'deactivated'
    ACTION_REACTIVATED     = 'reactivated'
    ACTION_RENEWED         = 'renewed'
    ACTION_ADMIN_OVERRIDE  = 'admin_override'
    ACTION_CHOICES = [
        (ACTION_TRIAL_STARTED,   'Trial started'),
        (ACTION_WARNING_30D,     '30-day warning sent'),
        (ACTION_WARNING_7D,      '7-day warning sent'),
        (ACTION_WARNING_1D,      '1-day warning sent'),
        (ACTION_EXPIRING_SOON,   'Marked expiring soon'),
        (ACTION_TRIAL_ENDED,     'Trial ended'),
        (ACTION_DEACTIVATED,     'Deactivated (offline)'),
        (ACTION_REACTIVATED,     'Reactivated (back online)'),
        (ACTION_RENEWED,         'Renewed (paid)'),
        (ACTION_ADMIN_OVERRIDE,  'Admin override'),
    ]

    ACTOR_SYSTEM = 'system'
    ACTOR_ADMIN  = 'admin'
    ACTOR_USER   = 'user'
    ACTOR_CHOICES = [
        (ACTOR_SYSTEM, 'System (cron)'),
        (ACTOR_ADMIN,  'Admin'),
        (ACTOR_USER,   'User'),
    ]

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='lifecycle_logs')
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    actor = models.CharField(max_length=16, choices=ACTOR_CHOICES, default=ACTOR_SYSTEM)
    actor_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
        help_text="Admin user who triggered the action (only for actor=admin).",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['card', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} · {self.card.slug} · {self.created_at:%Y-%m-%d %H:%M}"


class UserNotification(models.Model):
    """In-app inbox message shown to a user in their dashboard.

    Separate from the admin-facing UpgradeRequest system — this is for
    proactive notifications from the platform to the user (card going
    offline, back online, renewal due, admin action taken, etc.).
    """
    KIND_CARD_OFFLINE      = 'card_offline'
    KIND_CARD_ONLINE       = 'card_online'
    KIND_RENEWAL_WARNING   = 'renewal_warning'
    KIND_TRIAL_ENDED       = 'trial_ended'
    KIND_ADMIN_ACTION      = 'admin_action'
    KIND_PAYMENT_RECEIVED  = 'payment_received'
    KIND_CHOICES = [
        (KIND_CARD_OFFLINE,     'Card went offline'),
        (KIND_CARD_ONLINE,      'Card back online'),
        (KIND_RENEWAL_WARNING,  'Renewal reminder'),
        (KIND_TRIAL_ENDED,      'Trial ended'),
        (KIND_ADMIN_ACTION,     'Admin action'),
        (KIND_PAYMENT_RECEIVED, 'Payment received'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    card = models.ForeignKey(Card, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    action_url = models.CharField(max_length=250, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', 'created_at']),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} → {self.user.username}"
