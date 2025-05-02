# pyright: reportPrivateImportUsage=false
# pyright: reportIncompatibleVariableOverride=false
import factory
from factory.django import DjangoModelFactory

from .models import DailyUserStandup, Quote


class DailyUserStandupFactory(DjangoModelFactory):
    class Meta:
        model = DailyUserStandup


class QuoteFactory(DjangoModelFactory):
    author = factory.Faker("name")
    text = factory.Faker("sentence")

    class Meta:
        model = Quote
