import datetime
import typing

from django.core.management import BaseCommand
from django.utils import timezone
from ulid import ULID

from apps.track.models import TimeEntry
from main.sentry import SentryMonitorConfig, monitor


# TODO: Add test cases
@monitor(SentryMonitorConfig.CronJob.PROCESS_NOT_DONE_TIME_ENTRIES)
class Command(BaseCommand):
    help = "Move past TODO and clone past DOING to today"

    def move_todo_entries(self, today: datetime.date):
        qs = TimeEntry.objects.filter(status=TimeEntry.Status.TODO, date__lt=today)
        resp = qs.update(date=today)
        self.stdout.write(self.style.SUCCESS(f"{resp} TODO moved"))

    def clone_doing_entries(self, today: datetime.date):
        # Only look for yesterday
        qs = TimeEntry.objects.filter(
            status=TimeEntry.Status.DOING,
            date=today - datetime.timedelta(days=1),
        )
        cloned_count = 0
        for time_entry in qs:
            existing_qs = TimeEntry.objects.filter(
                status=TimeEntry.Status.TODO,
                date=today,
                # Fields to check similarity
                type=time_entry.type,
                description=time_entry.description,
            )
            if existing_qs.exists():
                continue
            time_entry.pk = None  # Create a new copy
            time_entry.client_id = str(ULID())
            time_entry.date = today
            time_entry.status = TimeEntry.Status.TODO  # Use todo Status
            # Clear data
            time_entry.start_time = None
            time_entry.duration = None
            # Save
            time_entry.save()
            cloned_count += 1
        self.stdout.write(self.style.SUCCESS(f"{cloned_count} DOING cloned"))

    @typing.override
    def handle(self, **_):
        # XXX: Use the system localtime to figure out the today's date
        # NOTE: timezone.now() will provide datetime with UTC
        # Which can give wrong date compare to local timezone
        today = timezone.localtime(timezone.now()).date()
        self.move_todo_entries(today)
        self.clone_doing_entries(today)
