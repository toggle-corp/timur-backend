import strawberry
import strawberry_django
from strawberry_django.filters import apply as apply_filters

from apps.api_token.scopes import ApiTokenScope, field_scope
from main.graphql.context import Info
from utils.strawberry.paginations import CountList, pagination_field

from .filters import ClientFilter, ContractorFilter, DeadlineFilter, ProjectFilter
from .orders import ClientOrder, ContractorOrder, ProjectOrder
from .types import ClientType, ContractorType, DeadlineType, ProjectType


@strawberry.type
class PrivateQuery:
    # Paginated ----------------------------
    clients: CountList[ClientType] = pagination_field(
        pagination=True,
        filters=ClientFilter,
        order=ClientOrder,
        metadata=field_scope(ApiTokenScope.PROJECT_READ),
    )

    contractors: CountList[ContractorType] = pagination_field(
        pagination=True,
        filters=ContractorFilter,
        order=ContractorOrder,
        metadata=field_scope(ApiTokenScope.PROJECT_READ),
    )

    projects: CountList[ProjectType] = pagination_field(
        pagination=True,
        filters=ProjectFilter,
        order=ProjectOrder,
        metadata=field_scope(ApiTokenScope.PROJECT_READ),
    )

    # Unbound ----------------------------
    @strawberry_django.field(metadata=field_scope(ApiTokenScope.PROJECT_READ))
    async def all_projects(self, info: Info) -> list[ProjectType]:
        qs = ProjectType.get_queryset(None, None, info).filter(is_archived=False).order_by("slide_order").all()
        return [project async for project in qs]

    @strawberry_django.field(metadata=field_scope(ApiTokenScope.PROJECT_READ))
    async def all_deadlines(self, info: Info, filters: DeadlineFilter | None = None) -> list[DeadlineType]:
        # NOTE: filters is temporarily optional
        qs = DeadlineType.get_queryset(None, None, info)
        if filters is None or filters.is_archived is strawberry.UNSET:
            qs = qs.filter(is_archived=False)
        if filters is not None:
            qs = apply_filters(filters, qs, info, None)
        return [deadline async for deadline in qs]

    # Single ----------------------------
    @strawberry_django.field(metadata=field_scope(ApiTokenScope.PROJECT_READ))
    async def client(self, info: Info, pk: strawberry.ID) -> ClientType | None:
        return await ClientType.get_queryset(None, None, info).filter(pk=pk).afirst()

    @strawberry_django.field(metadata=field_scope(ApiTokenScope.PROJECT_READ))
    async def contractor(self, info: Info, pk: strawberry.ID) -> ContractorType | None:
        return await ContractorType.get_queryset(None, None, info).filter(pk=pk).afirst()

    @strawberry_django.field(metadata=field_scope(ApiTokenScope.PROJECT_READ))
    async def project(self, info: Info, pk: strawberry.ID) -> ProjectType | None:
        return await ProjectType.get_queryset(None, None, info).filter(pk=pk).afirst()
