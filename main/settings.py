"""
Django settings for main project.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

import os
import sys
from pathlib import Path

import environ

from main import sentry

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_SECRET_KEY=str,
    DJANGO_CORS_ORIGIN_REGEX_WHITELIST=(list, []),
    # Database
    DB_NAME=str,
    DB_USER=str,
    DB_PASSWORD=str,
    DB_HOST=str,
    DB_PORT=int,
    # Redis
    CELERY_REDIS_URL=str,
    DJANGO_CACHE_REDIS_URL=str,
    # -- For running test (Optional)
    TEST_DJANGO_CACHE_REDIS_URL=(str, None),
    # Static, Media configs
    DJANGO_STATIC_URL=(str, "/static/"),
    DJANGO_MEDIA_URL=(str, "/media/"),
    # -- File System
    DJANGO_STATIC_ROOT=(str, os.path.join(BASE_DIR, "assets/static")),  # Where to store
    DJANGO_MEDIA_ROOT=(str, os.path.join(BASE_DIR, "assets/media")),  # Where to store
    # -- S3
    DJANGO_USE_S3=(bool, False),
    MEDIA_FILE_CACHE_URL_TTL=(int, 86400),  # 1 day default
    TEMP_FILE_DIR=(str, "/tmp/"),
    AWS_S3_BUCKET_STATIC=str,
    AWS_S3_BUCKET_MEDIA=str,
    AWS_S3_QUERYSTRING_EXPIRE=(int, 60 * 60 * 24 * 2),  # Default 2 days
    # -- -- S3 Credentials - Role is preferred
    AWS_S3_ACCESS_KEY_ID=(str, None),
    AWS_S3_SECRET_ACCESS_KEY=(str, None),
    AWS_S3_ENDPOINT_URL=(str, None),  # Optional
    # Sentry
    SENTRY_DSN=(str, None),
    SENTRY_SAMPLE_RATE=(float, 0.2),
    # App Domain
    APP_DOMAIN=str,  # api.example.com
    APP_HTTP_PROTOCOL=str,  # http|https
    APP_FRONTEND_HOST=str,  # http://frontend.example.com
    DJANGO_ALLOWED_HOST=(list, ["*"]),
    SESSION_COOKIE_DOMAIN=str,
    CSRF_COOKIE_DOMAIN=str,
    # Misc
    RELEASE=(str, "develop"),
    APP_ENVIRONMENT=str,  # dev/prod
    APP_TYPE=str,
    DJANGO_TIME_ZONE=(str, "UTC"),
    DOCKER_HOST_IP=(str, None),
    # Hcaptcha
    HCAPTCHA_SECRET=(str, "0x0000000000000000000000000000000000000000"),
    # Testing
    PYTEST_XDIST_WORKER=(str, None),
    # EMAIL
    EMAIL_FROM=str,
    DJANGO_ADMINS=(list, ["Admin <admin@thedeep.io>"]),
    EMAIL_BACKEND=(str, ""),  # SES|SMTP -> CONSOLE is used by default
    # -- SES Credentials - Role is preferred
    AWS_SES_AWS_ACCESS_KEY_ID=(str, None),
    AWS_SES_AWS_SECRET_ACCESS_KEY=(str, None),
    # -- SMTP
    SMTP_EMAIL_HOST=str,
    SMTP_EMAIL_PORT=int,
    SMTP_EMAIL_USERNAME=str,
    SMTP_EMAIL_PASSWORD=str,
    # MISC
    ALLOW_DUMMY_DATA_SCRIPT=(bool, False),  # WARNING
    ENABLE_BREAKING_MODE=(bool, False),  # Only enable if you know what you are doing
)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("DJANGO_SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DJANGO_DEBUG")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOST")

APP_SITE_NAME = "Questionnaire Builder"
APP_HTTP_PROTOCOL = env("APP_HTTP_PROTOCOL")
APP_DOMAIN = env("APP_DOMAIN")
APP_FRONTEND_HOST = env("APP_FRONTEND_HOST")

APP_ENVIRONMENT = env("APP_ENVIRONMENT")
APP_TYPE = env("APP_TYPE")

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    # External apps
    "admin_auto_filters",
    "django_premailer",
    "storages",
    "corsheaders",
    # Internal apps
    "apps.common",  # Common
    "apps.user",
    "apps.project",
    "apps.track",
    "apps.journal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "main.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            "apps/templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "main.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "OPTIONS": {"options": "-c search_path=public"},
    },
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTH_USER_MODEL = "user.User"

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = env("DJANGO_TIME_ZONE")

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = env("DJANGO_STATIC_URL")
MEDIA_URL = env("DJANGO_MEDIA_URL")

# Default
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

TEMP_FILE_DIR = env("TEMP_FILE_DIR")
MEDIA_FILE_CACHE_URL_TTL = env("MEDIA_FILE_CACHE_URL_TTL")

if env("DJANGO_USE_S3"):
    # AWS S3 Bucket Credentials
    AWS_S3_BUCKET_STATIC = env("AWS_S3_BUCKET_STATIC")
    AWS_S3_BUCKET_MEDIA = env("AWS_S3_BUCKET_MEDIA")
    # If environment variable are not provided, then EC2 Role will be used.
    AWS_S3_ACCESS_KEY_ID = env("AWS_S3_ACCESS_KEY_ID")
    AWS_S3_SECRET_ACCESS_KEY = env("AWS_S3_SECRET_ACCESS_KEY")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL")
    AWS_QUERYSTRING_EXPIRE = env("AWS_S3_QUERYSTRING_EXPIRE")
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_IS_GZIPPED = True
    GZIP_CONTENT_TYPES = [
        "text/css",
        "text/javascript",
        "application/javascript",
        "application/x-javascript",
        "image/svg+xml",
        "application/json",
    ]
    # Static configuration
    STORAGES["staticfiles"]["BACKEND"] = "main.storages.S3StaticStorage"
    # Media configuration
    STORAGES["default"]["BACKEND"] = "main.storages.S3MediaStorage"
else:  # File system storage
    STATIC_ROOT = env("DJANGO_STATIC_ROOT")
    MEDIA_ROOT = env("DJANGO_MEDIA_ROOT")

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS
if not env("DJANGO_CORS_ORIGIN_REGEX_WHITELIST"):
    CORS_ORIGIN_ALLOW_ALL = True
else:
    # Example ^https://[\w-]+\.mapswipe\.org$
    CORS_ORIGIN_REGEX_WHITELIST = env("DJANGO_CORS_ORIGIN_REGEX_WHITELIST")

CORS_ALLOW_CREDENTIALS = True
CORS_URLS_REGEX = r"(^/media/.*$)|(^/graphql/$)"
CORS_ALLOW_METHODS = (
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
)

CORS_ALLOW_HEADERS = (
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "sentry-trace",
)

# Sentry Config
SENTRY_DSN = env("SENTRY_DSN")
SENTRY_SAMPLE_RATE = env("SENTRY_SAMPLE_RATE")
SENTRY_ENABLED = False

SENTRY_CONFIG = {
    "app_type": APP_TYPE,
    "dsn": SENTRY_DSN,
    "send_default_pii": True,
    "release": env("RELEASE"),
    "environment": APP_ENVIRONMENT,
    "debug": DEBUG,
    "tags": {
        "site": ",".join(set(ALLOWED_HOSTS)),
    },
}

if SENTRY_DSN:
    sentry.init_sentry(**SENTRY_CONFIG)
    SENTRY_ENABLED = True

# See if we are inside a test environment (pytest)
TESTING = (
    any(
        [
            arg in sys.argv
            for arg in [
                "test",
                "pytest",
                "/usr/local/bin/pytest",
                "py.test",
                "/usr/local/bin/py.test",
                "/usr/local/lib/python3.6/dist-packages/py/test.py",
            ]
            # Provided by pytest-xdist
        ]
    )
    or env("PYTEST_XDIST_WORKER") is not None
)


# Security Header configuration
SESSION_COOKIE_NAME = f"questionnaire-builder-{APP_ENVIRONMENT}-sessionid"
CSRF_COOKIE_NAME = f"questionnaire-builder-{APP_ENVIRONMENT}-csrftoken"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
CSP_DEFAULT_SRC = ["'self'"]
SECURE_REFERRER_POLICY = "same-origin"
if APP_HTTP_PROTOCOL == "https":
    SESSION_COOKIE_NAME = f"__Secure-{SESSION_COOKIE_NAME}"
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SECURE_HSTS_SECONDS = 30  # TODO: Increase this slowly
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_TRUSTED_ORIGINS = [
        APP_FRONTEND_HOST,
        f"{APP_HTTP_PROTOCOL}://{APP_DOMAIN}",
    ]

# https://docs.djangoproject.com/en/3.2/ref/settings/#std:setting-SESSION_COOKIE_DOMAIN
SESSION_COOKIE_DOMAIN = env("SESSION_COOKIE_DOMAIN")
# https://docs.djangoproject.com/en/3.2/ref/settings/#csrf-cookie-domain
CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN")

# https://docs.hcaptcha.com/#integration-testing-test-keys
HCAPTCHA_SECRET = env("HCAPTCHA_SECRET")

TOKEN_DEFAULT_RESET_TIMEOUT_DAYS = 7

# EMAIL
SPECIFED_EMAIL_BACKEND = env("EMAIL_BACKEND").upper()
ADMINS = env("DJANGO_ADMINS")
EMAIL_FROM = env("EMAIL_FROM")

if not TESTING and SPECIFED_EMAIL_BACKEND == "SES":
    EMAIL_BACKEND = "django_ses.SESBackend"
    # If environment variable are not provided, then EC2 Role will be used.
    AWS_SES_ACCESS_KEY_ID = env("AWS_SES_AWS_ACCESS_KEY_ID")
    AWS_SES_SECRET_ACCESS_KEY = env("AWS_SES_AWS_SECRET_ACCESS_KEY")
elif not TESTING and SPECIFED_EMAIL_BACKEND == "SMTP":
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("SMTP_EMAIL_HOST")
    EMAIL_PORT = env("SMTP_EMAIL_PORT")
    EMAIL_HOST_USER = env("SMTP_EMAIL_USERNAME")
    EMAIL_HOST_PASSWORD = env("SMTP_EMAIL_PASSWORD")
else:
    # DUMP EMAILS TO CONSOLE
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Strawberry
# -- Pagination
STRAWBERRY_ENUM_TO_STRAWBERRY_ENUM_MAP = "main.graphql.enums.ENUM_TO_STRAWBERRY_ENUM_MAP"
STRAWBERRY_DEFAULT_PAGINATION_LIMIT = 50
STRAWBERRY_MAX_PAGINATION_LIMIT = 100


# Redis
CELERY_REDIS_URL = env("CELERY_REDIS_URL")
DJANGO_CACHE_REDIS_URL = env("DJANGO_CACHE_REDIS_URL")
TEST_DJANGO_CACHE_REDIS_URL = env("TEST_DJANGO_CACHE_REDIS_URL")

# Caches
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": DJANGO_CACHE_REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "dj_cache-",
    },
    "local-memory": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "local-memory-02",
    },
}

# Celery
CELERY_BROKER_URL = CELERY_REDIS_URL
CELERY_RESULT_BACKEND = CELERY_REDIS_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_EVENT_QUEUE_PREFIX = "cracker-celery-"
CELERY_ACKS_LATE = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
