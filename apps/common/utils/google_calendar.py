import base64
import datetime
import functools
import gzip
import io
import json
import logging
import typing

from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build
from googleapiclient.errors import HttpError as GoogleHttpError

from apps.common.models import Event
from apps.project.models import Deadline
from main.logging import log_extra

if typing.TYPE_CHECKING:
    from googleapiclient._apis.calendar.v3.schemas import (  # type: ignore[reportMissingModuleSource]
        Event as CalendarEvent,
    )

logger = logging.getLogger(__name__)


GoogleCalendarShareRoleType = typing.Literal["owner", "reader", "writer", "freeBusyReader"]


class GoogleCalendarInitialisationError(Exception): ...


CALENDAR_FALLBACK_COLOR_ID = "8"  # #e1e1e1
CALENDAR_COLOR_ID_MAPPING = {
    # Events - type
    (Event, Event.Type.HOLIDAY): "10",  # #51b749
    (Event, Event.Type.RETREAT): "3",  # #dbadff
    (Event, Event.Type.MISC): "8",  # #e1e1e1
    # Deadlines - is_external
    (Deadline, True): "11",  # #dc2127
    (Deadline, False): "4",  # #ff887c
}


CALENDAR_FALLBACK_EMOJI = "❓"
CALENDAR_EMOJI_MAPPING = {
    # Events - type
    (Event, Event.Type.HOLIDAY): "🏖️",
    (Event, Event.Type.RETREAT): "🎉",
    (Event, Event.Type.MISC): "💼",
    # Deadlines - is_external
    (Deadline, True): "🎯",
    (Deadline, False): "📌",
}


class GoogleServiceAccount:
    def __init__(self):
        # Create a Google Calendar service
        self.service_account = self._load_service_account()

    @staticmethod
    @functools.cache
    def _load_service_account():
        logger.info("Loading GOOGLE_CREDENTIALS_B64_GZ")
        gzipped_bytes = base64.b64decode(settings.GOOGLE_CREDENTIALS_B64_GZ)
        with gzip.GzipFile(fileobj=io.BytesIO(gzipped_bytes)) as f:
            json_bytes = f.read()
            service_account_key = json.loads(json_bytes.decode("utf-8"))

        credentials = service_account.Credentials.from_service_account_info(
            service_account_key,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )

        # Create a Google Calendar service
        return google_build("calendar", "v3", credentials=credentials)

    def list_calendar(self):
        calendar_list = self.service_account.calendarList().list().execute()
        return calendar_list.get("items", [])

    def delete_calendar(self, calendar_id) -> bool:
        try:
            self.service_account.calendars().delete(calendarId=calendar_id).execute()
            logger.info("Calendar with ID '%s' has been deleted", calendar_id)
            return True
        except Exception:
            logger.error("Failed to delete calendar with ID '%s'", calendar_id, exc_info=True)
        return False

    def create_calendar(self):
        calendar = {
            "summary": f"Timur - {settings.APP_ENVIRONMENT}",
            "timeZone": settings.TIME_ZONE,
        }
        return (
            self.service_account.calendars()
            .insert(
                body=calendar,  # type: ignore[reportArgumentType]
            )
            .execute()
        )

    def share_calendar(
        self,
        calendar_id: str,
        email: str,
        role: GoogleCalendarShareRoleType,
    ) -> bool:
        rule = {
            "scope": {
                "type": "user",
                "value": email,
            },
            "role": role,
        }

        try:
            created_rule = (
                self.service_account.acl()
                .insert(
                    calendarId=calendar_id,
                    body=rule,  # type: ignore[reportArgumentType]
                )
                .execute()
            )
            logger.info("Shared calendar with %s as %s Rule ID: %s", email, role, created_rule.get("id"))
            return True
        except Exception:
            logger.error("Error sharing calendar with %s as %s", email, role, exc_info=True)
        return False


