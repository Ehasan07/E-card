"""Backfill existing cards with a fresh 12-month trial from today.

Q4 answer: grandfather all existing cards into a full new trial period
regardless of how long they've already existed. Also mark inactive cards
(is_active=False) as admin_disabled so the automated tick doesn't touch
them.
"""

from django.db import migrations
from django.utils import timezone


def backfill(apps, schema_editor):
    Card = apps.get_model('cards', 'Card')
    trial_end = timezone.now() + timezone.timedelta(days=12 * 30)

    for card in Card.objects.all():
        if card.trial_ends_at is None:
            card.trial_ends_at = trial_end
        if not card.is_active:
            card.lifecycle_status = 'admin_disabled'
            card.deactivation_reason = 'pre_lifecycle_disabled'
            if not card.deactivated_at:
                card.deactivated_at = timezone.now()
        else:
            card.lifecycle_status = 'trial'
        card.save(update_fields=[
            'trial_ends_at',
            'lifecycle_status',
            'deactivation_reason',
            'deactivated_at',
        ])


def noop_reverse(apps, schema_editor):
    """Reversing this migration leaves the data untouched — the schema
    migration handles rollback of the fields themselves."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('cards', '0023_card_deactivated_at_card_deactivation_reason_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
