import strawberry
import strawberry_django

from .models import Milestone, Task, TimeTrack


@strawberry_django.ordering.order(Milestone)
class MilestoneOrder:
    id: strawberry.auto
    name: strawberry.auto
    created_at: strawberry.auto


@strawberry_django.ordering.order(Task)
class TaskOrder:
    id: strawberry.auto
    name: strawberry.auto
    created_at: strawberry.auto


@strawberry_django.ordering.order(TimeTrack)
class TimeTrackOrder:
    id: strawberry.auto
    date: strawberry.auto
