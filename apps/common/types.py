import datetime

import strawberry
import strawberry_django
from django.db import models
from django.utils import timezone

from apps.common.serializers import TempClientIdMixin
from apps.user.types import UserType
from main.caches import local_cache
from main.graphql.context import Info
from utils.strawberry.enums import enum_display_field, enum_field
from utils.strawberry.types import string_field

from .models import Event, UserResource


# -- Interfaces
@strawberry.interface
class UserResourceTypeMixin:
    created_at: datetime.datetime
    modified_at: datetime.datetime

    @strawberry_django.field
    async def created_by(self, root: UserResource, info: Info) -> UserType:
        return await info.context.dl.user.load_user.load(root.created_by_id)

    @strawberry_django.field
    async def modified_by(self, root: UserResource, info: Info) -> UserType:
        return await info.context.dl.user.load_user.load(root.modified_by_id)


@strawberry.interface
class ClientIdMixin:

    @strawberry_django.field
    def client_id(self, root: models.Model, info: Info) -> strawberry.ID:
        # NOTE: We should always provide non-null client_id
        return strawberry.ID(
            getattr(self, "client_id", None)
            or local_cache.get(TempClientIdMixin.get_cache_key(self, info.context.request))
            or str(root.pk)
        )


# -- Common models type
@strawberry_django.type(Event)
class EventType(UserResourceTypeMixin):
    id: strawberry.ID
    start_date: strawberry.auto
    end_date: strawberry.auto
    name = string_field(Event.name)

    type = enum_field(Event.type)
    type_display = enum_display_field(Event.type)

    @strawberry_django.field
    def dates(self, event: strawberry.Parent[Event]) -> list[datetime.date]:
        # NOTE: include_holidays=True, Don't care about other holidays (itself included)
        if event.type in Event.Type.__NON_WORKING__:
            return event.get_dates(include_holidays=True)
        return event.get_dates(include_holidays=False)

    @strawberry_django.field
    def is_active(self, event: strawberry.Parent[Event]) -> bool:
        now = timezone.now().date()
        return event.start_date <= now <= event.end_date

    @strawberry_django.field
    async def remaining_days_to_start(self, event: strawberry.Parent[Event]) -> int:
        # XXX: This doesn't work if two non-working events collide
        now = timezone.now().date()
        if now >= event.start_date:
            return 0
        if event.type in Event.Type.__NON_WORKING__:
            return await Event.aget_working_days_count(
                now,
                event.start_date - datetime.timedelta(days=1),
                include_holidays=True,
            )
        return await Event.aget_working_days_count(
            now,
            event.start_date - datetime.timedelta(days=1),
            include_holidays=False,
        )

    @strawberry_django.field
    async def remaining_days_to_end(self, event: strawberry.Parent[Event]) -> int:
        # XXX: This doesn't work if two non-working events collide
        now = timezone.now().date()
        if event.type in Event.Type.__NON_WORKING__:
            return await Event.aget_working_days_count(now, event.end_date, include_holidays=True)
        return await Event.aget_working_days_count(now, event.end_date, include_holidays=False)
