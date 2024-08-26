import strawberry
from asgiref.sync import sync_to_async

from main.graphql.context import Info

from .types import UserMeType


@strawberry.type
class PublicQuery:
    @strawberry.field
    @sync_to_async
    def me(self, info: Info) -> UserMeType | None:
        user = info.context.request.user
        if user.is_authenticated:
            return user  # type: ignore[reportGeneralTypeIssues]


@strawberry.type
class PrivateQuery: ...
