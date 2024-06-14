import strawberry
import strawberry_django
from django.db import models

from .enums import TimeTrackTaskTypeEnum
from .models import Milestone, Task, TimeTrack


@strawberry_django.filters.filter(Milestone, lookups=True)
class MilestoneFilter:
    id: strawberry.auto
    project_id: strawberry.auto


@strawberry_django.filters.filter(Task, lookups=True)
class TaskFilter:
    id: strawberry.auto
    milestone_id: strawberry.auto

    @strawberry_django.filter_field
    def project(
        self,
        queryset: models.QuerySet,
        value: strawberry.ID,
        prefix: str,
    ) -> tuple[models.QuerySet, models.Q]:
        return queryset, models.Q(**{f"{prefix}milestone__project": value})


@strawberry_django.filters.filter(TimeTrack, lookups=True)
class TimeTrackFilter:
    id: strawberry.auto
    user: strawberry.auto
    task: strawberry.auto
    date: strawberry.auto

    task_types: list[TimeTrackTaskTypeEnum]  # type: ignore[reportInvalidTypeForm]

    @strawberry_django.filter_field
    def project(
        self,
        queryset: models.QuerySet,
        value: strawberry.ID,
        prefix: str,
    ) -> tuple[models.QuerySet, models.Q]:
        return queryset, models.Q(**{f"{prefix}task__milestone__project": value})

    @strawberry_django.filter_field
    def milestone(
        self,
        queryset: models.QuerySet,
        value: strawberry.ID,
        prefix: str,
    ) -> tuple[models.QuerySet, models.Q]:
        return queryset, models.Q(**{f"{prefix}task__milestone": value})
