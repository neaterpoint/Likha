"""
Django settings for the Likha project.
"""

from pathlib import Path
import os
import sys

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# SECURITY: DEBUG defaults to False, so a missing env var can never expose debug pages.
# Set DEBUG=True in your local .env.
DEBUG = _env_bool("DEBUG", False)

# SECURITY: the insecure fallback is only allowed while DEBUG is on.
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-dev-only-change-me"
    else:
        raise ImproperlyConfigured("SECRET_KEY must be set in the environment when DEBUG is False.")

# Comma-separated, e.g. ALLOWED_HOSTS=192.168.1.20,likha.example.com
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]

# Needed behind an HTTPS proxy, e.g. CSRF_TRUSTED_ORIGINS=https://likha.example.com
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Feature apps (vertical slices)
    'apps.login',
    'apps.register',
    'apps.home',
    'apps.profile',
    'apps.user_settings',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # serves static files in production
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.user_settings.context_processors.theme',   # provides {{ user_theme }}
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database (Supabase Postgres via the Session pooler URL in .env)
DATABASES = {
    "default": dj_database_url.parse(
        os.environ["DATABASE_URL"],
        conn_max_age=600,
        ssl_require=True,
    )
}
# Run the test suite on in-memory SQLite: fast, and it never touches your Supabase project
# (Supabase's pooler keeps connections open, which breaks Django's test-database teardown).
if "test" in sys.argv:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'          # `python manage.py collectstatic` writes here
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# Media files (user-uploaded, e.g. profile images).
# NOTE: most hosts have an ephemeral disk, so for production move these to
# object storage (e.g. Supabase Storage) instead of the local media/ folder.
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'


LOGIN_REDIRECT_URL = 'home:home'
LOGOUT_REDIRECT_URL = 'login:login'
LOGIN_URL = 'login:login'


# Production hardening (only when DEBUG is off)
if not DEBUG:
    SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Start small; raise to 31536000 (1 year) once you've confirmed HTTPS works everywhere.
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
    # Only enable if your host's proxy sets X-Forwarded-Proto (Render, Railway, Heroku, etc. do).
    if _env_bool("TRUST_PROXY_SSL_HEADER", False):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# AI + external APIs
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-4-hydrogen")
# Used automatically if the main model times out or is overloaded. Set empty to disable.
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
GEMINI_TIMEOUT_SECONDS = int(os.environ.get("GEMINI_TIMEOUT_SECONDS", "75"))
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")   # free, instant: pixabay.com/api/docs
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")     # optional; Pexels has paused new keys
SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY", "")   # Google Images via serpapi.com (tried first)
# Google Images "tbs" filter. Default: photos only. To restrict to Creative Commons, set it in .env:
# in Google Images click Tools > Usage rights > Creative Commons licenses, then copy the tbs= value from the URL.
SERPAPI_TBS = os.environ.get("SERPAPI_TBS", "itp:photos")


# Show AI timing/errors in the runserver terminal.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)-7s %(message)s", "datefmt": "%H:%M:%S"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {"apps": {"handlers": ["console"], "level": "INFO"}},
}