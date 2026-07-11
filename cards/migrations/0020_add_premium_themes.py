from django.db import migrations


NEW_THEMES = [
    dict(
        slug='deep-ocean',
        name='Deep Ocean',
        description='Abyssal blue depths bleeding into a teal-lit sonar accent — quiet, confident, professional.',
        background='linear-gradient(160deg, #030B24 0%, #052042 45%, #0A6E80 100%)',
        accent_color='#38E1FF',
        text_color='#E8F6FF',
        is_premium=True,
        sort_order=70,
    ),
    dict(
        slug='molten-gold',
        name='Molten Gold',
        description='Charcoal base with warm gold and amber runoff — VIP without the shout.',
        background='linear-gradient(140deg, #14100C 0%, #2A1F14 55%, #5A3B0F 100%)',
        accent_color='#FBBF24',
        text_color='#FFF7E6',
        is_premium=True,
        sort_order=80,
    ),
    dict(
        slug='neon-tokyo',
        name='Neon Tokyo',
        description='Cyberpunk pink and cyan on a wet-street black. Instantly memorable.',
        background='linear-gradient(135deg, #05060B 0%, #1B0533 40%, #4B1178 75%, #FF2E92 100%)',
        accent_color='#F471FF',
        text_color='#FFFFFF',
        is_premium=True,
        sort_order=90,
    ),
    dict(
        slug='forest-whisper',
        name='Forest Whisper',
        description='Deep emerald canopy with lime shafts breaking through. Grounded and organic.',
        background='linear-gradient(160deg, #051B12 0%, #0E3D2A 50%, #185E42 100%)',
        accent_color='#A3E635',
        text_color='#E9FBEF',
        is_premium=True,
        sort_order=100,
    ),
    dict(
        slug='rose-champagne',
        name='Rose Champagne',
        description='Muted rose plum with warm gold trim — luxury, evening-event energy.',
        background='linear-gradient(150deg, #1A0B14 0%, #3D1B2E 50%, #6E2A46 100%)',
        accent_color='#F5B893',
        text_color='#FEE9DC',
        is_premium=True,
        sort_order=110,
    ),
    dict(
        slug='midnight-aurora',
        name='Midnight Aurora',
        description='Deep indigo sky with iridescent violet + cyan curtain lights. Dramatic.',
        background='linear-gradient(160deg, #030214 0%, #0A0B3D 30%, #241361 60%, #1AA5A5 100%)',
        accent_color='#B78BFF',
        text_color='#EEEBFF',
        is_premium=True,
        sort_order=120,
    ),
    dict(
        slug='coral-reef',
        name='Coral Reef',
        description='Warm sunset coral rolling into deep teal water. Tropical premium.',
        background='linear-gradient(135deg, #FF7A5C 0%, #FF9A73 25%, #4EC5C5 75%, #0E5E7C 100%)',
        accent_color='#0E5E7C',
        text_color='#0B0D14',
        is_premium=True,
        sort_order=130,
    ),
    dict(
        slug='ember-flame',
        name='Ember Flame',
        description='Charred graphite with hot ember pulses — for the founders who ship.',
        background='linear-gradient(155deg, #0E0704 0%, #23110B 40%, #7A2410 80%, #F45C1E 100%)',
        accent_color='#F45C1E',
        text_color='#FFEAD4',
        is_premium=True,
        sort_order=140,
    ),
]


def forwards(apps, schema_editor):
    CardTheme = apps.get_model('cards', 'CardTheme')
    for theme in NEW_THEMES:
        CardTheme.objects.update_or_create(slug=theme['slug'], defaults=theme)


def backwards(apps, schema_editor):
    CardTheme = apps.get_model('cards', 'CardTheme')
    CardTheme.objects.filter(slug__in=[t['slug'] for t in NEW_THEMES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('cards', '0019_seed_card_themes'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
