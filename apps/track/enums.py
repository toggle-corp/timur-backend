import datetime
import logging
from enum import Enum

import strawberry
from django.utils import timezone

from apps.common.models import Event
from utils.strawberry.enums import get_enum_name_from_django_field

from .models import TimeEntry

TimeEntryTypeEnum = strawberry.enum(TimeEntry.Type, name="TimeEntryTypeEnum")
TimeEntryStatusEnum = strawberry.enum(TimeEntry.Status, name="TimeEntryStatusEnum")


logger = logging.getLogger(__name__)


@strawberry.enum
class TimeEntryDateFilterEnum(Enum):
    LAST_WORKING_DAY = 1
    TODAY = 2

    @classmethod
    def resolve_value(cls, value: "TimeEntryDateFilterEnum") -> datetime.date:
        now_date = timezone.now().date()
        if value == TimeEntryDateFilterEnum.TODAY:
            return now_date
        elif value == TimeEntryDateFilterEnum.LAST_WORKING_DAY:
            return Event.get_last_working_date(now_date=now_date, offset_count=1)


enum_map = {
    get_enum_name_from_django_field(field): enum
    for field, enum in (
        (TimeEntry.type, TimeEntryTypeEnum),
        (TimeEntry.status, TimeEntryStatusEnum),
    )
}
