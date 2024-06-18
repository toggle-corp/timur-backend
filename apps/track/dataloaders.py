import typing

from asgiref.sync import sync_to_async
from django.db import models
from django.utils.functional import cached_property
from strawberry.dataloader import DataLoader

from apps.common.dataloaders import load_model_objects

from .models import Contract, Task

if typing.TYPE_CHECKING:
    from .types import ContractType, TaskType


def load_task(keys: list[int]) -> list["TaskType"]:
    return load_model_objects(Task, keys)  # type: ignore[reportReturnType]


def load_contract(keys: list[int]) -> list["ContractType"]:
    return load_model_objects(Contract, keys)  # type: ignore[reportReturnType]


def load_total_tasks_estimated_hours_by_contract(keys: list[int]) -> list[float]:
    task_qs = (
        Task.objects.filter(contract__in=keys)
        .order_by()
        .values("contract")
        .annotate(
            total_estimated_hours=models.Sum("estimated_hours"),
        )
    )
    _map = {
        contract_id: total_estimated_hours
        for contract_id, total_estimated_hours in task_qs.values_list("contract", "total_estimated_hours")
    }
    return [_map.get(key, 0) for key in keys]


class TrackDataLoader:

    @cached_property
    def load_task(self):
        return DataLoader(load_fn=sync_to_async(load_task))

    @cached_property
    def load_contract(self):
        return DataLoader(load_fn=sync_to_async(load_contract))

    @cached_property
    def load_total_tasks_estimated_hours_by_contract(self):
        return DataLoader(load_fn=sync_to_async(load_total_tasks_estimated_hours_by_contract))
