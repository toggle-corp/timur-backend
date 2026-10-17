import datetime
import typing

import strawberry
import strawberry_django

from apps.standup.models import DailyUserStandup

from .occupancy import validate_occupancy_range
from .types import (
    DailyStandUpType,
    OccupancyPersonType,
    OccupancyType,
    aget_occupancy_person_type,
    aget_occupancy_type,
)


@strawberry.type
class PrivateQuery:
    # Single ----------------------------
    @strawberry_django.field
    async def daily_standup(self, date: datetime.date) -> DailyStandUpType:
        standup, _ = await DailyUserStandup.objects.aget_or_create(date=date)
        return typing.cast("DailyStandUpType", standup)

    @strawberry_django.field(
        description="Return occupancy for every day within the range, of the users on the standup slides who "
        "joined by its end",
    )
    async def occupancy(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> OccupancyType:
        validate_occupancy_range(start_date, end_date)
        return await aget_occupancy_type(start_date, end_date)

    @strawberry_django.field(
        description="Return the monthly occupancy of a person up to the end date, and their leave this year",
    )
    async def occupancy_person(
        self,
        user_id: strawberry.ID,
        end_date: datetime.date,
    ) -> OccupancyPersonType | None:
        return await aget_occupancy_person_type(int(user_id), end_date)
