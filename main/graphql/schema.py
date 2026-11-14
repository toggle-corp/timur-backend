import typing

import strawberry
from django.core.cache import cache
from strawberry.django.views import AsyncGraphQLView

# Imported to make sure strawberry custom modules are loadded first
import utils.strawberry.transformers  # pyright: ignore[reportUnusedImport] # type: ignore # noqa F401
from apps.api_token import mutations as api_token_mutations
from apps.api_token import queries as api_token_queries
from apps.api_token.auth import ApiTokenAuditExtension, dispatch_with_api_token
from apps.api_token.scopes import ApiTokenScopeExtension, ScopeTag, field_scope, type_scope
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
from .errors import MaskUnexpectedErrors, log_errors
from .limits import DocumentLimits, MaxTokensLimiter, OperationSelectionCheck
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

    async def dispatch(self, request, *args, **kwargs):  # type: ignore[reportIncompatibleMethodOverride]
        view_dispatch = super().dispatch
        return await dispatch_with_api_token(request, lambda: view_dispatch(request, *args, **kwargs))

    async def get_context(self, request, response):  # type: ignore[reportIncompatibleMethodOverride]
        await self.load_event_cache()
        return GraphQLContext(
            request=request,
            response=response,
            dl=GlobalDataLoader(),
        )


@type_scope(ScopeTag.ROOT)
@strawberry.type
class PublicQuery(
    user_queries.PublicQuery,
):
    id: strawberry.ID = strawberry.field(default=strawberry.ID("public"), metadata=field_scope(ScopeTag.NO_SCOPE))


@type_scope(ScopeTag.ROOT)
@strawberry.type
class PrivateQuery(
    user_queries.PrivateQuery,
    standup_queries.PrivateQuery,
    project_queries.PrivateQuery,
    track_queries.PrivateQuery,
    journal_queries.PrivateQuery,
    common_queries.PrivateQuery,
    api_token_queries.PrivateQuery,
):
    id: strawberry.ID = strawberry.field(default=strawberry.ID("private"), metadata=field_scope(ScopeTag.NO_SCOPE))


@type_scope(ScopeTag.ROOT)
@strawberry.type
class PublicMutation(
    user_mutations.PublicMutation,
):
    id: strawberry.ID = strawberry.field(default=strawberry.ID("public"), metadata=field_scope(ScopeTag.NO_SCOPE))


@type_scope(ScopeTag.ROOT)
@strawberry.type
class PrivateMutation(
    track_mutations.PrivateMutation,
    journal_mutations.PrivateMutation,
    api_token_mutations.PrivateMutation,
):
    id: strawberry.ID = strawberry.field(default=strawberry.ID("private"), metadata=field_scope(ScopeTag.NO_SCOPE))


@type_scope(ScopeTag.ROOT)
@strawberry.type
class Query:
    public: PublicQuery = strawberry.field(resolver=lambda: PublicQuery(), metadata=field_scope(ScopeTag.NO_SCOPE))
    private: PrivateQuery = strawberry.field(
        permission_classes=[IsAuthenticated],
        resolver=lambda: PrivateQuery(),
        metadata=field_scope(ScopeTag.NO_SCOPE),
    )
    enums: AppEnumCollection = strawberry.field(  # type: ignore[reportGeneralTypeIssues]
        resolver=lambda: AppEnumCollectionData(),
        metadata=field_scope(ScopeTag.NO_SCOPE),
    )


@type_scope(ScopeTag.ROOT)
@strawberry.type
class Mutation:
    public: PublicMutation = strawberry.field(resolver=lambda: PublicMutation(), metadata=field_scope(ScopeTag.NO_SCOPE))
    private: PrivateMutation = strawberry.field(
        resolver=lambda: PrivateMutation(),
        permission_classes=[IsAuthenticated],
        metadata=field_scope(ScopeTag.NO_SCOPE),
    )


class CustomSchema(strawberry.Schema):
    @typing.override
    def process_errors(self, errors, execution_context=None):
        log_errors(errors, execution_context)


schema = CustomSchema(
    query=Query,
    mutation=Mutation,
    # Classes, not instances: strawberry instantiates classes per operation but shares instances between
    # concurrent operations (overwriting their execution_context).
    extensions=[
        MaxTokensLimiter,
        OperationSelectionCheck,
        DocumentLimits,
        ApiTokenScopeExtension,
        ApiTokenAuditExtension,
        MaskUnexpectedErrors,
    ],
)
