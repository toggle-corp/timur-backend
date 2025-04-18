import json
import logging
import typing

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.common.utils.google_calendar import GoogleCalendarShareRoleType, GoogleServiceAccount

CommandActionType = typing.Literal[
    "list-calendars",
    "list-events",
    "list-colors",
    # Mutations
    "create-calendar",
    "share-calendar",
    "delete-calendar",
    "delete-event",
]

logger = logging.getLogger(__name__)


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
        list_events_parser.add_argument("time_min", type=str, help="From (eg: 2024-01-01T10:00:00Z)")
        list_events_parser.add_argument("--max-results", type=str, default=10)

        subparsers.add_parser("create-calendar", help="Create new calenadr")

        share_calendar_parser = subparsers.add_parser("share-calendar", help="Create new calendar")
        share_calendar_parser.add_argument("email", type=str, help="User Email")
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
        email = options["email"]
        role = options["role"]
        calendar_id = options.get("calendar_id") or settings.GOOGLE_CALENDAR_ID

        success = service.share_calendar(calendar_id, email, role)  # type: ignore[reportArgumentType]
        if success:
            self.stdout.write(self.style.SUCCESS("Calendar has been shared"))
            return
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
        max_results = options["max_results"]
        # "2024-01-01T10:00:00Z"
        results = (
            service.service_account.events()
            .list(
                calendarId=settings.GOOGLE_CALENDAR_ID,
                timeMin=time_min,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        for result in results.get("items", []):
            self.stdout.write(json.dumps(result, indent=2))

    def list_colors(self, service: GoogleServiceAccount):
        results = service.service_account.colors().get().execute()
        self.stdout.write(json.dumps(list(results.items()), indent=2))

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

    def handle(self, action: CommandActionType, **options):
        gsc = GoogleServiceAccount()

        match action:
            case "list-calendars":
                return self.list_calendars(gsc)
            case "list-colors":
                return self.list_colors(gsc)
            case "list-events":
                return self.list_events(gsc, **options)
            # Mutations
            case "create-calendar":
                return self.create_calendar(gsc)
            case "share-calendar":
                return self.share_calendar(gsc, **options)
            case "delete-calendar":
                return self.delete_calendar(gsc, **options)
            case "delete-event":
                return self.delete_event(gsc, **options)
            case _:
                typing.assert_never(action)
