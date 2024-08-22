import strawberry
import strawberry_django
from django.db import models
from django.utils import timezone

from apps.common.types import UserResourceTypeMixin
from main.graphql.context import Info
from utils.common import get_queryset_for_model
from utils.strawberry.types import string_field

from .models import Client, Contractor, Deadline, Project


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


@strawberry_django.type(Deadline)
class DeadlineType(UserResourceTypeMixin):
    id: strawberry.ID
    start_date: strawberry.auto
    end_date: strawberry.auto

    name = string_field(Deadline.name)
    project_id: strawberry.ID
    contract_id: strawberry.ID | None

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Deadline, queryset)

    @strawberry_django.field
    async def total_days(self, root: strawberry.Parent[Deadline]) -> int:
        # TODO: Return only working days
        return (root.end_date - root.start_date).days

    @strawberry_django.field
    async def used_days(self, root: strawberry.Parent[Deadline]) -> int:
        # TODO: Return only working days
        return (timezone.now().date() - root.start_date).days

    @strawberry_django.field
    async def remaining_days(self, root: strawberry.Parent[Deadline]) -> int:
        # TODO: Return only working days
        return (root.end_date - timezone.now().date()).days


@strawberry_django.type(Project)
class ProjectType(UserResourceTypeMixin):
    id: strawberry.ID
    logo: strawberry.auto
    project_client_id: strawberry.ID
    contractor_id: strawberry.ID

    name = string_field(Project.name)
    description = string_field(Project.description)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Project, queryset)

    @strawberry_django.field
    async def project_client(self, root: strawberry.Parent[Project], info: Info) -> ClientType:
        return await info.context.dl.project.load_client.load(root.project_client_id)

    @strawberry_django.field
    async def contractor(self, root: strawberry.Parent[Project], info: Info) -> ContractorType:
        return await info.context.dl.project.load_contractor.load(root.contractor_id)

    @strawberry_django.field
    async def deadlines(self, root: strawberry.Parent[Project], info: Info) -> list[DeadlineType]:
        return await info.context.dl.project.load_deadlines.load(root.id)
