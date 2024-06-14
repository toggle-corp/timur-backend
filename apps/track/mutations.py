import strawberry

from main.graphql.context import Info
from utils.common import get_object_or_404_async
from utils.strawberry.mutations import ModelMutation, MutationResponseType

from .serializers import TimeTrackSerializer
from .types import TimeTrackType

TimeTrackMutation = ModelMutation("TimeTrack", TimeTrackSerializer)


@strawberry.type
class PrivateMutation:
    @strawberry.mutation
    async def create_time_track(
        self,
        data: TimeTrackMutation.InputType,  # type: ignore[reportInvalidTypeForm]
        info: Info,
    ) -> MutationResponseType[TimeTrackType]:
        return await TimeTrackMutation.handle_create_mutation(data, info, None)

    @strawberry.mutation
    async def update_time_track(
        self,
        data: TimeTrackMutation.PartialInputType,  # type: ignore[reportInvalidTypeForm]
        info: Info,
    ) -> MutationResponseType[TimeTrackType]:
        queryset = TimeTrackType.get_queryset(None, None, info).filter(user=info.context.request.user)
        instance = await get_object_or_404_async(queryset, id=id)
        return await TimeTrackMutation.handle_update_mutation(data, info, None, instance)
