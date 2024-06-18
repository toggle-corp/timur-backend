import datetime

import strawberry

from main.graphql.context import Info
from utils.strawberry.mutations import ModelMutation, MutationResponseType

from .serializers import JournalSerializer
from .types import JournalType

JournalMutation = ModelMutation("Journal", JournalSerializer)


@strawberry.type
class PrivateMutation:

    @strawberry.mutation
    async def update_journal(
        self,
        date: datetime.date,
        data: JournalMutation.PartialInputType,  # type: ignore[reportInvalidTypeForm]
        info: Info,
    ) -> MutationResponseType[JournalType]:
        queryset = JournalType.get_queryset(None, None, info).filter(
            user=info.context.request.user,
            date=date,
        )
        context = {"journal_date": date}
        if instance := await queryset.afirst():
            return await JournalMutation.handle_update_mutation(data, info, None, instance, extra_context=context)
        return await JournalMutation.handle_create_mutation(data, info, None, extra_context=context)
