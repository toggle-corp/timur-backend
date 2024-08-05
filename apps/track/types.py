import strawberry
import strawberry_django
from django.db import models

from apps.common.types import ClientIdMixin, UserResourceTypeMixin
from apps.project.types import ProjectType
from apps.user.types import UserType
from main.graphql.context import Info
from utils.common import get_queryset_for_model
from utils.strawberry.enums import enum_display_field, enum_field
from utils.strawberry.types import TimeDuration, string_field

from .models import Contract, Task, TimeEntry


@strawberry_django.type(Contract)
class ContractType(UserResourceTypeMixin):
    id: strawberry.ID
    project_id: strawberry.ID
    total_estimated_hours: strawberry.auto
    is_archived: strawberry.auto

    name = string_field(Contract.name)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Contract, queryset)

    @strawberry_django.field
    async def project(self, root: Contract, info: Info) -> ProjectType:
        return await info.context.dl.project.load_project.load(root.project_id)

    @strawberry_django.field(description="Sum of all task's estimated hours under this contract")
    async def total_tasks_estimated_hours(self, root: Contract, info: Info) -> float:
        return await info.context.dl.track.load_total_tasks_estimated_hours_by_contract.load(root.pk)


@strawberry_django.type(Task)
class TaskType(UserResourceTypeMixin):
    id: strawberry.ID
    estimated_hours: strawberry.auto
    is_archived: strawberry.auto
    contract_id: strawberry.ID

    name = string_field(Task.name)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Task, queryset)

    @strawberry_django.field
    async def contract(self, root: Task, info: Info) -> ContractType:
        return await info.context.dl.track.load_contract.load(root.contract_id)


@strawberry_django.type(TimeEntry)
class TimeEntryType(ClientIdMixin):
    id: strawberry.ID
    date: strawberry.auto
    user_id: strawberry.ID
    task_id: strawberry.ID
    is_done: strawberry.auto
    start_time: strawberry.auto
    duration: TimeDuration | None

    type = enum_field(TimeEntry.type)
    type_display = enum_display_field(TimeEntry.type)
    description = string_field(TimeEntry.description)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(TimeEntry, queryset)

    @strawberry_django.field
    async def user(self, root: TimeEntry, info: Info) -> UserType:
        return await info.context.dl.user.load_user.load(root.user_id)

    @strawberry_django.field
    async def task(self, root: TimeEntry, info: Info) -> TaskType:
        return await info.context.dl.track.load_task.load(root.task_id)
