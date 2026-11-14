import datetime

import strawberry
import strawberry_django
from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.api_token.scopes import ApiTokenScope, ScopeTag, field_scope, type_scope
from apps.common.models import Event
from apps.common.views import get_login_expire
from apps.journal.enums import JournalLeaveTypeEnum, JournalWorkFromHomeTypeEnum
from apps.journal.models import Journal
from main.graphql.context import Info
from utils.strawberry.enums import enum_display_field, enum_field
from utils.strawberry.types import string_field

from .models import User


@type_scope(ApiTokenScope.USER_READ)
@strawberry.interface
class UserBaseType:
    # NOTE: Can't use strawberry.auto on interface
    # Field tags are required because UserMeType (ScopeTag.ROOT) implements this interface.
    id: strawberry.ID = strawberry.field(metadata=field_scope(ScopeTag.NO_SCOPE))
    first_name = string_field(User.first_name, metadata=field_scope(ScopeTag.NO_SCOPE))
    last_name = string_field(User.last_name, metadata=field_scope(ScopeTag.NO_SCOPE))

    @strawberry.field(metadata=field_scope(ScopeTag.NO_SCOPE))
    def display_name(self, user: strawberry.Parent[User]) -> str:
        return User.get_display_name(user.pk, user.display_name)

    display_picture = string_field(User.display_picture, metadata=field_scope(ScopeTag.NO_SCOPE))

    department = enum_field(User.department, metadata=field_scope(ScopeTag.NO_SCOPE))
    department_display = enum_display_field(User.department, metadata=field_scope(ScopeTag.NO_SCOPE))

    @strawberry.field(metadata=field_scope(ApiTokenScope.JOURNAL_READ))
    async def leave_today(
        self,
        user: strawberry.Parent[User],
        info: Info,
    ) -> JournalLeaveTypeEnum | None:  # type: ignore[reportInvalidTypeForm]
        return await info.context.dl.journal.load_user_leave_today.load(user.pk)

    @strawberry.field(metadata=field_scope(ApiTokenScope.JOURNAL_READ))
    async def work_from_home_today(
        self,
        user: strawberry.Parent[User],
        info: Info,
    ) -> JournalWorkFromHomeTypeEnum | None:  # type: ignore[reportInvalidTypeForm]
        return await info.context.dl.journal.load_user_work_from_home_today.load(user.pk)


@type_scope(ApiTokenScope.USER_READ)
@strawberry_django.type(User)
class UserType(UserBaseType): ...


@type_scope(ScopeTag.ROOT)
@strawberry_django.type(User)
class UserMeType(UserBaseType):
    id: strawberry.ID = strawberry_django.field(metadata=field_scope(ScopeTag.NO_SCOPE))
    email: strawberry.auto = strawberry_django.field(metadata=field_scope(ScopeTag.NO_SCOPE))
    is_staff: strawberry.auto = strawberry_django.field(metadata=field_scope(ScopeTag.NO_SCOPE))
    is_superuser: strawberry.auto = strawberry_django.field(metadata=field_scope(ScopeTag.NO_SCOPE))

    @strawberry.field(metadata=field_scope(ApiTokenScope.JOURNAL_READ, ApiTokenScope.EVENT_READ))
    async def my_last_working_date(self) -> datetime.date:
        recent_leaves_dates = list(Journal.as_leave_qs(recent_only=True).values_list("date", flat=True).distinct())
        return await Event.aget_last_working_date(
            now_date=timezone.now().date(),
            skip_dates=recent_leaves_dates,
        )

    @strawberry.field(metadata=field_scope(ScopeTag.SESSION_ONLY))
    async def login_expire(self, info: Info) -> datetime.datetime | None:
        return await sync_to_async(get_login_expire)(info.context.request)
