import strawberry

from utils.strawberry.enums import get_enum_name_from_django_field

from .models import TimeTrack

TimeTrackTaskTypeEnum = strawberry.enum(TimeTrack.TaskType, name="TimeTrackTaskTypeEnum")


enum_map = {get_enum_name_from_django_field(field): enum for field, enum in ((TimeTrack.task_type, TimeTrackTaskTypeEnum),)}
