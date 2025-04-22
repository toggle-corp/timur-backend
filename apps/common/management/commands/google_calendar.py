import json
import logging
import typing

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.common.models import Event
from apps.common.tasks import sync_event_with_google_calendar
from apps.common.utils.google_calendar import GoogleCalendarShareRoleType, GoogleServiceAccount
from apps.project.models import Deadline
from apps.project.tasks import sync_deadline_with_google_calendar

CommandActionType = typing.Literal[
    "list-calendars",
    "list-events",
    "list-colors",
    "list-calendar-access",
    # Mutations
    "create-calendar",
    "share-calendar",
    "delete-calendar",
    "delete-event",
    "sync-timur-data",
    "reset-timur-data",
]

logger = logging.getLogger(__name__)


def list_all_events(service: GoogleServiceAccount, calendar_id, time_min: str | None = None):
    """Generator to yield all events from the calendar."""
    page_token = None
    while True:
        events = (
            service.service_account.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,  # type: ignore[reportArgumentType]
                pageToken=page_token,  # type: ignore[reportArgumentType]
                maxResults=2500,
            )
            .execute()
        )
        yield from events.get("items", [])
        page_token = events.get("nextPageToken")
        if not page_token:
            break


class Command(BaseCommand):
    help = "Initialize google calendar"

    def confirm(self, message: str) -> bool:
        prompt = self.style.NOTICE(f"{message} (y/n): ")
        return input(prompt).strip().lower() == "y"

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="action", help="Actions", required=True)

        subparsers.add_parser("list-calendars", help="List calendars")
        subparsers.add_parser("list-colors", help="List calendars colors")

        list_events_parser = subparsers.add_parser("list-events", help="List calendars colors")
        list_events_parser.add_argument("--time-min", type=str, help="From (eg: 2024-01-01T10:00:00Z)", default=None)

        list_calendar_access_parser = subparsers.add_parser(
            "list-calendar-access",
            help="List users with access to calendar",
        )
        list_calendar_access_parser.add_argument("--calendar-id", type=str, default=None, help="Calendar ID (Optional)")
        list_calendar_access_parser.add_argument("--compact", action="store_true")

        subparsers.add_parser("create-calendar", help="Create new calendar")

        share_calendar_parser = subparsers.add_parser("share-calendar", help="Create new calendar")
        share_calendar_parser.add_argument("emails", type=str, help="User Emails (Seperated by comma)")
        share_calendar_parser.add_argument(
            "role",
            type=str,
            choices=typing.get_args(GoogleCalendarShareRoleType),
            help="Role for using when inviting",
        )
        share_calendar_parser.add_argument("--calendar-id", type=str, default=None, help="Calendar ID (Optional)")

        delete_calendar_parser = subparsers.add_parser("delete-calendar", help="Delete calendar")
        delete_calendar_parser.add_argument("calendar-id", type=str, help="Calendar id to delete")

        delete_event_parser = subparsers.add_parser("delete-event", help="Delete calendar")
        delete_event_parser.add_argument("event-id", type=str, help="Event id to delete")

        sync_timur_data_parser = subparsers.add_parser(
            "sync-timur-data",
            help="Sync timur data (events, deadlines) with google calendar",
        )
        sync_timur_data_parser.add_argument("--force-update", action="store_true")
        sync_timur_data_parser.add_argument("--events", action="store_true")
        sync_timur_data_parser.add_argument("--deadlines", action="store_true")
        sync_timur_data_parser.add_argument("--all", action="store_true")

        subparsers.add_parser("reset-timur-data", help="List calendars")

    def list_calendars(self, service: GoogleServiceAccount):
        logger.info("Action calendar ID: %s", settings.GOOGLE_CALENDAR_ID)
        for cal in service.list_calendar():
            self.stdout.write(json.dumps(cal, indent=2))

    def create_calendar(self, service: GoogleServiceAccount):
        new_calendar = service.create_calendar()
        self.stdout.write(json.dumps(new_calendar, indent=2))

    def share_calendar(
        self,
        service: GoogleServiceAccount,
        **options: dict,
    ):
        emails = typing.cast("str", options["emails"])
        role = typing.cast("GoogleCalendarShareRoleType", options["role"])
        calendar_id = typing.cast(
            "str",
            options.get("calendar_id") or settings.GOOGLE_CALENDAR_ID,
        )

        if role == "owner":
            confirm_message = f"Are you sure? You want to add <{emails}> as {role}?"
            if not self.confirm(confirm_message):
                self.stderr.write(self.style.ERROR("Skipped"))
                return

        for email in emails.split(","):
            success = service.share_calendar(calendar_id, email, role)
            if success:
                self.stdout.write(self.style.SUCCESS("Calendar has been shared"))
            else:
                self.stderr.write(self.style.ERROR("Failed to share"))

    def delete_calendar(self, service: GoogleServiceAccount, **options):
        calendar_id = options["calendar-id"]

        # FIXME: Show events count?
        if self.confirm("Are you sure?"):
            if service.delete_calendar(calendar_id):
                self.stdout.write(self.style.SUCCESS("Calendar has been deleted"))
                return
            self.stderr.write(self.style.ERROR("Failed to delete"))
            return
        self.stdout.write(self.style.ERROR("Skipped"))

    def list_events(self, service: GoogleServiceAccount, **options):
        time_min = options["time_min"]
        google_calendar_events = list_all_events(
            service,
            calendar_id=settings.GOOGLE_CALENDAR_ID,
            time_min=time_min,
        )
        for result in google_calendar_events:
            self.stdout.write(json.dumps(result, indent=2))

    def list_colors(self, service: GoogleServiceAccount):
        results = service.service_account.colors().get().execute()
        self.stdout.write(json.dumps(list(results.items()), indent=2))

    def list_calendar_access(self, service: GoogleServiceAccount, **options):
        calendar_id = options.get("calendar_id") or settings.GOOGLE_CALENDAR_ID
        compact = options.get("compact", False)

        results = service.service_account.acl().list(calendarId=calendar_id).execute()
        for result in results.get("items", []):
            if compact:
                scope = result.get("scope") or {}
                role = typing.cast("GoogleCalendarShareRoleType", result.get("role"))
                scope_type = scope.get("type")
                scope_value = scope.get("value", "N/A")
                _role = self.style.SUCCESS(role)
                if role in ["writer", "owner"]:
                    _role = self.style.ERROR(role)
                self.stdout.write(f"- {scope_type}: {scope_value} → {_role}")
            else:
                self.stdout.write(json.dumps(result, indent=2))

    def delete_event(self, service: GoogleServiceAccount, **options):
        event_id = options["event-id"]

        if self.confirm("Are you sure?"):
            service.service_account.events().delete(
                calendarId=settings.GOOGLE_CALENDAR_ID,
                eventId=event_id,
            ).execute()

            self.stdout.write(self.style.SUCCESS("Calendar event has been deleted"))
            return
        self.stdout.write(self.style.ERROR("Skipped"))

    def _sync_timur_events(self, force_update):
        self.stdout.write("Syncing timur events with google calendar")

        to_process_qs = Event.objects.all()

        if not force_update:
            to_process_qs = to_process_qs.exclude(google_calendar_sync_status=Event.GoogleCalendarSyncStatus.SUCCESS)
        elif not self.confirm(f"Are you sure? This will update {to_process_qs.count()} events"):
            return

        if to_process_qs.count() == 0:
            self.stdout.write(" - All up-to-date")
            return

        total_count = to_process_qs.count()
        for index, event in enumerate(to_process_qs.iterator(), start=1):
            sync_event_with_google_calendar(event, force_update=force_update)
            self.stdout.write(f" - [{index}/{total_count}]: {event.get_google_calendar_sync_status_display()} - {event}")

    def _sync_timur_deadlines(self, force_update):
        self.stdout.write("Syncing timur deadlines with google calendar")

        to_process_qs = Deadline.objects.all()

        if not force_update:
            to_process_qs = to_process_qs.exclude(google_calendar_sync_status=Deadline.GoogleCalendarSyncStatus.SUCCESS)
        elif not self.confirm(f"Are you sure? This will update {to_process_qs.count()} deadlines"):
            return

        if to_process_qs.count() == 0:
            self.stdout.write(" - All up-to-date")

        total_count = to_process_qs.count()
        for index, deadline in enumerate(to_process_qs.iterator(), start=1):
            sync_deadline_with_google_calendar(deadline, force_update=force_update)
            self.stdout.write(
                f" - [{index}/{total_count}]: "
                + deadline.get_google_calendar_sync_status_display()
                + f" - {deadline.display_name}",
            )

    def sync_timur_data(self, **options):
        force_update = options["force_update"]
        process_all = options["all"]
        process_events = process_all or options["events"]
        process_deadlines = process_all or options["deadlines"]

        if process_events:
            self._sync_timur_events(force_update)

        if process_deadlines:
            self._sync_timur_deadlines(force_update)

    def reset_timur_data(self, service: GoogleServiceAccount):
        to_process_event_qs = Event.objects.filter(google_calendar_event_id__isnull=False).all()
        to_process_deadline_qs = Deadline.objects.filter(google_calendar_event_id__isnull=False).all()
        summary = {
            "events": to_process_event_qs.count(),
            "deadlines": to_process_deadline_qs.count(),
        }

        calendar_id = settings.GOOGLE_CALENDAR_ID
        if not self.confirm(f"Are you sure? This will remove {summary}"):
            return

        self.stdout.write("Deleting events from google calendar")
        google_calendar_events = list_all_events(service, calendar_id=calendar_id)
        google_calendar_events_deleted_counts = 0
        for event in google_calendar_events:
            event_id = event.get("id")
            if event_id is None:
                continue

            try:
                service.service_account.events().delete(calendarId=calendar_id, eventId=event_id).execute()
                self.stdout.write(f" - Deleted event: {event.get('summary', 'No Title')}")
                google_calendar_events_deleted_counts += 1
            except Exception:
                logger.warning("Failed to delete event ID %s", event_id, exc_info=True)
            self.stdout.write(f"Total events delete from google calendar: {google_calendar_events_deleted_counts}")

        # Clean-up the database
        events_resp = to_process_event_qs.update(
            google_calendar_event_id=None,
            google_calendar_html_link=None,
            google_calendar_sync_status=Event.GoogleCalendarSyncStatus.PENDING,
        )

        deadline_resp = to_process_deadline_qs.update(
            google_calendar_event_id=None,
            google_calendar_html_link=None,
            google_calendar_sync_status=Deadline.GoogleCalendarSyncStatus.PENDING,
        )

        self.stdout.write(f" - Success {events_resp}")
        self.stdout.write(f" - Success {deadline_resp}")

    def handle(self, action: CommandActionType, **options):
        gsc = GoogleServiceAccount()

        match action:
            case "list-calendars":
                return self.list_calendars(gsc)
            case "list-colors":
                return self.list_colors(gsc)
            case "list-events":
                return self.list_events(gsc, **options)
            case "list-calendar-access":
                return self.list_calendar_access(gsc, **options)
            # Mutations
            case "create-calendar":
                return self.create_calendar(gsc)
            case "share-calendar":
                return self.share_calendar(gsc, **options)
            case "delete-calendar":
                return self.delete_calendar(gsc, **options)
            case "delete-event":
                return self.delete_event(gsc, **options)
            case "sync-timur-data":
                return self.sync_timur_data(**options)
            case "reset-timur-data":
                return self.reset_timur_data(gsc)
            case _:
                typing.assert_never(action)
