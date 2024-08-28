import strawberry
import strawberry_django
from django.db import models

from .enums import TimeEntryStatusEnum, TimeEntryTypeEnum
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
    task: strawberry.auto
    date: strawberry.auto

    @strawberry_django.filter_field
    def users(
        self,
        queryset: models.QuerySet,
        value: list[strawberry.ID],  # type: ignore[reportInvalidTypeForm]
        prefix: str,
    ) -> tuple[models.QuerySet, models.Q]:
        return queryset, models.Q(**{f"{prefix}user__in": value})

    @strawberry_django.filter_field
    def types(
        self,
        queryset: models.QuerySet,
        value: list[TimeEntryTypeEnum],  # type: ignore[reportInvalidTypeForm]
        prefix: str,
    ) -> tuple[models.QuerySet, models.Q]:
        return queryset, models.Q(**{f"{prefix}type__in": value})

    @strawberry_django.filter_field
    def statuses(
        self,
        queryset: models.QuerySet,
        value: list[TimeEntryStatusEnum],  # type: ignore[reportInvalidTypeForm]
        prefix: str,
    ) -> tuple[models.QuerySet, models.Q]:
        return queryset, models.Q(**{f"{prefix}status__in": value})

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
