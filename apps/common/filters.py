import strawberry
import strawberry_django

from .enums import EventTypeEnum
from .models import Event


@strawberry_django.filters.filter(Event, lookups=True)
class EventFilter:
    id: strawberry.auto
    start_date: strawberry.auto
    end_date: strawberry.auto
    types: list[EventTypeEnum]  # type: ignore[reportInvalidTypeForm]
