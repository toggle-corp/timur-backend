"""
limited but with type hint settings.py
"""

import typing
from dataclasses import dataclass

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
SOCIALACCOUNT_PROVIDERS = typing.cast("dict | None", getattr(settings, "SOCIALACCOUNT_PROVIDERS", None))


# Storage
MEDIA_URL = typing.cast("str", settings.MEDIA_URL)
MEDIA_ROOT = typing.cast("str | None", getattr(settings, "MEDIA_ROOT", None))
STATIC_URL = typing.cast("str", settings.STATIC_URL)
STATIC_ROOT = typing.cast("str | None", getattr(settings, "STATIC_ROOT", None))

# Calendar
GOOGLE_CALENDAR_INCLUDE_DEBUG_IN_EVENT = typing.cast("bool", settings.GOOGLE_CALENDAR_INCLUDE_DEBUG_IN_EVENT)
GOOGLE_CALENDAR_ID = typing.cast("str | None", getattr(settings, "GOOGLE_CALENDAR_ID", None))
GOOGLE_CREDENTIALS_B64_GZ = typing.cast("str | None", getattr(settings, "GOOGLE_CREDENTIALS_B64_GZ", None))

# Sentry
SENTRY_ENABLED = typing.cast("bool", settings.SENTRY_ENABLED)

# Daily Standup
DAILY_STANDUP_DOCUMENTATION_REF = typing.cast("str | None", settings.DAILY_STANDUP_DOCUMENTATION_REF)
DAILY_STANDUP_MEET_LINK = typing.cast("str | None", settings.DAILY_STANDUP_MEET_LINK)


# Slack
class Slack:
    @dataclass
    class SlackConfigDisabled:
        enabled: typing.Literal[False]

    @dataclass
    class SlackConfigEnabled:
        enabled: typing.Literal[True]
        token: str
        channel: str
        bot_name: str | None
        bot_icon: str | None

    SlackConfig = SlackConfigEnabled | SlackConfigDisabled

    @classmethod
    def load_slack_config(cls) -> SlackConfig:
        if settings.SLACK_BOT_ENABLED:
            return cls.SlackConfigEnabled(
                enabled=True,
                token=settings.SLACK_BOT_TOKEN,
                channel=settings.SLACK_BOT_CHANNEL,
                bot_name=settings.SLACK_BOT_NAME,
                bot_icon=settings.SLACK_BOT_ICON,
            )
        return cls.SlackConfigDisabled(enabled=False)
