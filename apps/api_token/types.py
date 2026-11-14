import strawberry
import strawberry_django
from django.db import models

from apps.api_token.scopes import ScopeTag, type_scope
from main.graphql.context import Info
from utils.common import get_queryset_for_model
from utils.strawberry.enums import enum_field
from utils.strawberry.types import string_field

from .enums import ApiTokenStatusEnum
from .models import ApiToken


@type_scope(ScopeTag.SESSION_ONLY)
@strawberry_django.type(ApiToken)
class ApiTokenType:
    id: strawberry.ID
    prefix: strawberry.auto
    created_at: strawberry.auto
    expires_at: strawberry.auto
    last_used_at: strawberry.auto
    revoked_at: strawberry.auto

    name = string_field(ApiToken.name)
    scopes = enum_field(ApiToken.scopes)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(ApiToken, queryset)

    @strawberry_django.field
    def status(self, root: strawberry.Parent[ApiToken]) -> ApiTokenStatusEnum:  # type: ignore[reportInvalidTypeForm]
        return root.get_status()


@type_scope(ScopeTag.SESSION_ONLY)
@strawberry.type
class CreatedApiTokenType:
    token: ApiTokenType
    secret: str = strawberry.field(description="The full token. It is returned only once, on creation.")
