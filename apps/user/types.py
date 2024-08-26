import datetime

import strawberry
import strawberry_django
from django.utils import timezone

from apps.common.models import Event
from apps.journal.enums import JournalLeaveTypeEnum, JournalWorkFromHomeTypeEnum
from apps.journal.models import Journal
from main.graphql.context import Info
from utils.strawberry.enums import enum_display_field, enum_field
from utils.strawberry.types import string_field

from .models import User


@strawberry.interface
class UserBaseType:
    # NOTE: Can't use strawberry.auto on interface
    id: strawberry.ID
    first_name = string_field(User.first_name)
    last_name = string_field(User.last_name)
    display_name = string_field(User.display_name)  # type: ignore[reportArgumentType]
    display_picture = string_field(User.display_picture)

    department = enum_field(User.department)
    department_display = enum_display_field(User.department)

    @strawberry.field
    async def leave_today(
        self,
        user: strawberry.Parent[User],
        info: Info,
    ) -> JournalLeaveTypeEnum | None:  # type: ignore[reportInvalidTypeForm]
        return await info.context.dl.journal.load_user_leave_today.load(user.pk)

    @strawberry.field
    async def work_from_home_today(
        self,
        user: strawberry.Parent[User],
        info: Info,
    ) -> JournalWorkFromHomeTypeEnum | None:  # type: ignore[reportInvalidTypeForm]
        return await info.context.dl.journal.load_user_work_from_home_today.load(user.pk)


@strawberry_django.type(User)
class UserType(UserBaseType): ...


@strawberry_django.type(User)
class UserMeType(UserBaseType):
    email: strawberry.auto
    is_staff: strawberry.auto
    is_superuser: strawberry.auto

    @strawberry.field
    async def my_last_working_date(self) -> datetime.date:
        recent_leaves_dates = list(Journal.as_leave_qs(recent_only=True).values_list("date", flat=True).distinct())
        return await Event.aget_last_working_date(
            now_date=timezone.now().date(),
            skip_dates=recent_leaves_dates,
        )
