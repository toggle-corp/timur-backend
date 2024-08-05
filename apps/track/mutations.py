import strawberry

from main.graphql.context import Info
from utils.common import get_object_or_404_async
from utils.strawberry.mutations import (
    BulkMutationResponseType,
    ModelMutation,
    MutationResponseType,
)

from .serializers import TimeEntryBulkSerializer, TimeEntrySerializer
from .types import TimeEntryType

TimeEntryMutation = ModelMutation("TimeEntry", TimeEntrySerializer)
TimeEntryBulkMutation = ModelMutation("TimeEntryBulk", TimeEntryBulkSerializer)


@strawberry.type
class PrivateMutation:
    @strawberry.mutation
    async def create_time_entry(
        self,
        data: TimeEntryMutation.InputType,  # type: ignore[reportInvalidTypeForm]
        info: Info,
    ) -> MutationResponseType[TimeEntryType]:
        return await TimeEntryMutation.handle_create_mutation(data, info, None)

    @strawberry.mutation
    async def update_time_entry(
        self,
        id: strawberry.ID,
        data: TimeEntryMutation.PartialInputType,  # type: ignore[reportInvalidTypeForm]
        info: Info,
    ) -> MutationResponseType[TimeEntryType]:
        queryset = TimeEntryType.get_queryset(None, None, info).filter(user=info.context.request.user)
        instance = await get_object_or_404_async(queryset, id=id)
        return await TimeEntryMutation.handle_update_mutation(data, info, None, instance)

    @strawberry.mutation
    async def bulk_time_entry(
        self,
        info: Info,
        items: list[TimeEntryBulkMutation.InputType] | None = [],  # type: ignore[reportInvalidTypeForm]
        delete_ids: list[strawberry.ID] | None = [],
    ) -> BulkMutationResponseType[TimeEntryType]:
        queryset = TimeEntryType.get_queryset(None, None, info).filter(user=info.context.request.user)
        return await TimeEntryBulkMutation.handle_bulk_mutation(
            queryset,
            items,
            delete_ids,
            info,
            None,
        )
