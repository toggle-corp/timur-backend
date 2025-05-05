# pyright: reportPrivateImportUsage=false
# pyright: reportIncompatibleVariableOverride=false
import factory
from factory.django import DjangoModelFactory

from .models import DailyUserStandup, Quote, StandupGatherAroundMedia


class DailyUserStandupFactory(DjangoModelFactory):
    class Meta:
        model = DailyUserStandup


class QuoteFactory(DjangoModelFactory):
    author = factory.Faker("name")
    text = factory.Faker("sentence")

    class Meta:
        model = Quote


class StandupGatherAroundMediaFactory(DjangoModelFactory):
    url = factory.Faker("url")
    caption = factory.Faker("sentence")

    class Meta:
        model = StandupGatherAroundMedia
