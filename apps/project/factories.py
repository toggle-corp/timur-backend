import factory
from factory.django import DjangoModelFactory

from .models import Client, Contractor, Project


class ClientFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Client-{n}")

    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = Client


class ContractorFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Contractor-{n}")

    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = Contractor


class ProjectFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Project-{n}")

    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = Project
