import datetime

import strawberry
import strawberry_django

from main.graphql.context import Info
from utils.strawberry.paginations import CountList, pagination_field

from .filters import MilestoneFilter, TaskFilter, TimeTrackFilter
from .orders import MilestoneOrder, TaskOrder, TimeTrackOrder
from .types import MilestoneType, TaskType, TimeTrackType


@strawberry.type
class PrivateQuery:
    # Paginated ----------------------------
    milestones: CountList[MilestoneType] = pagination_field(
        pagination=True,
        filters=MilestoneFilter,
        order=MilestoneOrder,
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
    @strawberry_django.field
    async def all_milestones(self, info: Info) -> list[MilestoneType]:
        return [milestone async for milestone in MilestoneType.get_queryset(None, None, info)]

    @strawberry_django.field
    async def all_tasks(self, info: Info) -> list[TaskType]:
        return [task async for task in TaskType.get_queryset(None, None, info)]

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
    async def milestone(self, info: Info, pk: strawberry.ID) -> MilestoneType | None:
        return await MilestoneType.get_queryset(None, None, info).filter(pk=pk).afirst()

    @strawberry_django.field
    async def task(self, info: Info, pk: strawberry.ID) -> TaskType | None:
        return await TaskType.get_queryset(None, None, info).filter(pk=pk).afirst()
