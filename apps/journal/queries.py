import datetime

import strawberry
import strawberry_django

from apps.api_token.scopes import ApiTokenScope, field_scope
from main.graphql.context import Info

from .types import JournalType


@strawberry.type
class PrivateQuery:
    @strawberry_django.field(metadata=field_scope(ApiTokenScope.JOURNAL_READ))
    async def journal(
        self,
        info: Info,
        date: datetime.date,
    ) -> JournalType | None:
        return (
            await JournalType.get_queryset(None, None, info)
            .filter(
                user=info.context.request.user,
                date=date,
            )
            .afirst()
        )
