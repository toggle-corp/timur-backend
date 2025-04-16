import strawberry
import strawberry_django

from .models import Event


@strawberry_django.ordering.order(Event)
class EventOrder:
    id: strawberry.auto
    name: strawberry.auto
    start_date: strawberry.auto
    end_date: strawberry.auto
