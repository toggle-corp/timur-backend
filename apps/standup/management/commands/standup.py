import logging
import typing

from django.core.management.base import BaseCommand

from apps.standup.tasks import (
    before_standup_reminder,
    morning_reminder,
    read_doc_reminder,
    setup_next_standup,
)
from main.sentry import SentryMonitorConfig, monitor

CommandActionType = typing.Literal[
    "morning-reminder",
    "before-standup-reminder",
    "setup-next-standup",
    "read-doc-reminder",
]

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Daily Standup cli"

    @typing.override
    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="action", help="Actions", required=True)

        subparsers.add_parser("morning-reminder", help="Send morning reminder for conductors")
        subparsers.add_parser("before-standup-reminder", help="Send before standup reminder for the team")
        subparsers.add_parser("setup-next-standup", help="Setup next standup and assign conductors")
        subparsers.add_parser("read-doc-reminder", help="Send read doc reminder for conductors")

    @typing.override
    def handle(self, action: CommandActionType, **_):
        match action:
            case "morning-reminder":
                with monitor(SentryMonitorConfig.CronJob.STANDUP_MORNING_REMINDER):
                    return morning_reminder()
            case "before-standup-reminder":
                with monitor(SentryMonitorConfig.CronJob.STANDUP_BEFORE_STANDUP_REMINDER):
                    return before_standup_reminder()
            case "setup-next-standup":
                with monitor(SentryMonitorConfig.CronJob.STANDUP_SETUP_NEXT_STANDUP):
                    return setup_next_standup()
            case "read-doc-reminder":
                with monitor(SentryMonitorConfig.CronJob.STANDUP_READ_DOC_REMINDER):
                    return read_doc_reminder()
            case _:
                typing.assert_never(action)
