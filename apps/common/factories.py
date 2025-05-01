# pyright: reportPrivateImportUsage=false
# pyright: reportIncompatibleVariableOverride=false
import factory
from factory.django import DjangoModelFactory

from .models import Event


class EventFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Event-{n}")

    class Meta:
        model = Event
