import strawberry
import strawberry_django
from asgiref.sync import sync_to_async

from main.graphql.context import Info

from .models import User


@strawberry_django.type(User)
class UserType:
    id: strawberry.ID
    first_name: strawberry.auto
    last_name: strawberry.auto
    display_name: strawberry.auto


@strawberry_django.type(User)
class UserMeType(UserType):
    id: strawberry.ID
    email: strawberry.auto
    first_name: strawberry.auto
    last_name: strawberry.auto
    display_name: strawberry.auto


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
    noop: strawberry.ID = strawberry.ID("noop")
