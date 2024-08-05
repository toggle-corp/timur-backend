import strawberry

from utils.strawberry.enums import get_enum_name_from_django_field

from .models import TimeEntry

TimeEntryTypeEnum = strawberry.enum(TimeEntry.Type, name="TimeEntryTypeEnum")


enum_map = {get_enum_name_from_django_field(field): enum for field, enum in ((TimeEntry.type, TimeEntryTypeEnum),)}
