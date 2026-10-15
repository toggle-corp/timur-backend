"""
limited but with type hint settings.py
"""

import typing
from dataclasses import dataclass

from django.conf import settings

if typing.TYPE_CHECKING:
    from urllib.parse import ParseResult as UrlParseResult

    from main.sentry import SentryConfig


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
SENTRY_CONFIG = typing.cast("SentryConfig | None", getattr(settings, "SENTRY_CONFIG", None))

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
        api_base_url: str | None

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
                api_base_url=settings.SLACK_API_BASE_URL,
            )
        return cls.SlackConfigDisabled(enabled=False)


# Slack availability
class SlackAvailability:
    type Mode = typing.Literal["off", "shadow", "live"]

    @dataclass
    class OllamaConfig:
        base_url: str
        model: str
        api_key: str | None
        timeout_seconds: int
        num_ctx: int
        keep_alive: str

    @dataclass
    class SlackAvailabilityConfig:
        mode: "SlackAvailability.Mode"
        channel_id: str | None
        signing_secret: str | None
        parser: str | None
        retention_days: int

        @property
        def is_off(self) -> bool:
            return self.mode == "off"

        @property
        def is_live(self) -> bool:
            return self.mode == "live"

    @staticmethod
    def load_config() -> SlackAvailabilityConfig:
        return SlackAvailability.SlackAvailabilityConfig(
            mode=settings.SLACK_AVAILABILITY_MODE,
            channel_id=getattr(settings, "SLACK_AVAILABILITY_CHANNEL_ID", None),
            signing_secret=getattr(settings, "SLACK_SIGNING_SECRET", None),
            parser=getattr(settings, "SLACK_AVAILABILITY_PARSER", None),
            retention_days=settings.SLACK_AVAILABILITY_RETENTION_DAYS,
        )

    @staticmethod
    def load_ollama_config() -> OllamaConfig:
        return SlackAvailability.OllamaConfig(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            api_key=getattr(settings, "OLLAMA_API_KEY", None),
            timeout_seconds=getattr(settings, "OLLAMA_TIMEOUT_SECONDS", 60),
            num_ctx=getattr(settings, "OLLAMA_NUM_CTX", 8192),
            keep_alive=getattr(settings, "OLLAMA_KEEP_ALIVE", "10m"),
        )
