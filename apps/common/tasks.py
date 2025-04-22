import logging

from apps.common.models import Event
from apps.common.utils.google_calendar import GoogleCalendar
from apps.project.models import Deadline

logger = logging.getLogger(__name__)


def sync_with_google_calendar(timur_obj: Event | Deadline, force_update=False):
    TimurModel = type(timur_obj)
    if not force_update and timur_obj.google_calendar_sync_status == TimurModel.GoogleCalendarSyncStatus.SUCCESS:
        logger.warning("Skip google calendar sync.. Already SUCCESS")
        return

    try:
        gc = GoogleCalendar()
        if timur_obj.google_calendar_event_id is None:
            gc.add_event(timur_obj)
        else:
            gc.update_event(timur_obj)
    except Exception:
        logger.error(
            "Failed to sync %s (%s) with google calendar",
            TimurModel.__name__,
            timur_obj.pk,
            exc_info=True,
        )


def delete_from_google_calendar(timur_obj: Event | Deadline):
    TimurModel = type(timur_obj)
    try:
        GoogleCalendar().delete_event(timur_obj)
    except Exception:
        logger.error(
            "Failed to delete %s (%s) from google calendar",
            TimurModel.__name__,
            timur_obj.pk,
            exc_info=True,
        )


def sync_event_with_google_calendar(event: Event, force_update=False):
    return sync_with_google_calendar(event, force_update=force_update)


def delete_event_from_google_calendar(event: Event):
    return delete_from_google_calendar(event)