class GoogleCalendar:
    def __init__(self):
        self.calendar_id: str = settings.GOOGLE_CALENDAR_ID
        if self.calendar_id is None:
            raise GoogleCalendarInitialisationError("GOOGLE_CALENDAR_ID is not defined")

        try:
            self.service = GoogleServiceAccount().service_account
        except Exception as e:
            raise GoogleCalendarInitialisationError("GOOGLE_CREDENTIALS_B64_GZ is not defined or invalid") from e

    @staticmethod
    def _generate_google_calendar_event_data(event: Event | Deadline) -> "CalendarEvent":
        # NOTE: Google calendar will create event till end_date - 1 day
        end_date = event.end_date + datetime.timedelta(days=1)

        # Allowed attributes https://developers.google.com/calendar/api/v3/reference/events
        if isinstance(event, Event):
            map_key = (Event, event.type)
            emoji_icon = CALENDAR_EMOJI_MAPPING.get(map_key, CALENDAR_FALLBACK_EMOJI)
            color_id = CALENDAR_COLOR_ID_MAPPING.get(map_key, CALENDAR_FALLBACK_COLOR_ID)
            start_date = event.start_date
        else:
            map_key = (Deadline, event.is_external)
            emoji_icon = CALENDAR_EMOJI_MAPPING.get(map_key, CALENDAR_FALLBACK_EMOJI)
            color_id = CALENDAR_COLOR_ID_MAPPING.get(map_key, CALENDAR_FALLBACK_COLOR_ID)
            start_date = end_date  # NOTE: Range creates noise in the calendar

        name = f"{emoji_icon} {event.name}"
        description = ""
        return {
            "summary": name,
            "colorId": color_id,
            "description": description,
            # "description": event.description,
            "start": {
                "date": start_date.isoformat(),
            },
            "end": {
                "date": end_date.isoformat(),
            },
            "reminders": {"useDefault": True},
            # TODO: "eventType": "birthday|default"
        }

    # Add an event to Google Calendar
    def add_event(self, timur_obj: Event | Deadline):
        TimurModel = type(timur_obj)
        try:
            calendar_event_data: CalendarEvent = self._generate_google_calendar_event_data(timur_obj)

            calendar_event = (
                self.service.events()
                .insert(
                    calendarId=self.calendar_id,
                    body=calendar_event_data,
                )
                .execute()
            )
            timur_obj.google_calendar_sync_status = TimurModel.GoogleCalendarSyncStatus.SUCCESS
            timur_obj.google_calendar_event_id = calendar_event.get("id")
            timur_obj.google_calendar_html_link = calendar_event.get("htmlLink")
        except Exception:
            timur_obj.google_calendar_sync_status = timur_obj.GoogleCalendarSyncStatus.FAILURE
            logger.error(
                "Failed to add google calendar event",
                exc_info=True,
                extra=log_extra({"event_id": timur_obj.pk}),
            )
        timur_obj.save(
            update_fields=(
                "google_calendar_sync_status",
                "google_calendar_event_id",
                "google_calendar_html_link",
            ),
        )

    # Update an event in Google Calendar
    def update_event(
        self,
        timur_obj: Event | Deadline,
    ):
        TimurModel = type(timur_obj)
        try:
            calendar_event_data = (
                self.service.events()
                .get(
                    calendarId=self.calendar_id,
                    eventId=timur_obj.google_calendar_event_id,
                )
                .execute()
            )

            # Update event details
            calendar_event_data.update(
                self._generate_google_calendar_event_data(timur_obj),
            )

            updated_event = (
                self.service.events()
                .update(
                    calendarId=self.calendar_id,
                    eventId=timur_obj.google_calendar_event_id,
                    body=calendar_event_data,
                )
                .execute()
            )

            timur_obj.google_calendar_sync_status = TimurModel.GoogleCalendarSyncStatus.SUCCESS
            timur_obj.google_calendar_html_link = updated_event.get("htmlLink")
            assert timur_obj.google_calendar_html_link == updated_event.get("htmlLink")
            logger.info("Event updated: %s", timur_obj.google_calendar_html_link)
        except Exception:
            timur_obj.google_calendar_sync_status = TimurModel.GoogleCalendarSyncStatus.FAILURE
            logger.error(
                "Failed to update google calendar event",
                exc_info=True,
                extra=log_extra({"event_id": timur_obj.pk}),
            )
        timur_obj.save(update_fields=("google_calendar_sync_status", "google_calendar_html_link"))

    # Delete an event from Google Calendar
    def delete_event(self, timur_obj: Event | Deadline):
        try:
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=timur_obj.google_calendar_event_id,
            ).execute()
            logger.info("Event with ID '%s' has been deleted", timur_obj.google_calendar_event_id)
            timur_obj.google_calendar_event_id = None
            timur_obj.save(update_fields=("google_calendar_event_id",))
        except GoogleHttpError:
            logger.error("Failed to delete Event with ID '%s'", timur_obj.google_calendar_event_id, exc_info=True)
