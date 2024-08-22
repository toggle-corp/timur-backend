import typing
from collections import defaultdict

from asgiref.sync import sync_to_async
from django.utils.functional import cached_property
from strawberry.dataloader import DataLoader

from apps.common.dataloaders import load_model_objects

from .models import Client, Contractor, Deadline, Project

if typing.TYPE_CHECKING:
    from .types import ClientType, ContractorType, DeadlineType, ProjectType


def load_client(keys: list[int]) -> list["ClientType"]:
    return load_model_objects(Client, keys)  # type: ignore[reportReturnType]


def load_contractor(keys: list[int]) -> list["ContractorType"]:
    return load_model_objects(Contractor, keys)  # type: ignore[reportReturnType]


def load_project(keys: list[int]) -> list["ProjectType"]:
    return load_model_objects(Project, keys)  # type: ignore[reportReturnType]


def load_deadlines(keys: list[int]) -> list[list["DeadlineType"]]:
    qs = Deadline.objects.filter(project__in=keys)
    _map = defaultdict(list)
    for obj in qs:
        _map[obj.project_id].append(obj)
    return [_map.get(key, []) for key in keys]


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

    @cached_property
    def load_deadlines(self):
        return DataLoader(load_fn=sync_to_async(load_deadlines))
