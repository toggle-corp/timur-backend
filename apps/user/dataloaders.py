import typing

from asgiref.sync import sync_to_async
from django.utils.functional import cached_property
from strawberry.dataloader import DataLoader

from apps.common.dataloaders import load_model_objects

from .models import User

if typing.TYPE_CHECKING:
    from .types import UserType


def load_user(keys: list[int]) -> list["UserType"]:
    return load_model_objects(User, keys)  # type: ignore[reportReturnType]


class UserDataLoader:
    @cached_property
    def load_user(self):
        return DataLoader(load_fn=sync_to_async(load_user))
