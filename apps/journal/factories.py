# pyright: reportPrivateImportUsage=false
# pyright: reportIncompatibleVariableOverride=false
from factory.django import DjangoModelFactory

from .models import Journal


class JournalFactory(DjangoModelFactory):
    class Meta:
        model = Journal
