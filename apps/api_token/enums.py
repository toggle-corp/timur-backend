import strawberry

from utils.strawberry.enums import get_enum_name_from_django_field

from .models import ApiToken
from .scopes import ApiTokenScope

ApiTokenScopeEnum = strawberry.enum(ApiTokenScope, name="ApiTokenScopeEnum")
ApiTokenStatusEnum = strawberry.enum(ApiToken.Status, name="ApiTokenStatusEnum")


enum_map = {
    get_enum_name_from_django_field(ApiToken.scopes): ApiTokenScopeEnum,
    "ApiTokenStatus": ApiTokenStatusEnum,
}
