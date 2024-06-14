from asgiref.sync import sync_to_async
from django.utils.functional import cached_property
from strawberry.dataloader import DataLoader

from apps.common.dataloaders import load_model_objects

from .models import Milestone, Task


def load_task(keys: list[int]) -> list[Task]:
    return load_model_objects(Task, keys)


def load_milestone(keys: list[int]) -> list[Milestone]:
    return load_model_objects(Milestone, keys)


class TrackDataLoader:

    @cached_property
    def load_task(self):
        return DataLoader(load_fn=sync_to_async(load_task))

    @cached_property
    def load_milestone(self):
        return DataLoader(load_fn=sync_to_async(load_milestone))
