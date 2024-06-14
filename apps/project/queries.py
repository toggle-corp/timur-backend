import strawberry
import strawberry_django

from main.graphql.context import Info
from utils.strawberry.paginations import CountList, pagination_field

from .filters import ClientFilter, ContractorFilter, ProjectFilter
from .orders import ClientOrder, ContractorOrder, ProjectOrder
from .types import ClientType, ContractorType, ProjectType


@strawberry.type
class PrivateQuery:
    # Paginated ----------------------------
    clients: CountList[ClientType] = pagination_field(
        pagination=True,
        filters=ClientFilter,
        order=ClientOrder,
    )

    contractors: CountList[ContractorType] = pagination_field(
        pagination=True,
        filters=ContractorFilter,
        order=ContractorOrder,
    )

    projects: CountList[ProjectType] = pagination_field(
        pagination=True,
        filters=ProjectFilter,
        order=ProjectOrder,
    )

    # Single ----------------------------
    @strawberry_django.field
    async def client(self, info: Info, pk: strawberry.ID) -> ClientType | None:
        return await ClientType.get_queryset(None, None, info).filter(pk=pk).afirst()

    @strawberry_django.field
    async def contractor(self, info: Info, pk: strawberry.ID) -> ContractorType | None:
        return await ContractorType.get_queryset(None, None, info).filter(pk=pk).afirst()

    @strawberry_django.field
    async def project(self, info: Info, pk: strawberry.ID) -> ProjectType | None:
        return await ProjectType.get_queryset(None, None, info).filter(pk=pk).afirst()
