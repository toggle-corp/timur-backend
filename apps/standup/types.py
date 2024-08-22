import datetime

import strawberry
import strawberry_django
from django.db import models
from django.utils import timezone

from apps.common.types import UserResourceTypeMixin
from apps.journal.enums import JournalLeaveTypeEnum, JournalWorkFromHomeTypeEnum
from apps.project.models import Project
from apps.project.types import ProjectType
from apps.standup.models import Quote
from apps.track.models import TimeEntry
from apps.user.models import User
from main.graphql.context import Info
from utils.common import get_queryset_for_model
from utils.strawberry.types import string_field


@strawberry_django.type(Quote)
class QuoteType(UserResourceTypeMixin):
    id: strawberry.ID

    text = string_field(Quote.text)
    author = string_field(Quote.author)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Quote, queryset)


@strawberry.type
class DailyStandUpProjectStatUserType:
    user_obj: strawberry.Private[User]
    date: strawberry.Private[datetime.date]

    @strawberry.field
    def id(self) -> strawberry.ID:
        return strawberry.ID(str(self.user_obj.pk))

    @strawberry.field
    def display_picture(self) -> str | None:
        return self.user_obj.display_picture

    @strawberry.field
    def display_name(self) -> str:
        return self.user_obj.display_name

    @strawberry.field
    async def leave(self, info: Info) -> JournalLeaveTypeEnum | None:  # type: ignore[reportInvalidTypeForm]
        return await info.context.dl.journal.load_user_leave.load((self.user_obj.pk, self.date))

    @strawberry.field
    async def work_from_home(self, info: Info) -> JournalWorkFromHomeTypeEnum | None:  # type: ignore[reportInvalidTypeForm]
        return await info.context.dl.journal.load_user_work_from_home.load((self.user_obj.pk, self.date))


@strawberry.type
class DailyStandUpProjectStatType:
    project_obj: strawberry.Private[Project]
    date: strawberry.Private[datetime.date]

    @strawberry.field
    def project(self) -> ProjectType:
        return self.project_obj  # type: ignore[reportReturnType]

    @strawberry.field
    async def users(self) -> list[DailyStandUpProjectStatUserType]:
        threshold = timezone.now() - datetime.timedelta(days=3)
        time_entries_qs = (
            TimeEntry.objects.filter(
                task__contract__project=self.project_obj,
                date__gte=threshold,
            )
            .values("user")
            .distinct()
        )
        return [
            DailyStandUpProjectStatUserType(user_obj=user, date=self.date)
            async for user in User.objects.filter(id__in=time_entries_qs).all()
        ]


@strawberry.type
class DailyStandUpType:
    date: strawberry.Private[datetime.date]

    def id(self) -> strawberry.ID:
        return strawberry.ID(self.date.isoformat())

    # TODO: primary_conductor
    # TODO: secondary_conductor

    @strawberry.field
    async def quote(self, info: Info) -> QuoteType | None:
        return await QuoteType.get_queryset(None, None, info).order_by("?").afirst()

    @strawberry.field
    async def project_stat(self, info: Info, pk: strawberry.ID) -> DailyStandUpProjectStatType | None:
        project = await ProjectType.get_queryset(None, None, info).filter(pk=pk).afirst()
        if project:
            return DailyStandUpProjectStatType(project_obj=project, date=self.date)
