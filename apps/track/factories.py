import factory
from factory.django import DjangoModelFactory

from .models import Contract, Task, TimeTrack


class ContractFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Contract-{n}")

    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = Contract


class TaskFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Task-{n}")

    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = Task


class TimeTrackFactory(DjangoModelFactory):
    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = TimeTrack
