import datetime
import typing

import strawberry
import strawberry_django

from apps.api_token.scopes import ScopeTag, field_scope
from apps.standup.models import DailyUserStandup

from .types import DailyStandUpType


@strawberry.type
class PrivateQuery:
    # Single ----------------------------
    @strawberry_django.field(metadata=field_scope(ScopeTag.SESSION_ONLY))
    async def daily_standup(self, date: datetime.date) -> DailyStandUpType:
        standup, _ = await DailyUserStandup.objects.aget_or_create(date=date)
        return typing.cast("DailyStandUpType", standup)
