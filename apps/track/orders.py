import strawberry
import strawberry_django

from .models import Contract, Task, TimeEntry


@strawberry_django.ordering.order(Contract)
class ContractOrder:
    id: strawberry.auto
    name: strawberry.auto
    created_at: strawberry.auto


@strawberry_django.ordering.order(Task)
class TaskOrder:
    id: strawberry.auto
    name: strawberry.auto
    created_at: strawberry.auto


@strawberry_django.ordering.order(TimeEntry)
class TimeEntryOrder:
    id: strawberry.auto
    date: strawberry.auto
