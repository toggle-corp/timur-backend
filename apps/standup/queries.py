import datetime

import strawberry
import strawberry_django

from .types import DailyStandUpType


@strawberry.type
class PrivateQuery:
    # Single ----------------------------
    @strawberry_django.field
    async def daily_standup(self, date: datetime.date) -> DailyStandUpType:
        return DailyStandUpType(date=date)
