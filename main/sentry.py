import dataclasses
import json
import logging
import typing
from difflib import context_diff
from functools import lru_cache
from pathlib import Path

import sentry_sdk
import yaml
from asgiref.sync import sync_to_async
from banjo_utils.health import make_sentry_traces_sampler_with_health_probe_ignore
from django.db import models
from sentry_sdk import Scope, set_user
from sentry_sdk.crons import monitor as og_monitor
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.strawberry import StrawberryIntegration

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from sentry_sdk._types import MonitorConfig  # type: ignore[reportPrivateImportUsage]


BASE_DIR = Path(__file__).resolve().parent.parent

helm_values_path = BASE_DIR / "helm/values.yaml"


IGNORED_ERRORS = []
IGNORED_LOGGERS = [
    "graphql.execution.utils",
    "strawberry.http.exceptions.HTTPException",
]

for _logger in IGNORED_LOGGERS:
    ignore_logger(_logger)


# TODO: Not tested
def sentry_before_send(event, hint):
    # Check if the exception is a GraphQLError
    if "exception" in event and isinstance(event["exception"], dict):
        for value in event["exception"].get("values", []):
            if value.get("type") == "GraphQLError":
                # Return None to prevent sending the GraphQLError to Sentry
                return None
    return event


@dataclasses.dataclass
class SentryConfig:
    dsn: str
    release: str | None
    environment: str
    send_default_pii: bool
    monitor_cron_tasks: bool
    traces_sample_rate: float
    profiles_sample_rate: float
    debug: bool
    # Custom configs
    # TODO: monitor_celery_beat_tasks: bool
    app_type: str
    tags: dict[str, str]

    def init_sentry(self):
        integrations = [
            DjangoIntegration(),
            RedisIntegration(),
            StrawberryIntegration(async_execution=True),
            CeleryIntegration(),
            # TODO: CeleryIntegration(monitor_beat_tasks=self.monitor_celery_beat_tasks),
        ]
        sentry_sdk.init(
            ignore_errors=IGNORED_ERRORS,
            integrations=integrations,
            dsn=self.dsn,
            release=self.release,
            environment=self.environment,
            send_default_pii=self.send_default_pii,
            # Ignore k8s health-probe (/healthz/*) requests so they don't consume tracing quota.
            traces_sampler=make_sentry_traces_sampler_with_health_probe_ignore(self.traces_sample_rate),
            profiles_sample_rate=self.profiles_sample_rate,
            before_send=sentry_before_send,
            debug=self.debug,
        )
        with sentry_sdk.configure_scope() as scope:
            scope.set_tag("app_type", self.app_type)
            for tag, value in self.tags.items():
                scope.set_tag(tag, value)


class SentryTransactionMiddlewareHelper:
    @classmethod
    @sync_to_async
    def atrack_transaction(cls, graphql_urls: set[str], request):
        return cls.track_transaction(graphql_urls, request)

    @staticmethod
    def track_transaction(graphql_urls: set[str], request):
        if request.path in graphql_urls:
            operation_type = "Query"
            operation_name = "Unknown"
            try:
                body = request.body.decode("utf-8")
                if body:
                    # XXX: This will be repeated by Strawberry as well.
                    data = json.loads(body)
                    operation_name = data.get("operationName", operation_name)
                    if data.get("query", "").startswith("mutation"):
                        operation_type = "Mutation"
            except Exception:
                ...

            scope = Scope.get_current_scope()
            scope.set_transaction_name(f"GraphQL/{operation_type}/{operation_name}")
            if (user := request.user) and user.pk:
                set_user(
                    {
                        "id": user.pk,
                        "email": user.email,
                        "is_superuser": user.is_superuser,
                    },
                )


