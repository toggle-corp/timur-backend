import strawberry
import strawberry_django

from .models import User


@strawberry_django.type(User)
class UserType:
    id: strawberry.ID
    first_name: strawberry.auto
    last_name: strawberry.auto

    @strawberry_django.field
    def display_name(self, root: User) -> str:
        return root.get_full_name()
