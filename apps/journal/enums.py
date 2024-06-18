import strawberry

from utils.strawberry.enums import get_enum_name_from_django_field

from .models import Journal

JournalLeaveTypeEnum = strawberry.enum(Journal.LeaveType, name="JournalLeaveTypeEnum")


enum_map = {get_enum_name_from_django_field(field): enum for field, enum in ((Journal.leave_type, JournalLeaveTypeEnum),)}
