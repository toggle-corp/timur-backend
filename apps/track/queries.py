import datetime

import strawberry
import strawberry_django

from main.graphql.context import Info
from utils.strawberry.paginations import CountList, pagination_field

from .filters import ContractFilter, TaskFilter, TimeEntryFilter
from .orders import ContractOrder, TaskOrder, TimeEntryOrder
from .types import ContractType, TaskType, TimeEntryType


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

    time_entries: CountList[TimeEntryType] = pagination_field(
        pagination=True,
        filters=TimeEntryFilter,
        order=TimeEntryOrder,
    )

    # Unbounded ----------------------------
    @strawberry_django.field(description="Return all UnArchived contracts")
    async def all_active_contracts(self, info: Info) -> list[ContractType]:
        qs = ContractType.get_queryset(None, None, info).filter(is_archived=False).order_by("-id")
        return [contract async for contract in qs]

    @strawberry_django.field(description="Return all UnArchived tasks")
    async def all_active_tasks(self, info: Info) -> list[TaskType]:
        qs = TaskType.get_queryset(None, None, info).filter(is_archived=False, contract__is_archived=False).order_by("-id")
        return [task async for task in qs]

    @strawberry_django.field
    async def my_time_entries(self, info: Info, date: datetime.date) -> list[TimeEntryType]:
        qs = (
            TimeEntryType.get_queryset(None, None, info)
            .filter(
                date=date,
                user=info.context.request.user,
            )
            .order_by("-id")
        )
        return [time_entry async for time_entry in qs]

    # Single ----------------------------
    @strawberry_django.field
    async def contract(self, info: Info, pk: strawberry.ID) -> ContractType | None:
        return await ContractType.get_queryset(None, None, info).filter(pk=pk).afirst()

    @strawberry_django.field
    async def task(self, info: Info, pk: strawberry.ID) -> TaskType | None:
        return await TaskType.get_queryset(None, None, info).filter(pk=pk).afirst()
