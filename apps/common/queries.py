import datetime

import strawberry
import strawberry_django
from django.utils import timezone

from utils.strawberry.paginations import CountList, pagination_field

from .filters import EventFilter
from .models import Event
from .orders import EventOrder
from .types import EventType


@strawberry.type
class PrivateQuery:
    # Paginated ----------------------------
    events: CountList[EventType] = pagination_field(
        pagination=True,
        filters=EventFilter,
        order=EventOrder,
    )

    # Unbound ----------------------------
    @strawberry_django.field
    async def relative_events(self) -> list[EventType]:
        now = timezone.now().date()
        start_threshold = now - datetime.timedelta(days=30)
        end_threshold = now + datetime.timedelta(days=30)
        qs = Event.objects.filter(
            start_date__gte=start_threshold,
            end_date__lte=end_threshold,
        )
        return [event async for event in qs]  # type: ignore[reportReturnType]
