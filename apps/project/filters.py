import strawberry
import strawberry_django

from .models import Client, Contractor, Project


@strawberry_django.filters.filter(Client, lookups=True)
class ClientFilter:
    id: strawberry.auto
    name: strawberry.auto


@strawberry_django.filters.filter(Contractor, lookups=True)
class ContractorFilter:
    id: strawberry.auto
    name: strawberry.auto


@strawberry_django.filters.filter(Project, lookups=True)
class ProjectFilter:
    id: strawberry.auto
    client: strawberry.auto
    contractor: strawberry.auto
