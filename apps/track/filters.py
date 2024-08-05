import strawberry
import strawberry_django
from django.db import models

from .enums import TimeEntryTaskTypeEnum
from .models import Contract, Task, TimeEntry


@strawberry_django.filters.filter(Contract, lookups=True)
class ContractFilter:
    id: strawberry.auto
    project_id: strawberry.auto
    is_archived: strawberry.auto


@strawberry_django.filters.filter(Task, lookups=True)
class TaskFilter:
    id: strawberry.auto
    contract_id: strawberry.auto
    is_archived: strawberry.auto

    @strawberry_django.filter_field
    def project(
        self,
        queryset: models.QuerySet,
        value: strawberry.ID,
        prefix: str,
    ) -> tuple[models.QuerySet, models.Q]:
        return queryset, models.Q(**{f"{prefix}contract__project": value})


@strawberry_django.filters.filter(TimeEntry, lookups=True)
class TimeEntryFilter:
    id: strawberry.auto
    user: strawberry.auto
    task: strawberry.auto
    date: strawberry.auto

    task_types: list[TimeEntryTaskTypeEnum]  # type: ignore[reportInvalidTypeForm]

    @strawberry_django.filter_field
    def project(
        self,
        queryset: models.QuerySet,
        value: strawberry.ID,
        prefix: str,
    ) -> tuple[models.QuerySet, models.Q]:
        return queryset, models.Q(**{f"{prefix}task__contract__project": value})

    @strawberry_django.filter_field
    def contract(
        self,
        queryset: models.QuerySet,
        value: strawberry.ID,
        prefix: str,
    ) -> tuple[models.QuerySet, models.Q]:
        return queryset, models.Q(**{f"{prefix}task__contract": value})
