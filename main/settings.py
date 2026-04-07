"""
Django settings for main project.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

import sys
import typing
from pathlib import Path

if typing.TYPE_CHECKING:
    from urllib.parse import ParseResult as UrlParseResult

import environ
from corsheaders.defaults import default_headers

from main.logging import log_render_custom_field
from main.sentry import SentryConfig

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_SECRET_KEY=str,
    # Database
    DB_NAME=str,
    DB_USER=str,
    DB_PASSWORD=str,
    DB_HOST=str,
    DB_PORT=int,
    DB_SSLMODE=(str, "prefer"),
    # Redis
    CELERY_REDIS_URL=str,
    DJANGO_CACHE_REDIS_URL=str,
    # -- For running test (Optional)
    TEST_DJANGO_CACHE_REDIS_URL=(str, None),
    # Static, Media configs
    DJANGO_STATIC_URL=(str, "/static/"),
    DJANGO_MEDIA_URL=(str, "/media/"),
    # -- File System
    DJANGO_STATIC_ROOT=(str, BASE_DIR / "assets/static"),  # Where to store
    DJANGO_MEDIA_ROOT=(str, BASE_DIR / "assets/media"),  # Where to store
    # -- S3
    AWS_S3_ENABLED=(bool, False),
    AWS_S3_ENDPOINT_URL=(str, None),
    AWS_S3_ACCESS_KEY_ID=str,
    AWS_S3_SECRET_ACCESS_KEY=str,
    AWS_S3_REGION_NAME=str,
    AWS_S3_MEDIA_BUCKET_NAME=str,
    AWS_S3_STATIC_BUCKET_NAME=str,
    # Sentry
    SENTRY_ENABLED=(bool, False),
    SENTRY_MONITOR_CRON_TASKS=(bool, True),
    SENTRY_DEBUG=(str, False),
    SENTRY_DSN=str,
    SENTRY_TRACES_SAMPLE_RATE=(float, 0.2),
    SENTRY_PROFILE_SAMPLE_RATE=(float, 0.2),
    # App Domain
    APP_DOMAIN=str,  # https://api.example.com
    APP_FRONTEND_HOST=str,  # http://frontend.example.com
    ADDITIONAL_ALLOWED_HOST=(list, []),
    ADDITIONAL_TRUSTED_ORIGINS=(list, []),  # https://app1.example.com,https://app2.example.com
    SESSION_COOKIE_DOMAIN=str,
    SESSION_COOKIE_AGE=(int, 1209600),  # seconds (Default: 2 weeks)
    CSRF_COOKIE_DOMAIN=str,
    # Health check
    HEALTH_CHECK_DISK_USAGE_MAX=(int, 95),  # in percentage
    HEALTH_CHECK_DISK_MEMORY_MIN=(int, 100),  # in MB
    # Misc
    TEMP_FILE_DIR=(str, "/tmp/"),
    RELEASE=(str, "develop"),
    APP_ENVIRONMENT=str,  # dev/prod
    DJANGO_APP_TYPE=str,
    APP_LOG_LEVEL=(str, "INFO"),
    DJANGO_TIME_ZONE=(str, "UTC"),
    DOCKER_HOST_IP=(str, None),
    ALLOW_DUMMY_DATA_SCRIPT=(bool, False),  # WARNING
    # Testing
    PYTEST_XDIST_WORKER=(str, None),
    # EMAIL
    EMAIL_FROM=str,
    EMAIL_BACKEND=(str, ""),  # SES|SMTP -> CONSOLE is used by default
    # -- SES Credentials - Role is preferred
    AWS_SES_AWS_ACCESS_KEY_ID=(str, None),
    AWS_SES_AWS_SECRET_ACCESS_KEY=(str, None),
    # -- SMTP
    SMTP_EMAIL_HOST=str,
    SMTP_EMAIL_PORT=int,
    SMTP_EMAIL_USERNAME=str,
    SMTP_EMAIL_PASSWORD=str,
    # Google SSO
    GOOGLE_SSO_ENABLED=(bool, False),
    GOOGLE_SSO_ALLOWED_DOMAINS=(str, None),
    GOOGLE_SSO_CLIENT_ID=str,
    GOOGLE_SSO_SECRET=str,
    # Google services
    GOOGLE_CREDENTIALS_B64_GZ=(str, None),  # gzip -cn credential.json | base64 -w 0
    GOOGLE_CALENDAR_ID=(str, None),
    GOOGLE_CALENDAR_INCLUDE_DEBUG_IN_EVENT=(bool, False),
    # Slack
    SLACK_BOT_ENABLED=(bool, False),
    SLACK_BOT_NAME=(str, None),
    SLACK_BOT_ICON=(str, None),
    SLACK_BOT_TOKEN=str,
    SLACK_BOT_CHANNEL=str,
    # Daily Standup
    DAILY_STANDUP_DOCUMENTATION_REF=(str, None),
    DAILY_STANDUP_MEET_LINK=(str, None),
)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("DJANGO_SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DJANGO_DEBUG")
ALLOW_DUMMY_DATA_SCRIPT = env("ALLOW_DUMMY_DATA_SCRIPT")

APP_SITE_NAME = "Timur"
APP_DOMAIN = typing.cast("UrlParseResult", env.url("APP_DOMAIN"))
APP_FRONTEND_HOST = typing.cast("UrlParseResult", env.url("APP_FRONTEND_HOST"))

APP_ENVIRONMENT = typing.cast("str", env("APP_ENVIRONMENT")).upper()
DJANGO_APP_TYPE = typing.cast("str", env("DJANGO_APP_TYPE"))

ALLOWED_HOSTS: list[str] = [
    *env.list("ADDITIONAL_ALLOWED_HOST"),  # type: ignore[assignment]
    typing.cast("str", APP_DOMAIN.hostname),
]

# Application definition

INSTALLED_APPS = [
    "apps.common",  # Common (NOTE: Moved to first to override some of existing commands like clearsessions)
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    # External apps
    "reversion",
    "admin_auto_filters",
    "django_premailer",
    "storages",
    "corsheaders",
    "rangefilter",  # Django admin date range filter
    "djangoql",
    # -- Allauth
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    # - Health-check
    "health_check",  # required
    "health_check.db",  # stock Django health checkers
    "health_check.cache",
    "health_check.storage",
    "health_check.contrib.migrations",
    "health_check.contrib.psutil",  # disk and memory utilization; requires psutil
    "health_check.contrib.redis",  # requires Redis broker
    # Internal apps
    "apps.standup",
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
    "main.middlewares.sentry_middleware",
    "allauth.account.middleware.AccountMiddleware",
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
                "main.context_processors.app_contexts",
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
        "OPTIONS": {
            "options": "-c search_path=public",
            "sslmode": env("DB_SSLMODE"),
        },
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

STATICFILES_DIRS = [
    Path("apps") / "static",
]


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

AWS_S3_CACHED_TTL = 60 * 60 * 24

if env("AWS_S3_ENABLED"):
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL")

    AWS_S3_ACCESS_KEY_ID = env("AWS_S3_ACCESS_KEY_ID")
    AWS_S3_SECRET_ACCESS_KEY = env("AWS_S3_SECRET_ACCESS_KEY")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME")

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": env("AWS_S3_MEDIA_BUCKET_NAME"),
                "location": "media/",
                "file_overwrite": False,
                "querystring_expire": AWS_S3_CACHED_TTL + (60 * 60),
            },
        },
        "staticfiles": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": env("AWS_S3_STATIC_BUCKET_NAME"),
                "querystring_auth": False,
                "location": "static/",
                "file_overwrite": True,
            },
        },
    }
else:
    STATIC_ROOT = env("DJANGO_STATIC_ROOT")
    MEDIA_ROOT = env("DJANGO_MEDIA_ROOT")

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TIMUR_TRUSTED_ORIGINS = [
    APP_DOMAIN.geturl(),
    APP_FRONTEND_HOST.geturl(),
    *typing.cast("list[str]", env("ADDITIONAL_TRUSTED_ORIGINS")),
]

# CORS
CORS_ALLOWED_ORIGINS = TIMUR_TRUSTED_ORIGINS

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
    *default_headers,
    # Misc
    "accept-encoding",
    "content-type",
    "origin",
    # Sentry
    "sentry-trace",
    "baggage",
)

# Sentry Config
SENTRY_ENABLED = env("SENTRY_ENABLED")

if SENTRY_ENABLED:
    SENTRY_CONFIG = SentryConfig(
        dsn=typing.cast("str", env("SENTRY_DSN")),
        debug=typing.cast("bool", env("SENTRY_DEBUG")),
        app_type=DJANGO_APP_TYPE,
        release=typing.cast("str", env("RELEASE")),
        environment=APP_ENVIRONMENT,
        send_default_pii=True,
        monitor_cron_tasks=typing.cast("bool", env("SENTRY_MONITOR_CRON_TASKS")),
        traces_sample_rate=typing.cast("float", env("SENTRY_TRACES_SAMPLE_RATE")),
        profiles_sample_rate=typing.cast("float", env("SENTRY_PROFILE_SAMPLE_RATE")),
        # Custom configs
        tags={"site": APP_DOMAIN.geturl()},
        # TODO: monitor_celery_beat_tasks=env("SENTRY_MONITOR_CELERY_BEAT_TASKS"),
    )
    SENTRY_CONFIG.init_sentry()


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
        ],
    )
    or env("PYTEST_XDIST_WORKER") is not None
)


# Security Header configuration
SESSION_COOKIE_NAME = f"timur-{APP_ENVIRONMENT}-sessionid"
CSRF_COOKIE_NAME = f"timur-{APP_ENVIRONMENT}-csrftoken"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
CSP_DEFAULT_SRC = ["'self'"]
SECURE_REFERRER_POLICY = "same-origin"
if APP_DOMAIN.scheme == "https":
    SESSION_COOKIE_NAME = f"__Secure-{SESSION_COOKIE_NAME}"
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SECURE_HSTS_SECONDS = 30  # TODO: Increase this slowly
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = TIMUR_TRUSTED_ORIGINS

# https://docs.djangoproject.com/en/3.2/ref/settings/#std:setting-SESSION_COOKIE_DOMAIN
SESSION_COOKIE_DOMAIN = env("SESSION_COOKIE_DOMAIN")
SESSION_COOKIE_AGE = env("SESSION_COOKIE_AGE")
# https://docs.djangoproject.com/en/3.2/ref/settings/#csrf-cookie-domain
CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN")

TOKEN_DEFAULT_RESET_TIMEOUT_DAYS = 7

# EMAIL
SPECIFED_EMAIL_BACKEND: str = env("EMAIL_BACKEND").upper()  # type: ignore[assignment]
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
CELERY_EVENT_QUEUE_PREFIX = "timur-celery-"
CELERY_ACKS_LATE = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True


AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Google SSO
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*"]
ACCOUNT_UNIQUE_EMAIL = True
LOGIN_REDIRECT_URL = APP_FRONTEND_HOST.geturl()

# HEADLESS_ONLY = True

GOOGLE_SSO_ENABLED = env("GOOGLE_SSO_ENABLED")
if env("GOOGLE_SSO_ENABLED"):
    SOCIALACCOUNT_ADAPTER = "main.allauth.SocialAccountAdapter"
    ACCOUNT_EMAIL_VERIFICATION = "none"
    SOCIALACCOUNT_QUERY_EMAIL = True
    SOCIALACCOUNT_AUTO_SIGNUP = True
    SOCIALACCOUNT_ONLY = True

    SOCIALACCOUNT_PROVIDERS = {
        "google": {
            "FETCH_USERINFO": True,
            "EMAIL_AUTHENTICATION": True,
            "EMAIL_AUTHENTICATION_AUTO_CONNECT": True,
            "APP": {
                "verified_email": env("GOOGLE_SSO_ALLOWED_DOMAINS"),
                "client_id": env("GOOGLE_SSO_CLIENT_ID"),
                "secret": env("GOOGLE_SSO_SECRET"),
                "key": "",
            },
        },
    }

# TODO: We need these lines below to allow the Google sign in popup to work.
SECURE_REFERRER_POLICY = "no-referrer-when-downgrade"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"

# Google services
GOOGLE_CREDENTIALS_B64_GZ = env("GOOGLE_CREDENTIALS_B64_GZ")
GOOGLE_CALENDAR_ID = env("GOOGLE_CALENDAR_ID")
GOOGLE_CALENDAR_INCLUDE_DEBUG_IN_EVENT = env("GOOGLE_CALENDAR_INCLUDE_DEBUG_IN_EVENT")

# Health check
REDIS_URL = DJANGO_CACHE_REDIS_URL
HEALTHCHECK_CACHE_KEY = "alert_hub_healthcheck_key"
HEALTH_CHECK = {
    "DISK_USAGE_MAX": env("HEALTH_CHECK_DISK_USAGE_MAX"),
    "MEMORY_MIN": env("HEALTH_CHECK_DISK_MEMORY_MIN"),
}

# Slack
SLACK_BOT_ENABLED = env("SLACK_BOT_ENABLED")
if SLACK_BOT_ENABLED:
    SLACK_BOT_NAME = env("SLACK_BOT_NAME")
    SLACK_BOT_ICON = env("SLACK_BOT_ICON")
    SLACK_BOT_TOKEN = env("SLACK_BOT_TOKEN")
    SLACK_BOT_CHANNEL = env("SLACK_BOT_CHANNEL")

# Daily Standup
DAILY_STANDUP_DOCUMENTATION_REF = env("DAILY_STANDUP_DOCUMENTATION_REF")
DAILY_STANDUP_MEET_LINK = env("DAILY_STANDUP_MEET_LINK")

# Loggging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "render_extra_context": {
            "()": "django.utils.log.CallbackFilter",
            "callback": log_render_custom_field,
        },
    },
    "formatters": {
        "simple": {
            "format": ("%(asctime)s: - %(short_name)s - %(message)s %(context)s"),
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["render_extra_context"],
        },
    },
    "loggers": {
        **{
            app: {
                "level": env("APP_LOG_LEVEL"),
                "handlers": ["console"],
                "propagate": False,
            }
            for app in ["apps", "main", "utils", "celery", "django"]
        },
    },
    "root": {
        "level": env("APP_LOG_LEVEL"),
        "handlers": ["console"],
    },
}

if DEBUG:
    LOGGING = {
        **LOGGING,
        "formatters": {
            **LOGGING["formatters"],  # type: ignore[reportGeneralTypeIssues]
            "colored_verbose": {
                "()": "colorlog.ColoredFormatter",
                "format": ("%(log_color)s%(asctime)s: %(red)s %(short_name)-s%(reset)s %(blue)s%(message)s %(context)s"),
                "datefmt": "%m/%d %H:%M:%S",
            },
        },
        "handlers": {
            **LOGGING["handlers"],  # type: ignore[reportGeneralTypeIssues]
            "colored_console": {
                "class": "logging.StreamHandler",
                "formatter": "colored_verbose",
                "filters": ["render_extra_context"],
            },
        },
        "loggers": {
            **{
                key: {
                    **logger,  # type: ignore[reportGeneralTypeIssues]
                    "handlers": ["colored_console"],
                }
                for key, logger in LOGGING["loggers"].items()  # type: ignore[reportAttributeAccessIssue]
            },
        },
        "root": {
            "level": env("APP_LOG_LEVEL"),
            "handlers": ["colored_console"],
        },
    }
