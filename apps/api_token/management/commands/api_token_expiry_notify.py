import typing

from django.core.management.base import BaseCommand, CommandError

from apps.api_token.notifications import send_expiry_notices
from main.sentry import SentryMonitorConfig, monitor


class Command(BaseCommand):
    help = "Email users about API tokens that expire within 7 days or have expired"

    @typing.override
    def handle(self, *_, **__):
        with monitor(SentryMonitorConfig.CronJob.API_TOKEN_EXPIRY_NOTIFY):
            result = send_expiry_notices()
            summary = (
                f"Sent {result.expiry_reminders} expiry reminders, {result.expired_notices} expired notices,"
                f" {result.failed} failed"
            )
            if result.failed:
                # Fails the Sentry cron check-in
                raise CommandError(summary)
        self.stdout.write(self.style.SUCCESS(summary))
