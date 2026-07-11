

from pathlib import Path
import os
from decouple import config
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config(
      'ALLOWED_HOSTS',
      default='127.0.0.1,localhost,0.0.0.0'
  ).split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cards',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'ecard_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'cards/templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ecard_project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASE_URL = config(
    "DATABASE_URL",
    default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
)

DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL)
}

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Email settings
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='localhost')
EMAIL_PORT = config('EMAIL_PORT', default=25, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=False, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='webmaster@localhost')


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en'

LANGUAGES = [
    ('en', 'English'),
    ('bn', 'বাংলা'),
]

LOCALE_PATHS = [BASE_DIR / 'locale']

TIME_ZONE = 'UTC'

USE_I18N = True
USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT =  os.path.join(BASE_DIR,'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/register/'

# Security settings
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)


# Sprint 4 — payments, AI, wallet feature flags (empty = feature hidden / disabled)
STRIPE_PUBLIC_KEY   = config('STRIPE_PUBLIC_KEY',   default='')
STRIPE_SECRET_KEY   = config('STRIPE_SECRET_KEY',   default='')
BKASH_MERCHANT_URL  = config('BKASH_MERCHANT_URL',  default='')
BKASH_APP_KEY       = config('BKASH_APP_KEY',       default='')
BKASH_APP_SECRET    = config('BKASH_APP_SECRET',    default='')

AI_PROVIDER = config('AI_PROVIDER', default='')          # 'anthropic' | 'openai' | ''
AI_API_KEY  = config('AI_API_KEY',  default='')
AI_MODEL    = config('AI_MODEL',    default='claude-haiku-4-5-20251001')

APPLE_WALLET_CERT_PATH = config('APPLE_WALLET_CERT_PATH', default='')
GOOGLE_WALLET_SA_JSON  = config('GOOGLE_WALLET_SA_JSON',  default='')

# Convenience feature flags
FEATURE_PAYMENTS = bool(STRIPE_SECRET_KEY or BKASH_APP_KEY)
FEATURE_AI       = bool(AI_PROVIDER and AI_API_KEY)
FEATURE_WALLET   = bool(APPLE_WALLET_CERT_PATH or GOOGLE_WALLET_SA_JSON)


# ZeptoMail — transactional email for OTP password reset
ZEPTOMAIL_URL          = config('ZEPTOMAIL_URL',          default='https://api.zeptomail.com/v1.1/email')
ZEPTOMAIL_TOKEN        = config('ZEPTOMAIL_TOKEN',        default='')
ZEPTOMAIL_FROM_ADDRESS = config('ZEPTOMAIL_FROM_ADDRESS', default='mycard@dupno.com')
ZEPTOMAIL_FROM_NAME    = config('ZEPTOMAIL_FROM_NAME',    default='MY-Card')

FEATURE_EMAIL_OTP = bool(ZEPTOMAIL_TOKEN)

# Password reset OTP config
PW_RESET_OTP_TTL_SECONDS = 600         # 10 minutes
PW_RESET_OTP_MAX_ATTEMPTS = 5
PW_RESET_OTP_RESEND_COOLDOWN = 45      # seconds between resends
PW_RESET_MAX_PER_DAY = 2               # per user (email/phone), rolling 24h day
