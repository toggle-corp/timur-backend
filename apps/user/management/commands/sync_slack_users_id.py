import csv
import sys
import typing

from django.core.management.base import BaseCommand

from apps.user.models import User
from apps.user.tasks import sync_slack_users_id
from main.sentry import SentryMonitorConfig, monitor


@monitor(SentryMonitorConfig.CronJob.USER_SYNC_SLACK_USERS_ID)
class Command(BaseCommand):
    help = "Fetch and store slack user id"

    @typing.override
    def add_arguments(self, parser):
        parser.add_argument("--only-list", action="store_true", help="List existing local data")

    @typing.override
    def handle(self, *_, **options):
        if options["only_list"]:
            fieldnames = ["id", "email", "slack_user_id"]
            csv_writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            csv_writer.writeheader()
            for row in User.get_active_user_qs().values(*fieldnames):
                csv_writer.writerow(row)
            return

        self.stdout.write("Processing....")
        sync_slack_users_id()
        self.stdout.write(self.style.SUCCESS("Success"))
