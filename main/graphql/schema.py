import strawberry
from django.core.cache import cache
from strawberry.django.views import AsyncGraphQLView

# Imported to make sure strawberry custom modules are loadded first
import utils.strawberry.transformers  # pyright: ignore[reportUnusedImport] # type: ignore # noqa F401
from apps.common import queries as common_queries
from apps.common.models import Event
from apps.journal import mutations as journal_mutations
from apps.journal import queries as journal_queries
from apps.project import queries as project_queries
from apps.standup import queries as standup_queries
from apps.track import mutations as track_mutations
from apps.track import queries as track_queries
from apps.user import mutations as user_mutations
from apps.user import queries as user_queries
from main.caches import CacheKey

from .context import GraphQLContext
from .dataloaders import GlobalDataLoader
from .enums import AppEnumCollection, AppEnumCollectionData
from .permissions import IsAuthenticated


class CustomAsyncGraphQLView(AsyncGraphQLView):
    async def load_event_cache(self):
        """
        XXX: This is used by other internal modules
        """
        cache.delete(CacheKey.TIMUR_EVENT_DATES)
        if not cache.has_key(CacheKey.TIMUR_EVENT_DATES):
            # Generate cache
            await Event.aget_relative_event_dates()

    async def get_context(self, *args, **kwargs) -> GraphQLContext:
        await self.load_event_cache()
        return GraphQLContext(
            *args,
            **kwargs,
            dl=GlobalDataLoader(),
        )


@strawberry.type
class PublicQuery(
    user_queries.PublicQuery,
):
    id: strawberry.ID = strawberry.ID("public")


@strawberry.type
class PrivateQuery(
    user_queries.PrivateQuery,
    standup_queries.PrivateQuery,
    project_queries.PrivateQuery,
    track_queries.PrivateQuery,
    journal_queries.PrivateQuery,
    common_queries.PrivateQuery,
):
    id: strawberry.ID = strawberry.ID("private")


@strawberry.type
class PublicMutation(
    user_mutations.PublicMutation,
):
    id: strawberry.ID = strawberry.ID("public")


@strawberry.type
class PrivateMutation(
    track_mutations.PrivateMutation,
    journal_mutations.PrivateMutation,
):
    id: strawberry.ID = strawberry.ID("private")


@strawberry.type
class Query:
    public: PublicQuery = strawberry.field(resolver=lambda: PublicQuery())
    private: PrivateQuery = strawberry.field(permission_classes=[IsAuthenticated], resolver=lambda: PrivateQuery())
    enums: AppEnumCollection = strawberry.field(  # type: ignore[reportGeneralTypeIssues]
        resolver=lambda: AppEnumCollectionData()
    )


@strawberry.type
class Mutation:
    public: PublicMutation = strawberry.field(resolver=lambda: PublicMutation())
    private: PrivateMutation = strawberry.field(
        resolver=lambda: PrivateMutation(),
        permission_classes=[IsAuthenticated],
    )


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
)
