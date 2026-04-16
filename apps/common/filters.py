import strawberry
import strawberry_django
from django.db import models

from .enums import EventTypeEnum
from .models import Event


@strawberry_django.filters.filter(Event, lookups=True)
class EventFilter:
    id: strawberry.auto
    start_date: strawberry.auto
    end_date: strawberry.auto

    @strawberry_django.filter_field
    def types(
        self,
        queryset: models.QuerySet,
        value: list[EventTypeEnum],  # type: ignore[reportInvalidTypeForm]
        prefix: str,
    ) -> tuple[models.QuerySet, models.Q]:
        return queryset, models.Q(**{f"{prefix}type__in": value})
