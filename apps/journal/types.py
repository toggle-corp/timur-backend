import strawberry
import strawberry_django
from django.db import models

from apps.user.types import UserType
from main.graphql.context import Info
from utils.common import get_queryset_for_model
from utils.strawberry.enums import enum_display_field, enum_field
from utils.strawberry.types import string_field

from .models import Journal


@strawberry_django.type(Journal)
class JournalType:
    id: strawberry.ID
    user_id: strawberry.ID
    date: strawberry.auto

    leave_type = enum_field(Journal.leave_type)
    leave_type_display = enum_display_field(Journal.leave_type)
    journal_text = string_field(Journal.journal_text)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Journal, queryset)

    @strawberry_django.field
    async def user(self, root: Journal, info: Info) -> UserType:
        return await info.context.dl.user.load_user.load(root.user_id)
