import datetime

import strawberry
import strawberry_django

from main.graphql.context import Info
from utils.strawberry.paginations import CountList, pagination_field

from .filters import ContractFilter, TaskFilter, TimeTrackFilter
from .orders import ContractOrder, TaskOrder, TimeTrackOrder
from .types import ContractType, TaskType, TimeTrackType


@strawberry.type
class PrivateQuery:
    # Paginated ----------------------------
    contracts: CountList[ContractType] = pagination_field(
        pagination=True,
        filters=ContractFilter,
        order=ContractOrder,
    )

    tasks: CountList[TaskType] = pagination_field(
        pagination=True,
        filters=TaskFilter,
        order=TaskOrder,
    )

    time_tracks: CountList[TimeTrackType] = pagination_field(
        pagination=True,
        filters=TimeTrackFilter,
        order=TimeTrackOrder,
    )

    # Unbounded ----------------------------
    @strawberry_django.field(description="Return all UnArchived contracts")
    async def all_contracts(self, info: Info) -> list[ContractType]:
        return [contract async for contract in ContractType.get_queryset(None, None, info).filter(is_archived=False)]

    @strawberry_django.field(description="Return all UnArchived tasks")
    async def all_tasks(self, info: Info) -> list[TaskType]:
        qs = TaskType.get_queryset(None, None, info).filter(is_archived=False, contract__is_archived=False)
        return [task async for task in qs]

    @strawberry_django.field
    async def my_time_tracks(self, info: Info, date: datetime.date) -> list[TimeTrackType]:
        qs = (
            TimeTrackType.get_queryset(None, None, info)
            .filter(
                date=date,
                user=info.context.request.user,
            )
            .all()
        )
        return [time_track async for time_track in qs]

    # Single ----------------------------
    @strawberry_django.field
    async def contract(self, info: Info, pk: strawberry.ID) -> ContractType | None:
        return await ContractType.get_queryset(None, None, info).filter(pk=pk).afirst()

    @strawberry_django.field
    async def task(self, info: Info, pk: strawberry.ID) -> TaskType | None:
        return await TaskType.get_queryset(None, None, info).filter(pk=pk).afirst()
