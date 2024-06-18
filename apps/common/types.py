import datetime

import strawberry
import strawberry_django
from django.db import models

from apps.common.serializers import TempClientIdMixin
from apps.user.types import UserType
from main.caches import local_cache
from main.graphql.context import Info

from .models import UserResource


class UserResourceTypeMixin:
    created_at: datetime.datetime
    modified_at: datetime.datetime

    @strawberry_django.field
    async def created_by(self, root: UserResource, info: Info) -> UserType:
        return await info.context.dl.user.load_user.load(root.created_by_id)

    @strawberry_django.field
    async def modified_by(self, root: UserResource, info: Info) -> UserType:
        return await info.context.dl.user.load_user.load(root.modified_by_id)


class ClientIdMixin:
    @strawberry_django.field
    def client_id(self, root: models.Model, info: Info) -> strawberry.ID:
        # NOTE: We should always provide non-null client_id
        return strawberry.ID(
            getattr(self, "client_id", None)
            or local_cache.get(TempClientIdMixin.get_cache_key(self, info.context.request))
            or str(root.pk)
        )
