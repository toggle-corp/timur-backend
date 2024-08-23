import strawberry
import strawberry_django

from main.graphql.context import Info
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
    async def relative_events(self, info: Info) -> list[EventType]:
        return [event async for event in Event.get_relative_events()]  # type: ignore[reportReturnType]