class SentryMonitorConfig:
    """
    Custom config for SentryMonitor
    https://docs.sentry.io/product/crons/getting-started/http/#creating-or-updating-a-monitor-through-a-check-in-optional
    """

    class CronJob(models.TextChoices):
        PROCESS_NOT_DONE_TIME_ENTRIES = "process_not_done_time_entries"
        CLEARSESSIONS = "clearsessions"
        USER_SYNC_SLACK_USERS_ID = "user_sync_slack_users_id"
        STANDUP_MORNING_REMINDER = "standup_morning_reminder"
        STANDUP_BEFORE_STANDUP_REMINDER = "standup_before_standup_reminder"
        STANDUP_SETUP_NEXT_STANDUP = "standup_setup_next_standup"
        STANDUP_READ_DOC_REMINDER = "standup_read_doc_reminder"

    class CronConfig(typing.NamedTuple):
        checkin_margin: int = 5
        """
        The amount of time (in minutes) Sentry should wait for your check-in before it's considered missed ("grace period").
        Optional.
        """

        max_runtime: int = 30
        """The amount of time (in minutes) your job is allowed to run before it's considered failed. Optional."""

        failure_issue_threshold: int = 1
        """The number of consecutive failed check-ins it takes before an issue is created. Optional."""

        recovery_threshold: int = 1
        """The number of consecutive OK check-ins it takes before an issue is resolved. Optional."""

        def as_dict(self) -> "MonitorConfig":
            return {
                "checkin_margin": self.checkin_margin,
                "max_runtime": self.max_runtime,
                "failure_issue_threshold": self.failure_issue_threshold,
                "recovery_threshold": self.recovery_threshold,
            }

    def __init__(self):
        self.cron_data = self.load_cron_data()
        self.validate_config()

    def validate_config(self):
        code_config = [job_name for job_name, _ in self.CronJob.choices]
        helm_config = list(self.cron_data.keys())
        assert code_config == helm_config, (
            # Show a simple diff for correction
            "SentryMonitorConfig.CronJob needs update\n\n"
            + (
                "\n".join(
                    list(
                        context_diff(
                            code_config,
                            helm_config,
                            fromfile=__file__,
                            tofile=str(helm_values_path),
                        ),
                    ),
                )
            )
        )

    @staticmethod
    def load_cron_data() -> dict[str, str]:
        with Path.open(helm_values_path) as fp:
            try:
                yaml_data = yaml.safe_load(fp)
                return {
                    name: metadata["schedule"]
                    for name, metadata in yaml_data["app"]["cronjobs"]["jobs"].items()
                    if metadata["enabled"]
                }
            except yaml.YAMLError as e:
                logger.error("Failed to load cronjob data from helm", exc_info=True)
                raise e

    def get_cron_config(
        self,
        job_name: str,
        cron_config: CronConfig | None = None,
    ) -> "MonitorConfig":
        from django.conf import settings

        schedule = self.cron_data[job_name]
        if cron_config is None:
            cron_config = SentryMonitorConfig.CronConfig()

        return {
            "schedule": {
                "type": "crontab",
                "value": schedule,
            },
            "timezone": settings.TIME_ZONE,
            **cron_config.as_dict(),
        }


sentry_monitor_config = SentryMonitorConfig()


class monitor(og_monitor):
    def __init__(
        self,
        monitor_slug: str,
        *,
        monitor_config: SentryMonitorConfig.CronConfig | None = None,
    ):
        if monitor_config is None:
            monitor_config = SentryMonitorConfig.CronConfig()

        self.monitor_slug = monitor_slug
        self.monitor_config = sentry_monitor_config.get_cron_config(
            monitor_slug,
            monitor_config,
        )

    @staticmethod
    @lru_cache(maxsize=1)
    def is_monitor_enabled():
        from main.config import SENTRY_CONFIG

        return not (SENTRY_CONFIG is None or not SENTRY_CONFIG.monitor_cron_tasks)

    @typing.override
    def __enter__(self):
        if self.is_monitor_enabled():
            super().__enter__()

    @typing.override
    def __exit__(self, exc_type, exc_value, traceback):
        if self.is_monitor_enabled():
            super().__exit__(exc_type, exc_value, traceback)
