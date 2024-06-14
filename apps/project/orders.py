import strawberry
import strawberry_django

from .models import Client, Contractor, Project


@strawberry_django.ordering.order(Client)
class ClientOrder:
    id: strawberry.auto
    name: strawberry.auto


@strawberry_django.ordering.order(Contractor)
class ContractorOrder:
    id: strawberry.auto
    name: strawberry.auto


@strawberry_django.ordering.order(Project)
class ProjectOrder:
    id: strawberry.auto
    name: strawberry.auto
