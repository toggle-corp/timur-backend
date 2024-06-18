import datetime

import strawberry
import strawberry_django

from main.graphql.context import Info

from .types import JournalType


@strawberry.type
class PrivateQuery:
    @strawberry_django.field
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
