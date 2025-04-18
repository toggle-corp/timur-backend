import base64
import functools
import gzip
import io
import json
import logging
import typing

from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build

logger = logging.getLogger(__name__)


GoogleCalendarShareRoleType = typing.Literal["reader", "writer", "freeBusyReader"]


class GoogleCalendarInitialisationError(Exception): ...


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
