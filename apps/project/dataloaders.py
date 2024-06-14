from asgiref.sync import sync_to_async
from django.utils.functional import cached_property
from strawberry.dataloader import DataLoader

from apps.common.dataloaders import load_model_objects

from .models import Client, Contractor, Project


def load_client(keys: list[int]) -> list[Client]:
    return load_model_objects(Client, keys)


def load_contractor(keys: list[int]) -> list[Contractor]:
    return load_model_objects(Contractor, keys)


def load_project(keys: list[int]) -> list[Project]:
    return load_model_objects(Project, keys)


class ProjectDataLoader:
    @cached_property
    def load_client(self):
        return DataLoader(load_fn=sync_to_async(load_client))

    @cached_property
    def load_contractor(self):
        return DataLoader(load_fn=sync_to_async(load_contractor))

    @cached_property
    def load_project(self):
        return DataLoader(load_fn=sync_to_async(load_project))
