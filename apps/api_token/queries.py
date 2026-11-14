import datetime

import strawberry
import strawberry_django
from django.db import models
from django.utils import timezone

from main.graphql.context import Info

from .scopes import ScopeTag, field_scope
from .types import ApiTokenType

HIDE_AFTER_DAYS = 30


@strawberry.type
class PrivateQuery:
    @strawberry_django.field(
        description="Your tokens: active, and expired or revoked within the last 30 days.",
        metadata=field_scope(ScopeTag.SESSION_ONLY),
    )
    async def my_api_tokens(self, info: Info) -> list[ApiTokenType]:
        hide_before = timezone.now() - datetime.timedelta(days=HIDE_AFTER_DAYS)
        qs = (
            ApiTokenType.get_queryset(None, None, info)
            .filter(user=info.context.request.user)
            .filter(
                # Revoked: visible for 30 days after revoked_at, whatever the expiry
                models.Q(revoked_at__gte=hide_before)
                # Not revoked: active, or expired within the last 30 days
                | models.Q(revoked_at__isnull=True, expires_at__gte=hide_before),
            )
            .order_by("-created_at", "-id")
        )
        return [token async for token in qs]
