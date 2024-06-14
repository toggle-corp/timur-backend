import strawberry
from strawberry.django.views import AsyncGraphQLView

# Imported to make sure strawberry custom modules are loadded first
import utils.strawberry.transformers  # pyright: ignore[reportUnusedImport] # type: ignore # noqa F401
from apps.project import queries as project_queries
from apps.track import mutations as track_mutations
from apps.track import queries as track_queries
from apps.user import mutations as user_mutations
from apps.user import queries as user_queries

from .context import GraphQLContext
from .dataloaders import GlobalDataLoader
from .enums import AppEnumCollection, AppEnumCollectionData
from .permissions import IsAuthenticated


class CustomAsyncGraphQLView(AsyncGraphQLView):
    async def get_context(self, *args, **kwargs) -> GraphQLContext:
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
    project_queries.PrivateQuery,
    track_queries.PrivateQuery,
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
