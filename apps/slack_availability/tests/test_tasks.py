import datetime
import typing
from unittest import mock

from django.core import management
from django.test import override_settings
from django.utils import timezone

from apps.slack_availability.events import classify_event
from apps.slack_availability.factories import SlackAvailabilityRunFactory, SlackAvailabilityThreadFactory
from apps.slack_availability.models import SlackAvailabilityRun
from apps.slack_availability.processor import Reaction
from apps.slack_availability.tasks import (
    MAX_RETRIES,
    notify_slack_availability_run,
    process_slack_availability_event,
)
from main.tests import TestCase

from . import AVAILABILITY_SETTINGS, CHANNEL_ID, FakeSlack, message_event, next_monday, ts_at


@override_settings(**AVAILABILITY_SETTINGS)
@mock.patch("apps.slack_availability.tasks.TimurSlack", FakeSlack)
class TestProcessSlackAvailabilityEvent(TestCase):
    @typing.override
    def setUp(self):
        super().setUp()
        self.ts = ts_at(next_monday())
        message_event_ = classify_event(message_event("U1", "Leave today", self.ts), CHANNEL_ID)
        assert message_event_ is not None
        self.event = message_event_.as_dict()

    @mock.patch("apps.slack_availability.tasks.AvailabilityProcessor")
    def test_event_is_processed(self, processor_mock):
        process_slack_availability_event.apply(args=(self.event,))
        processor_mock.return_value.process.assert_called_once()
        message_event_ = processor_mock.return_value.process.call_args.args[0]
        assert message_event_.trigger_ts == self.ts

    @mock.patch("apps.slack_availability.tasks.notify_slack_availability_run")
    @mock.patch("apps.slack_availability.tasks.AvailabilityProcessor")
    def test_run_is_notified(self, processor_mock, notify_task_mock):
        process_slack_availability_event.apply(args=(self.event,))
        processor = processor_mock.return_value
        processor.notify.assert_called_once_with(processor.process.return_value)
        notify_task_mock.apply_async.assert_not_called()

    @mock.patch("apps.slack_availability.tasks.notify_slack_availability_run")
    @mock.patch("apps.slack_availability.tasks.AvailabilityProcessor")
    def test_notify_failure_is_retried_separately(self, processor_mock, notify_task_mock):
        processor = processor_mock.return_value
        processor.process.return_value.pk = 42
        processor.notify.side_effect = RuntimeError("Slack is down")

        with self.assertLogs("apps.slack_availability.tasks", level="WARNING"):
            process_slack_availability_event.apply(args=(self.event,))

        # Processing is not retried, only the notification
        processor.process.assert_called_once()
        notify_task_mock.apply_async.assert_called_once()
        assert notify_task_mock.apply_async.call_args.kwargs["args"] == (42,)

    @override_settings(SLACK_AVAILABILITY_MODE="off")
    @mock.patch("apps.slack_availability.tasks.AvailabilityProcessor")
    def test_off_mode(self, processor_mock):
        process_slack_availability_event.apply(args=(self.event,))
        processor_mock.assert_not_called()

    @mock.patch("apps.slack_availability.tasks.mark_event_failed")
    @mock.patch("apps.slack_availability.tasks.AvailabilityProcessor")
    def test_failure_is_retried(self, processor_mock, mark_event_failed_mock):
        processor_mock.return_value.process.side_effect = RuntimeError("Ollama is down")

        # Eager mode runs the retries right away
        process_slack_availability_event.apply(args=(self.event,))
        assert processor_mock.return_value.process.call_count == MAX_RETRIES + 1
        mark_event_failed_mock.assert_called_once()

    @mock.patch("apps.slack_availability.tasks.AvailabilityProcessor")
    def test_failure_after_retries(self, processor_mock):
        processor_mock.return_value.process.side_effect = RuntimeError("Ollama is down")

        with self.assertLogs("apps.slack_availability.processor", level="ERROR"):
            process_slack_availability_event.apply(args=(self.event,), retries=MAX_RETRIES)

        run = SlackAvailabilityRun.objects.get()
        assert run.status == SlackAvailabilityRun.Status.FAILED
        slack = processor_mock.call_args.args[0]
        assert slack.reactions == [(self.ts, Reaction.FAILED)]


