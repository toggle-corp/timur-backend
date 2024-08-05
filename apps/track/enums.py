import strawberry

from utils.strawberry.enums import get_enum_name_from_django_field

from .models import TimeEntry

TimeEntryTaskTypeEnum = strawberry.enum(TimeEntry.TaskType, name="TimeEntryTaskTypeEnum")


enum_map = {get_enum_name_from_django_field(field): enum for field, enum in ((TimeEntry.task_type, TimeEntryTaskTypeEnum),)}
