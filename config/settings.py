"""Django settings. Everything environment-specific comes from `.env` (see `.env.example`)."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
    EMAIL_PORT=(int, 25),
    EMAIL_USE_TLS=(bool, False),
    EMAIL_USE_SSL=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.accounts",
    "apps.masterdata",
    "apps.platform_config",
    "apps.shipments",
    "apps.notifications",
    "apps.inventory",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "apps.shipments.middleware.RequestIdMiddleware",
    "apps.accounts.middleware.NoStoreApiMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.SessionLimitsMiddleware",
    "apps.shipments.middleware.RequestLanguageMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# PostgreSQL only (never SQLite, including tests).
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
if not DATABASES["default"]["ENGINE"].endswith("postgresql"):
    raise RuntimeError("DATABASE_URL must point to PostgreSQL.")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Argon2 first; PBKDF2 stays so existing hashes still verify. (Sign-in is by one-time code; this
# covers the few emergency `createsuperuser` passwords.)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Times are stored in UTC and displayed in Europe/Rome.
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
TIME_ZONE_DISPLAY = env("TIME_ZONE_DISPLAY", default="Europe/Rome")

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
# Public address of the app, used for links in emails
SITE_URL = env("SITE_URL", default="http://localhost:5173")
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))

# Sessions: DB-backed. Absolute / idle limits come from SiteConfig (apps.accounts.middleware).
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False  # the SPA reads the token from the cookie

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")  # STARTTLS, usually port 587
EMAIL_USE_SSL = env("EMAIL_USE_SSL")  # implicit TLS, usually port 465 (not with EMAIL_USE_TLS)
# False: a background thread sends queued emails after the response; True: send in the request (tests)
EMAIL_WORKER_SYNC = env.bool("EMAIL_WORKER_SYNC", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=20)  # never hang a request on a slow mail server
# Testing against a real mail server (see .env.example). Both optional, empty by default.
EMAIL_FROM_OVERRIDE = env("EMAIL_FROM_OVERRIDE", default="")  # every email goes out From this
EMAIL_REDIRECT_TO = env("EMAIL_REDIRECT_TO", default="")  # every email goes ONLY to this
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply-shipments@diasorin.com")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.Session401Authentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.shipments.api.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Diasorin Digital Shipment Form API",
    "DESCRIPTION": "Backend API for DSI-FORM-000208.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}