@override_settings(**AVAILABILITY_SETTINGS)
@mock.patch("apps.slack_availability.tasks.TimurSlack", FakeSlack)
class TestNotifySlackAvailabilityRun(TestCase):
    @typing.override
    def setUp(self):
        super().setUp()
        self.availability_run = SlackAvailabilityRunFactory.create(
            thread=SlackAvailabilityThreadFactory.create(),
            today=datetime.date.today(),
            reply_text="<@U1> I've updated your Timur journal",
        )

    @mock.patch("apps.slack_availability.tasks.AvailabilityProcessor")
    def test_notify(self, processor_mock):
        notify_slack_availability_run.apply(args=(self.availability_run.pk,))
        processor_mock.return_value.notify.assert_called_once_with(self.availability_run)

    @mock.patch("apps.slack_availability.tasks.AvailabilityProcessor")
    def test_notify_failure_after_retries(self, processor_mock):
        processor_mock.return_value.notify.side_effect = RuntimeError("Slack is down")

        with self.assertLogs("apps.slack_availability.processor", level="ERROR"):
            notify_slack_availability_run.apply(args=(self.availability_run.pk,))

        assert processor_mock.return_value.notify.call_count == MAX_RETRIES + 1
        self.availability_run.refresh_from_db()
        assert self.availability_run.status == SlackAvailabilityRun.Status.APPLIED
        assert "Slack is down" in self.availability_run.error
        slack = processor_mock.call_args.args[0]
        assert slack.reactions == [(self.availability_run.trigger_ts, Reaction.FAILED)]


class TestPurgeSlackAvailabilityRuns(TestCase):
    @override_settings(SLACK_AVAILABILITY_RETENTION_DAYS=30)
    def test_purge(self):
        thread = SlackAvailabilityThreadFactory.create()
        llm_output = {
            "is_about_poster_availability": True,
            "availability": [
                {
                    "source_phrase": "fever, leave today",
                    "start_date": "2026-10-15",
                    "end_date": "2026-10-15",
                    "leave": "full",
                    "wfh": "none",
                },
            ],
            "unclear": ["off for my surgery, dates TBD"],
            "confidence": 0.9,
        }
        trace = {
            "version": 1,
            "messages": [{"ts": "1.0", "posted_at": "2026-10-15T09:00:00+05:45", "text": "I have fever, leave today"}],
            "ranges": [{"source_phrase": "fever, leave today", "dates": ["2026-10-15"], "leave": "full"}],
            "unclear": ["off for my surgery, dates TBD"],
            "dates": [{"date": "2026-10-15", "action": "add"}],
            "purged": False,
        }
        planned_changes = {
            "changes": [{"date": "2026-10-15", "action": "add"}],
            "unclear": ["off for my surgery, dates TBD"],
        }
        old_run, recent_run = SlackAvailabilityRunFactory.create_batch(
            2,
            thread=thread,
            today=datetime.date.today(),
            llm_input="I have fever, leave today",
            llm_output=llm_output,
            planned_changes=planned_changes,
            trace=trace,
            reply_text='I couldn\'t work out the dates for "off for my surgery, dates TBD"',
            error="AvailabilityParserError('Invalid date: surgery')",
        )
        SlackAvailabilityRun.objects.filter(pk=old_run.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=31),
        )

        management.call_command("slack_availability_purge")

        old_run.refresh_from_db()
        recent_run.refresh_from_db()
        assert old_run.purged_at is not None
        assert old_run.llm_input == ""
        assert old_run.reply_text == ""
        assert old_run.error == ""
        assert old_run.llm_output == {
            "is_about_poster_availability": True,
            "availability": [
                {"start_date": "2026-10-15", "end_date": "2026-10-15", "leave": "full", "wfh": "none"},
            ],
            "confidence": 0.9,
            "unclear": [],
        }
        assert old_run.trace == {
            **trace,
            "messages": [{"ts": "1.0", "posted_at": "2026-10-15T09:00:00+05:45", "text": ""}],
            "ranges": [{"source_phrase": "", "dates": ["2026-10-15"], "leave": "full"}],
            "unclear": [],
            "purged": True,
        }
        assert old_run.planned_changes == {"changes": planned_changes["changes"], "unclear": []}

        assert recent_run.purged_at is None
        assert recent_run.llm_input == "I have fever, leave today"
        assert recent_run.llm_output == llm_output
        assert recent_run.planned_changes == planned_changes
        assert recent_run.trace == trace

        # Already purged runs are left alone
        management.call_command("slack_availability_purge")
        old_run.refresh_from_db()
        assert old_run.purged_at is not None
