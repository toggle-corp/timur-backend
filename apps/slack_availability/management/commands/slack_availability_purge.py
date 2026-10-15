import typing

from django.core.management.base import BaseCommand

from apps.slack_availability.tasks import purge_slack_availability_runs
from main.sentry import SentryMonitorConfig, monitor


class Command(BaseCommand):
    help = "Blank message text of Slack availability runs older than SLACK_AVAILABILITY_RETENTION_DAYS"

    @typing.override
    def handle(self, *_, **__):
        with monitor(SentryMonitorConfig.CronJob.SLACK_AVAILABILITY_PURGE):
            updated_count = purge_slack_availability_runs()
        self.stdout.write(self.style.SUCCESS(f"Purged {updated_count} runs"))
