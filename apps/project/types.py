import strawberry
import strawberry_django
from django.db import models

from apps.common.types import UserResourceTypeMixin
from main.graphql.context import Info
from utils.common import get_queryset_for_model
from utils.strawberry.types import string_field

from .models import Client, Contractor, Project


@strawberry_django.type(Client)
class ClientType(UserResourceTypeMixin):
    id: strawberry.ID

    name = string_field(Client.name)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Client, queryset)


@strawberry_django.type(Contractor)
class ContractorType(UserResourceTypeMixin):
    id: strawberry.ID

    name = string_field(Contractor.name)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Contractor, queryset)


@strawberry_django.type(Project)
class ProjectType(UserResourceTypeMixin):
    id: strawberry.ID
    client_id: strawberry.ID
    contractor_id: strawberry.ID

    name = string_field(Project.name)
    description = string_field(Project.description)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Project, queryset)

    @strawberry_django.field
    async def client(self, root: Project, info: Info) -> ClientType:
        return await info.context.dl.project.load_client.load(root.client_id)

    @strawberry_django.field
    async def contractor(self, root: Project, info: Info) -> ContractorType:
        return await info.context.dl.project.load_contractor.load(root.contractor_id)
