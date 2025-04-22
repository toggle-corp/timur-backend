import logging

from apps.common.tasks import delete_from_google_calendar, sync_with_google_calendar
from apps.project.models import Deadline

logger = logging.getLogger(__name__)


def sync_deadline_with_google_calendar(deadline: Deadline, force_update=False):
    return sync_with_google_calendar(deadline, force_update=force_update)


def delete_deadline_from_google_calendar(deadline: Deadline):
    return delete_from_google_calendar(deadline)
