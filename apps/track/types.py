import strawberry
import strawberry_django
from django.db import models

from apps.common.types import ClientIdMixin, UserResourceTypeMixin
from apps.project.types import ProjectType
from apps.user.types import UserType
from main.graphql.context import Info
from utils.common import get_queryset_for_model
from utils.strawberry.enums import enum_display_field, enum_field
from utils.strawberry.types import string_field

from .models import Milestone, Task, TimeTrack


@strawberry_django.type(Milestone)
class MilestoneType(UserResourceTypeMixin):
    id: strawberry.ID
    project_id: strawberry.ID
    is_archived: strawberry.auto

    name = string_field(Milestone.name)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Milestone, queryset)

    @strawberry_django.field
    async def project(self, root: Milestone, info: Info) -> ProjectType:
        return info.context.dl.project.load_project.load(root.project_id)


@strawberry_django.type(Task)
class TaskType(UserResourceTypeMixin):
    id: strawberry.ID
    is_archived: strawberry.auto
    milestone_id: strawberry.ID

    name = string_field(Task.name)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Task, queryset)

    @strawberry_django.field
    async def milestone(self, root: Task, info: Info) -> MilestoneType:
        return info.context.dl.track.load_milestone.load(root.milestone_id)


@strawberry_django.type(TimeTrack)
class TimeTrackType(ClientIdMixin):
    id: strawberry.ID
    date: strawberry.auto
    user_id: strawberry.ID
    task_id: strawberry.ID
    is_done: strawberry.auto
    duration: strawberry.auto

    task_type = enum_field(TimeTrack.task_type)
    task_type_display = enum_display_field(TimeTrack.task_type)
    description = string_field(TimeTrack.description)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(TimeTrack, queryset)

    @strawberry_django.field
    async def user(self, root: TimeTrack, info: Info) -> UserType:
        return info.context.dl.user.load_user.load(root.user_id)

    @strawberry_django.field
    async def task(self, root: TimeTrack, info: Info) -> TaskType:
        return info.context.dl.track.load_task.load(root.task_id)
