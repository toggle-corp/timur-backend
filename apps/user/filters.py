import strawberry
import strawberry_django
from django.db import models

from .enums import UserDepartmentTypeEnum
from .models import User


@strawberry_django.filters.filter(User, lookups=True)
class UserFilter:
    id: strawberry.auto
    display_name: strawberry.auto

    @strawberry_django.filter_field
    def departments(
        self,
        queryset: models.QuerySet,
        value: list[UserDepartmentTypeEnum],  # type: ignore[reportInvalidTypeForm]
        prefix: str,
    ) -> tuple[models.QuerySet, models.Q]:
        return queryset, models.Q(**{f"{prefix}department__in": value})
