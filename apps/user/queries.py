import typing

import strawberry
from asgiref.sync import sync_to_async

from apps.api_token.scopes import ApiTokenScope, ScopeTag, field_scope
from main.graphql.context import Info
from utils.strawberry.paginations import CountList, pagination_field

from .filters import UserFilter
from .orders import UserOrder
from .types import UserMeType, UserType


@strawberry.type
class PublicQuery:
    @strawberry.field(metadata=field_scope(ScopeTag.NO_SCOPE))
    @sync_to_async
    def me(self, info: Info) -> UserMeType | None:
        user = info.context.request.user
        if user.is_authenticated:
            return typing.cast("UserMeType", user)
        return None


@strawberry.type
class PrivateQuery:
    # Paginated ----------------------------
    users: CountList[UserType] = pagination_field(
        pagination=True,
        filters=UserFilter,
        order=UserOrder,
        metadata=field_scope(ApiTokenScope.USER_READ),
    )
