"""
limited but with type hint settings.py
"""

import typing

from django.conf import settings

if typing.TYPE_CHECKING:
    from urllib.parse import ParseResult as UrlParseResult


DEBUG = typing.cast("bool", settings.DEBUG)
APP_DOMAIN = typing.cast("UrlParseResult", settings.APP_DOMAIN)
APP_FRONTEND_HOST = typing.cast("UrlParseResult", settings.APP_FRONTEND_HOST)
APP_ENVIRONMENT = typing.cast("str", settings.APP_ENVIRONMENT)
TIME_ZONE = typing.cast("str", settings.TIME_ZONE)

# SSO
GOOGLE_SSO_ENABLED = typing.cast("bool", settings.GOOGLE_SSO_ENABLED)
SOCIALACCOUNT_PROVIDERS = typing.cast("dict | None", settings.SOCIALACCOUNT_PROVIDERS)


# Storage
MEDIA_URL = typing.cast("str", settings.MEDIA_URL)
MEDIA_ROOT = typing.cast("str | None", settings.MEDIA_ROOT)
STATIC_URL = typing.cast("str", settings.STATIC_URL)
STATIC_ROOT = typing.cast("str | None", settings.STATIC_ROOT)

# Calendar
GOOGLE_CALENDAR_INCLUDE_DEBUG_IN_EVENT = typing.cast("bool", settings.GOOGLE_CALENDAR_INCLUDE_DEBUG_IN_EVENT)
GOOGLE_CALENDAR_ID = typing.cast("str | None", settings.GOOGLE_CALENDAR_ID)
GOOGLE_CREDENTIALS_B64_GZ = typing.cast("str | None", settings.GOOGLE_CREDENTIALS_B64_GZ)

# Sentry
SENTRY_ENABLED = typing.cast("bool", settings.SENTRY_ENABLED)
