import strawberry
from asgiref.sync import sync_to_async

from main.graphql.context import Info
from utils.strawberry.paginations import CountList, pagination_field

from .filters import UserFilter
from .orders import UserOrder
from .types import UserMeType, UserType


@strawberry.type
class PublicQuery:
    @strawberry.field
    @sync_to_async
    def me(self, info: Info) -> UserMeType | None:
        user = info.context.request.user
        if user.is_authenticated:
            return user  # type: ignore[reportGeneralTypeIssues]


@strawberry.type
class PrivateQuery:
    # Paginated ----------------------------
    users: CountList[UserType] = pagination_field(
        pagination=True,
        filters=UserFilter,
        order=UserOrder,
    )
