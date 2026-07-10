from django.db import migrations


THEMES = [
    dict(
        slug='aurora-dark',
        name='Aurora Dark',
        description='Deep space canvas with a neon-mint aurora — the MY-Card signature look.',
        background='linear-gradient(160deg, #05060B 0%, #0B0D14 40%, #124D33 100%)',
        accent_color='#7CFFB2',
        text_color='#F2F4F8',
        is_premium=False,
        sort_order=10,
    ),
    dict(
        slug='cyber-neon',
        name='Cyber Neon',
        description='Magenta and cyan glow — bold, tech-forward, memorable.',
        background='linear-gradient(135deg, #20002c 0%, #cbb4d4 100%)',
        accent_color='#F471FF',
        text_color='#F2F4F8',
        is_premium=False,
        sort_order=20,
    ),
    dict(
        slug='executive-slate',
        name='Executive Slate',
        description='Matte dark with silver accents — trustworthy, senior, LinkedIn-ready.',
        background='linear-gradient(135deg, #1f1c2c 0%, #928dab 100%)',
        accent_color='#CBD5E1',
        text_color='#F2F4F8',
        is_premium=False,
        sort_order=30,
    ),
    dict(
        slug='sunset-warm',
        name='Sunset Warm',
        description='Soft peach and blush — approachable and warm.',
        background='linear-gradient(135deg, #ff9a9e 0%, #fad0c4 100%)',
        accent_color='#E11D48',
        text_color='#0B0D14',
        is_premium=False,
        sort_order=40,
    ),
    dict(
        slug='paper-light',
        name='Paper Light',
        description='Ivory canvas for classic, print-inspired presence.',
        background='linear-gradient(160deg, #FEFCF9 0%, #F1F0EA 100%)',
        accent_color='#B45309',
        text_color='#1F1B15',
        is_premium=True,
        sort_order=50,
    ),
    dict(
        slug='bento-minimal',
        name='Bento Minimal',
        description='Structured off-white grid — modern minimalism for design-forward pros.',
        background='linear-gradient(180deg, #EFF2F7 0%, #E1E6EE 100%)',
        accent_color='#0F172A',
        text_color='#0B0D14',
        is_premium=True,
        sort_order=60,
    ),
]


def forwards(apps, schema_editor):
    CardTheme = apps.get_model('cards', 'CardTheme')
    for theme in THEMES:
        CardTheme.objects.update_or_create(slug=theme['slug'], defaults=theme)


def backwards(apps, schema_editor):
    CardTheme = apps.get_model('cards', 'CardTheme')
    CardTheme.objects.filter(slug__in=[t['slug'] for t in THEMES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('cards', '0018_cardtheme_payment'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
