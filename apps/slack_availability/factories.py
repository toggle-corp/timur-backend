# pyright: reportPrivateImportUsage=false
# pyright: reportIncompatibleVariableOverride=false
import factory
from factory.django import DjangoModelFactory

from .models import SlackAvailabilityJournalEntry, SlackAvailabilityRun, SlackAvailabilityThread


class SlackAvailabilityThreadFactory(DjangoModelFactory):
    channel_id = "C-AVAILABILITY"
    thread_ts = factory.Sequence(lambda n: f"1760000000.{n:06d}")
    slack_user_id = factory.Sequence(lambda n: f"u-slack-user-id-{n}")

    class Meta:
        model = SlackAvailabilityThread


class SlackAvailabilityRunFactory(DjangoModelFactory):
    mode = "live"
    trigger = SlackAvailabilityRun.Trigger.MESSAGE
    trigger_ts = factory.Sequence(lambda n: f"1760000000.{n:06d}")
    status = SlackAvailabilityRun.Status.APPLIED

    class Meta:
        model = SlackAvailabilityRun


class SlackAvailabilityJournalEntryFactory(DjangoModelFactory):
    class Meta:
        model = SlackAvailabilityJournalEntry
