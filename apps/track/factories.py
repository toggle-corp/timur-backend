import factory
from factory.django import DjangoModelFactory

from .models import Contract, Task, TimeEntry


class ContractFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Contract-{n}")

    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = Contract


class TaskFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Task-{n}")

    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = Task


class TimeEntryFactory(DjangoModelFactory):
    status = TimeEntry.Status.TODO

    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = TimeEntry
