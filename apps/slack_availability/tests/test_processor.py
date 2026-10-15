import datetime
import typing
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from slack_sdk.errors import SlackApiError

from apps.journal.factories import JournalFactory
from apps.journal.models import Journal
from apps.slack_availability.events import classify_event
from apps.slack_availability.messages import WHY_ACTION_ID, build_reply_blocks, format_date
from apps.slack_availability.models import (
    SlackAvailabilityJournalEntry,
    SlackAvailabilityRun,
    SlackAvailabilityThread,
)
from apps.slack_availability.processor import (
    AvailabilityProcessor,
    Reaction,
    mark_event_failed,
    mark_notify_failed,
)
from apps.slack_availability.structs import AvailabilityRange, DayState, Half, MissingDetail, UnclearPart
from apps.standup.models import DailyUserStandup
from apps.user.factories import UserFactory
from apps.user.models import User
from main.tests import TestCase
from utils import frontend_urls

from . import (
    AVAILABILITY_SETTINGS,
    CHANNEL_ID,
    FakeParser,
    FakeSlack,
    message_event,
    next_monday,
    slack_message,
    ts_at,
)

LT = Journal.LeaveType
WT = Journal.WorkFromHomeType
Status = SlackAvailabilityRun.Status


@override_settings(**AVAILABILITY_SETTINGS)
class TestAvailabilityProcessor(TestCase):
    @classmethod
    @typing.override
    def setUpTestData(cls):
        cls.user = UserFactory.create(slack_user_id="U-AUTHOR")
        cls.other_user = UserFactory.create(slack_user_id="U-OTHER")
        cls.monday = next_monday()
        cls.tuesday = cls.monday + datetime.timedelta(days=1)
        cls.wednesday = cls.monday + datetime.timedelta(days=2)
        cls.parent_ts = ts_at(cls.monday, 9)
        cls.parent = slack_message("U-AUTHOR", "On leave tomorrow and WFH wednesday", cls.parent_ts)

    @typing.override
    def setUp(self):
        super().setUp()
        self.slack = FakeSlack(threads={self.parent_ts: [self.parent]})

    def process(self, event: dict, parser: FakeParser) -> SlackAvailabilityRun | None:
        """
        Same steps as the Celery task: process, then notify
        """
        message_event_ = classify_event(event, CHANNEL_ID)
        assert message_event_ is not None
        processor = AvailabilityProcessor(self.slack, parser_factory=lambda: parser)
        run = processor.process(message_event_)
        if run is not None:
            processor.notify(run)
        return run

    def delete_event(self, deleted_ts: str, previous_message: dict, at: str) -> dict:
        return {
            "type": "message",
            "subtype": "message_deleted",
            "channel": CHANNEL_ID,
            "ts": at,
            "event_ts": at,
            "deleted_ts": deleted_ts,
            "previous_message": previous_message,
        }

    def journal_state(self, date: datetime.date, user=None) -> DayState | None:
        journal = Journal.objects.filter(user=user or self.user, date=date).first()
        return journal and DayState.from_journal(journal)

    def parent_event(self) -> dict:
        return message_event("U-AUTHOR", self.parent["text"], self.parent_ts)

    def default_parser(self) -> FakeParser:
        return FakeParser(
            ranges=[
                AvailabilityRange(self.tuesday, self.tuesday, leave=Half.FULL),
                AvailabilityRange(self.wednesday, self.wednesday, wfh=Half.FULL),
            ],
        )

    def test_new_message(self):
        parser = self.default_parser()
        run = self.process(self.parent_event(), parser)

        assert run is not None
        assert run.status == Status.APPLIED
        assert run.mode == "live"
        assert run.trigger == SlackAvailabilityRun.Trigger.MESSAGE
        assert run.today == self.monday
        assert "On leave tomorrow" in run.llm_input
        assert run.llm_output == {"fake": True}

        # Parser gets the thread text and the event date
        messages, today = parser.calls[0]
        assert [message.text for message in messages] == [self.parent["text"]]
        assert today == self.monday

        assert self.journal_state(self.tuesday) == DayState(leave_type=LT.FULL)
        assert self.journal_state(self.wednesday) == DayState(wfh_type=WT.FULL)
        assert SlackAvailabilityJournalEntry.objects.filter(thread=run.thread).count() == 2

        assert self.slack.reactions == [(self.parent_ts, Reaction.SEEN), (self.parent_ts, Reaction.DONE)]
        assert len(self.slack.posted) == 1
        posted = self.slack.posted[0]
        assert posted["thread_ts"] == self.parent_ts
        assert posted["channel"] == CHANNEL_ID
        assert posted["text"] == run.reply_text
        assert posted["text"].startswith("<@U-AUTHOR> I've updated your Timur journal:")
        assert "Leave (full)" in posted["text"]
        assert "WFH (full)" in posted["text"]
        assert frontend_urls.daily_journal(self.tuesday) in posted["text"]
        assert run.reply_ts == "9999999999.000001"

        # Blocks: the reply text and the button that opens the trace
        assert posted["blocks"] == build_reply_blocks(run.reply_text, run.pk)
        assert posted["blocks"][-1]["elements"][0]["action_id"] == WHY_ACTION_ID
        assert posted["blocks"][-1]["elements"][0]["value"] == str(run.pk)
        assert run.trace is not None
        assert run.trace["model"] == "fake-model"
        assert run.trace["messages"][0]["text"] == self.parent["text"]
        assert [item["action"] for item in run.trace["dates"]] == ["add", "add"]

    @override_settings(SLACK_AVAILABILITY_MODE="shadow")
    def test_shadow_mode(self):
        run = self.process(self.parent_event(), self.default_parser())

        assert run is not None
        assert run.status == Status.PLANNED
        assert run.mode == "shadow"
        assert [change["action"] for change in run.planned_changes["changes"]] == ["add", "add"]
        assert run.reply_text.startswith("<@U-AUTHOR> I've updated your Timur journal:")
        # Nothing is written or sent
        assert not Journal.objects.exists()
        assert not SlackAvailabilityJournalEntry.objects.exists()
        assert self.slack.reactions == []
        assert self.slack.posted == []

    def test_nothing_to_do(self):
        run = self.process(self.parent_event(), FakeParser())

        assert run is not None
        assert run.status == Status.NO_CHANGE
        assert self.slack.reactions == [(self.parent_ts, Reaction.SEEN)]
        assert self.slack.posted == []

    def test_not_about_availability(self):
        parser = FakeParser(
            ranges=self.default_parser().ranges,
            unclear=["leaving at 4"],
            is_about_availability=False,
        )
        run = self.process(self.parent_event(), parser)

        assert run is not None
        assert run.status == Status.NOT_ABOUT_AVAILABILITY
        assert run.reply_text == ""
        assert not Journal.objects.exists()
        # Seen, but no result reaction and no question
        assert self.slack.reactions == [(self.parent_ts, Reaction.SEEN)]
        assert self.slack.posted == []

    def test_not_about_availability_reverts_earlier_writes(self):
        self.process(self.parent_event(), self.default_parser())

        # The edited thread no longer asks for anything
        edit_ts = ts_at(self.monday, 12)
        edited = {**self.parent, "text": "Running late, in by 11"}
        self.slack.threads[self.parent_ts] = [edited]
        run = self.process(
            {
                "type": "message",
                "subtype": "message_changed",
                "channel": CHANNEL_ID,
                "ts": edit_ts,
                "event_ts": edit_ts,
                "message": edited,
                "previous_message": self.parent,
            },
            FakeParser(ranges=self.default_parser().ranges, unclear=["in by 11"], is_about_availability=False),
        )

        assert run is not None
        assert run.status == Status.APPLIED
        assert self.journal_state(self.tuesday) == DayState()
        assert self.journal_state(self.wednesday) == DayState()
        assert not SlackAvailabilityJournalEntry.objects.exists()
        run.thread.refresh_from_db()
        assert run.thread.desired_state == {}
        assert run.planned_changes["unclear"] == []
        text = self.slack.posted[-1]["text"]
        assert "Removed from your Timur journal:" in text
        assert "in by 11" not in text

    def test_seen_reaction_failure_does_not_stop_processing(self):
        error = SlackApiError("ratelimited", typing.cast("typing.Any", {"ok": False, "error": "ratelimited"}))
        processor = AvailabilityProcessor(self.slack, parser_factory=self.default_parser)
        message_event_ = classify_event(self.parent_event(), CHANNEL_ID)
        assert message_event_ is not None

        with (
            mock.patch.object(self.slack, "add_reaction", side_effect=error),
            self.assertLogs("apps.slack_availability.processor", level="WARNING"),
        ):
            run = processor.process(message_event_)

        assert run is not None
        assert run.status == Status.APPLIED
        assert self.journal_state(self.tuesday) == DayState(leave_type=LT.FULL)

    def test_low_confidence(self):
        run = self.process(self.parent_event(), FakeParser(ranges=self.default_parser().ranges, confidence=0.2))

        assert run is not None
        assert run.status == Status.LOW_CONFIDENCE
        assert not Journal.objects.exists()
        assert self.slack.reactions == [(self.parent_ts, Reaction.SEEN)]
        assert self.slack.posted == []
        assert run.trace is not None
        assert run.trace["low_confidence"] is True
        assert run.trace["dates"] is None

    def test_reply_from_other_user_is_ignored(self):
        reply_ts = ts_at(self.monday, 10)
        reply = slack_message("U-OTHER", "Get well soon", reply_ts, thread_ts=self.parent_ts)
        self.slack.threads[self.parent_ts].append(reply)

        parser = self.default_parser()
        run = self.process(message_event("U-OTHER", reply["text"], reply_ts, thread_ts=self.parent_ts), parser)

        assert run is None
        assert parser.calls == []
        assert self.slack.reactions == []

    def test_thread_text_excludes_other_users_and_bots(self):
        self.slack.threads[self.parent_ts].extend(
            [
                slack_message("U-OTHER", "Get well soon", ts_at(self.monday, 10), thread_ts=self.parent_ts),
                slack_message(
                    "U-TIMUR",
                    "<@U-AUTHOR> I've updated...",
                    ts_at(self.monday, 10, 1),
                    thread_ts=self.parent_ts,
                    bot_id="B-TIMUR",
                ),
                slack_message("U-AUTHOR", "Make wednesday leave too", ts_at(self.monday, 11), thread_ts=self.parent_ts),
            ],
        )
        parser = self.default_parser()
        self.process(self.parent_event(), parser)

        messages, _ = parser.calls[0]
        assert [message.text for message in messages] == [self.parent["text"], "Make wednesday leave too"]

    def test_thread_reply_updates(self):
        self.process(self.parent_event(), self.default_parser())

        reply_ts = ts_at(self.monday, 11)
        reply = slack_message("U-AUTHOR", "Actually WFH tomorrow, wednesday in office", reply_ts, thread_ts=self.parent_ts)
        self.slack.threads[self.parent_ts].append(reply)
        run = self.process(
            message_event("U-AUTHOR", reply["text"], reply_ts, thread_ts=self.parent_ts),
            FakeParser(ranges=[AvailabilityRange(self.tuesday, self.tuesday, wfh=Half.FULL)]),
        )

        assert run is not None
        assert run.trigger == SlackAvailabilityRun.Trigger.REPLY
        assert run.status == Status.APPLIED
        assert self.journal_state(self.tuesday) == DayState(wfh_type=WT.FULL)
        assert self.journal_state(self.wednesday) == DayState()
        assert (reply_ts, Reaction.SEEN) in self.slack.reactions
        assert (reply_ts, Reaction.DONE) in self.slack.reactions
        assert len(self.slack.posted) == 2
        assert "Removed from your Timur journal:" in self.slack.posted[1]["text"]

    def test_edit_without_change_does_not_reply(self):
        self.process(self.parent_event(), self.default_parser())

        edit_event = {
            "type": "message",
            "subtype": "message_changed",
            "channel": CHANNEL_ID,
            "ts": ts_at(self.monday, 12),
            "event_ts": ts_at(self.monday, 12),
            "message": {**self.parent, "text": "On leave tomorrow, and WFH wednesday"},
            "previous_message": self.parent,
        }
        run = self.process(edit_event, self.default_parser())

        assert run is not None
        assert run.trigger == SlackAvailabilityRun.Trigger.EDIT
        assert run.status == Status.NO_CHANGE
        assert len(self.slack.posted) == 1

    def test_parent_deleted(self):
        self.process(self.parent_event(), self.default_parser())
        self.slack.threads = {}

        delete_ts = ts_at(self.monday, 13)
        run = self.process(
            {
                "type": "message",
                "subtype": "message_deleted",
                "channel": CHANNEL_ID,
                "ts": delete_ts,
                "event_ts": delete_ts,
                "deleted_ts": self.parent_ts,
                "previous_message": self.parent,
            },
            self.default_parser(),
        )

        assert run is not None
        assert run.trigger == SlackAvailabilityRun.Trigger.DELETE
        assert run.status == Status.APPLIED
        assert self.journal_state(self.tuesday) == DayState()
        assert self.journal_state(self.wednesday) == DayState()
        assert SlackAvailabilityThread.objects.get(thread_ts=self.parent_ts).is_deleted
        assert not SlackAvailabilityJournalEntry.objects.exists()
        # No reaction or reply for a deleted message
        assert len(self.slack.posted) == 1
        assert len(self.slack.reactions) == 2

    def test_parent_deleted_keeps_manual_changes_and_past_dates(self):
        self.process(self.parent_event(), self.default_parser())
        Journal.objects.filter(user=self.user, date=self.wednesday).update(wfh_type=WT.FIRST_HALF)

        # Deleted on Wednesday: Tuesday is in the past
        delete_ts = ts_at(self.wednesday, 9)
        self.process(
            {
                "type": "message",
                "subtype": "message_deleted",
                "channel": CHANNEL_ID,
                "ts": delete_ts,
                "event_ts": delete_ts,
                "deleted_ts": self.parent_ts,
                "previous_message": self.parent,
            },
            self.default_parser(),
        )

        assert self.journal_state(self.tuesday) == DayState(leave_type=LT.FULL)
        assert self.journal_state(self.wednesday) == DayState(wfh_type=WT.FIRST_HALF)

    def test_reply_deleted_updates_and_replies(self):
        reply_ts = ts_at(self.monday, 11)
        reply = slack_message("U-AUTHOR", "and thursday too", reply_ts, thread_ts=self.parent_ts)
        self.slack.threads[self.parent_ts].append(reply)
        thursday = self.monday + datetime.timedelta(days=3)
        self.process(
            message_event("U-AUTHOR", reply["text"], reply_ts, thread_ts=self.parent_ts),
            FakeParser(ranges=[*self.default_parser().ranges, AvailabilityRange(thursday, thursday, leave=Half.FULL)]),
        )
        assert self.journal_state(thursday) == DayState(leave_type=LT.FULL)
        reactions_before = list(self.slack.reactions)

        self.slack.threads[self.parent_ts] = [self.parent]
        run = self.process(self.delete_event(reply_ts, reply, ts_at(self.monday, 12)), self.default_parser())

        assert run is not None
        assert run.trigger == SlackAvailabilityRun.Trigger.DELETE
        assert run.trigger_ts == reply_ts
        assert run.status == Status.APPLIED
        assert self.journal_state(thursday) == DayState()
        assert "Removed from your Timur journal:" in self.slack.posted[-1]["text"]
        assert run.reply_ts
        # Nothing to react on
        assert self.slack.reactions == reactions_before

    def test_unknown_parent_deleted(self):
        delete_ts = ts_at(self.monday, 13)
        run = self.process(
            {
                "type": "message",
                "subtype": "message_deleted",
                "channel": CHANNEL_ID,
                "ts": delete_ts,
                "event_ts": delete_ts,
                "deleted_ts": self.parent_ts,
                "previous_message": self.parent,
            },
            self.default_parser(),
        )
        assert run is None

    def test_unmapped_user(self):
        self.slack.threads[self.parent_ts] = [{**self.parent, "user": "U-UNKNOWN"}]
        parser = self.default_parser()

        with self.assertLogs("apps.slack_availability.processor", level="ERROR"):
            run = self.process(message_event("U-UNKNOWN", self.parent["text"], self.parent_ts), parser)

        assert run is not None
        assert run.status == Status.UNMAPPED_USER
        assert parser.calls == []
        assert self.slack.reactions == [(self.parent_ts, Reaction.SEEN), (self.parent_ts, Reaction.FAILED)]
        assert self.slack.posted == []

    def test_inactive_user_is_unmapped(self):
        UserFactory.create(slack_user_id="U-INACTIVE", is_active=False)
        self.slack.threads[self.parent_ts] = [{**self.parent, "user": "U-INACTIVE"}]

        with self.assertLogs("apps.slack_availability.processor", level="ERROR"):
            run = self.process(message_event("U-INACTIVE", self.parent["text"], self.parent_ts), self.default_parser())

        assert run is not None
        assert run.status == Status.UNMAPPED_USER

    def test_slack_id_held_by_inactive_user_is_not_relinked(self):
        UserFactory.create(slack_user_id="U-OLD", is_active=False)
        UserFactory.create(slack_user_id=None, email="old@xyz.com")
        self.slack.threads[self.parent_ts] = [{**self.parent, "user": "U-OLD"}]
        self.slack.emails["U-OLD"] = "old@xyz.com"

        with self.assertLogs("apps.slack_availability.processor", level="ERROR"):
            run = self.process(message_event("U-OLD", self.parent["text"], self.parent_ts), self.default_parser())

        assert run is not None
        assert run.status == Status.UNMAPPED_USER
        assert not User.objects.filter(email="old@xyz.com", slack_user_id="U-OLD").exists()

    def test_existing_slack_id_is_not_overwritten(self):
        user = UserFactory.create(slack_user_id="U-FIRST", email="same@xyz.com")
        self.slack.threads[self.parent_ts] = [{**self.parent, "user": "U-SECOND"}]
        self.slack.emails["U-SECOND"] = "same@xyz.com"

        with self.assertLogs("apps.slack_availability.processor", level="ERROR"):
            run = self.process(message_event("U-SECOND", self.parent["text"], self.parent_ts), self.default_parser())

        assert run is not None
        assert run.status == Status.UNMAPPED_USER
        assert (self.parent_ts, Reaction.FAILED) in self.slack.reactions
        user.refresh_from_db()
        assert user.slack_user_id == "U-FIRST"

    def test_user_is_linked_by_email(self):
        user = UserFactory.create(slack_user_id=None, email="new@xyz.com")
        self.slack.threads[self.parent_ts] = [{**self.parent, "user": "U-NEW"}]
        self.slack.emails["U-NEW"] = "New@xyz.com"

        run = self.process(message_event("U-NEW", self.parent["text"], self.parent_ts), self.default_parser())

        assert run is not None
        assert run.status == Status.APPLIED
        user.refresh_from_db()
        assert user.slack_user_id == "U-NEW"
        assert self.journal_state(self.tuesday, user=user) == DayState(leave_type=LT.FULL)

    def test_manual_value_is_skipped(self):
        JournalFactory.create(user=self.user, date=self.wednesday, leave_type=LT.FIRST_HALF)

        run = self.process(self.parent_event(), self.default_parser())

        assert run is not None
        assert run.status == Status.APPLIED
        assert self.journal_state(self.wednesday) == DayState(leave_type=LT.FIRST_HALF)
        text = self.slack.posted[0]["text"]
        assert "Leave (full)" in text
        assert "Thanks for already updating" in text
        assert f"{format_date(self.wednesday)}> in your journal, I left it as is." in text

    def test_manual_matching_values_reply_with_thanks_once(self):
        JournalFactory.create(user=self.user, date=self.tuesday, leave_type=LT.FULL)
        JournalFactory.create(user=self.user, date=self.wednesday, wfh_type=WT.FULL)

        run = self.process(self.parent_event(), self.default_parser())
        assert run is not None
        assert run.status == Status.NO_CHANGE
        assert self.slack.reactions == [(self.parent_ts, Reaction.SEEN)]
        assert len(self.slack.posted) == 1
        text = self.slack.posted[0]["text"]
        assert "I've updated" not in text
        assert (
            f"Thanks for already updating <{frontend_urls.daily_journal(self.tuesday)}|{format_date(self.tuesday)}>"
            f" and <{frontend_urls.daily_journal(self.wednesday)}|{format_date(self.wednesday)}>"
            " in your journal, I left it as is."
        ) in text
        assert text.endswith("> _LLM-interpreted (fake-model). Please double-check._")
        # Manual values stay manual
        assert not SlackAvailabilityJournalEntry.objects.exists()

        # Same outcome again: no new reply
        self.process(self.parent_event(), self.default_parser())
        assert len(self.slack.posted) == 1

    def test_timur_written_values_do_not_get_thanks(self):
        self.process(self.parent_event(), self.default_parser())
        assert len(self.slack.posted) == 1

        # Thread re-read with a new reply that asks for the same values
        reply_ts = ts_at(self.monday, 11)
        reply = slack_message("U-AUTHOR", "Same as above", reply_ts, thread_ts=self.parent_ts)
        self.slack.threads[self.parent_ts].append(reply)
        run = self.process(
            message_event("U-AUTHOR", reply["text"], reply_ts, thread_ts=self.parent_ts),
            self.default_parser(),
        )
        assert run is not None
        assert run.status == Status.NO_CHANGE
        assert len(self.slack.posted) == 1

    def test_only_skipped_replies_once(self):
        JournalFactory.create(user=self.user, date=self.tuesday, wfh_type=WT.FULL)
        JournalFactory.create(user=self.user, date=self.wednesday, leave_type=LT.FULL)

        run = self.process(self.parent_event(), self.default_parser())
        assert run is not None
        assert run.status == Status.NO_CHANGE
        assert run.llm_model == "fake-model"
        assert self.slack.reactions == [(self.parent_ts, Reaction.SEEN)]
        assert len(self.slack.posted) == 1
        assert "Thanks for already updating" in self.slack.posted[0]["text"]

        # Same outcome again: no new reply
        self.process(self.parent_event(), self.default_parser())
        assert len(self.slack.posted) == 1

    def test_guards(self):
        text = "WFH on Wednesday. If the car takes long, I might take Tuesday off."
        self.slack.threads[self.parent_ts] = [slack_message("U-AUTHOR", text, self.parent_ts)]
        next_week_wednesday = self.wednesday + datetime.timedelta(days=7)
        parser = FakeParser(
            ranges=[
                AvailabilityRange(self.tuesday, self.tuesday, leave=Half.FULL, source_phrase="I might take Tuesday off"),
                AvailabilityRange(
                    next_week_wednesday,
                    next_week_wednesday,
                    wfh=Half.FULL,
                    source_phrase="WFH on Wednesday",
                ),
            ],
        )

        run = self.process(message_event("U-AUTHOR", text, self.parent_ts), parser)
        assert run is not None
        assert run.status == Status.APPLIED
        # The conditional leave is dropped and the weekday is resolved from the posting date (Monday)
        assert self.journal_state(self.tuesday) is None
        assert self.journal_state(self.wednesday) == DayState(wfh_type=WT.FULL)
        assert self.journal_state(next_week_wednesday) is None
        assert run.planned_changes["guards"] == {
            "ignored": [
                {"start_date": self.tuesday.isoformat(), "end_date": self.tuesday.isoformat(), "reason": "conditional"},
            ],
            "corrected": [
                {
                    "kind": "weekday",
                    "before": [next_week_wednesday.isoformat()] * 2,
                    "after": [self.wednesday.isoformat()] * 2,
                },
            ],
        }
        assert [item["reason"] for item in run.trace["ignored"]] == ["conditional"]
        assert run.trace["ranges"][0]["corrections"][0]["kind"] == "weekday"
        # The parser output is stored as returned
        assert run.llm_output == {"fake": True}

    def test_unknown_half_asks_once(self):
        parser = FakeParser(ranges=[AvailabilityRange(self.tuesday, self.tuesday, leave=Half.UNKNOWN)])

        run = self.process(self.parent_event(), parser)
        assert run is not None
        assert run.status == Status.NO_CHANGE
        assert not Journal.objects.exists()
        assert len(self.slack.posted) == 1
        assert "Which half on" in self.slack.posted[0]["text"]
        assert self.slack.posted[0]["text"].endswith("> _LLM-interpreted (fake-model). Please double-check._")

        self.process(self.parent_event(), parser)
        assert len(self.slack.posted) == 1

        # The answer resolves it
        reply_ts = ts_at(self.monday, 11)
        self.slack.threads[self.parent_ts].append(
            slack_message("U-AUTHOR", "second half", reply_ts, thread_ts=self.parent_ts),
        )
        run = self.process(
            message_event("U-AUTHOR", "second half", reply_ts, thread_ts=self.parent_ts),
            FakeParser(ranges=[AvailabilityRange(self.tuesday, self.tuesday, leave=Half.SECOND_HALF)]),
        )
        assert run is not None
        assert run.status == Status.APPLIED
        assert self.journal_state(self.tuesday) == DayState(leave_type=LT.SECOND_HALF)

    def test_unknown_half_keeps_current_value(self):
        self.process(self.parent_event(), self.default_parser())

        # "make tuesday a half day" without saying which half
        reply_ts = ts_at(self.monday, 11)
        self.slack.threads[self.parent_ts].append(
            slack_message("U-AUTHOR", "make tuesday a half day", reply_ts, thread_ts=self.parent_ts),
        )
        run = self.process(
            message_event("U-AUTHOR", "make tuesday a half day", reply_ts, thread_ts=self.parent_ts),
            FakeParser(
                ranges=[
                    AvailabilityRange(self.tuesday, self.tuesday, leave=Half.UNKNOWN),
                    AvailabilityRange(self.wednesday, self.wednesday, wfh=Half.FULL),
                ],
            ),
        )

        assert run is not None
        assert run.status == Status.NO_CHANGE
        assert self.journal_state(self.tuesday) == DayState(leave_type=LT.FULL)
        assert SlackAvailabilityJournalEntry.objects.filter(journal__date=self.tuesday, thread=run.thread).exists()
        run.thread.refresh_from_db()
        assert run.thread.desired_state[self.tuesday.isoformat()] == {"leave_type": LT.FULL, "wfh_type": None}
        assert "Which half on" in self.slack.posted[-1]["text"]
        assert "Removed" not in self.slack.posted[-1]["text"]

    def test_unposted_reply_is_not_counted_as_told(self):
        JournalFactory.create(user=self.user, date=self.tuesday, wfh_type=WT.FULL)
        JournalFactory.create(user=self.user, date=self.wednesday, leave_type=LT.FULL)
        message_event_ = classify_event(self.parent_event(), CHANNEL_ID)
        assert message_event_ is not None
        processor = AvailabilityProcessor(self.slack, parser_factory=self.default_parser)

        # The first reply never reached Slack
        first_run = processor.process(message_event_)
        assert first_run is not None
        assert first_run.reply_text
        assert first_run.reply_ts == ""

        self.process(self.parent_event(), self.default_parser())
        assert len(self.slack.posted) == 1
        assert "Thanks for already updating" in self.slack.posted[0]["text"]

    def test_unclear_dates_ask(self):
        run = self.process(self.parent_event(), FakeParser(unclear=["next week sometime"]))

        assert run is not None
        assert 'I couldn\'t work out "next week sometime"' in self.slack.posted[0]["text"]

    def test_open_ended_leave_writes_start_and_asks(self):
        parser = FakeParser(
            ranges=[AvailabilityRange(self.monday, self.monday, leave=Half.FULL, source_phrase="on leave")],
            unclear=[UnclearPart("on leave till further notice", MissingDetail.END_DATE)],
            needs_care=True,
        )
        run = self.process(self.parent_event(), parser)

        assert run is not None
        assert run.status == Status.APPLIED
        assert self.journal_state(self.monday) == DayState(leave_type=LT.FULL)
        assert run.planned_changes["unclear"] == ["on leave till further notice"]
        text = self.slack.posted[0]["text"]
        assert text.startswith("<@U-AUTHOR> Sorry to hear that, take care.\nI've updated your Timur journal:")
        assert "No rush, reply here when you know how long you'll be out" in text

    def test_open_ended_leave_started_earlier_writes_today_and_asks(self):
        # The parser marks the range open-ended but adds no end-date question
        started = self.monday - datetime.timedelta(days=3)
        parser = FakeParser(
            ranges=[
                AvailabilityRange(started, started, leave=Half.FULL, source_phrase="off until I recover", open_end=True),
            ],
        )
        run = self.process(self.parent_event(), parser)

        assert run is not None
        assert run.status == Status.APPLIED
        assert self.journal_state(self.monday) == DayState(leave_type=LT.FULL)
        assert run.planned_changes["unclear"] == ["off until I recover"]
        assert "No rush, reply here when you know how long you'll be out" in self.slack.posted[0]["text"]
        assert run.trace["ranges"][0]["note"] == "no end date yet, so I set it from today and asked"

    def test_needs_care_only_when_about_availability(self):
        self.process(self.parent_event(), self.default_parser())
        parser = FakeParser(is_about_availability=False, needs_care=True)
        # The thread no longer asks for anything: the removal reply has no care line
        self.process(self.parent_event(), parser)
        assert "Removed from your Timur journal" in self.slack.posted[-1]["text"]
        assert all("take care" not in post["text"] for post in self.slack.posted)

    def test_standup_conductor_heads_up(self):
        DailyUserStandup.objects.create(date=self.tuesday, conductor=self.user, fallback_conductor=self.other_user)
        DailyUserStandup.objects.create(date=self.wednesday, conductor=self.other_user, fallback_conductor=self.user)

        self.process(self.parent_event(), self.default_parser())

        text = self.slack.posted[0]["text"]
        assert "you're conducting standup on" in text
        assert "<@U-OTHER> will take over" in text
        assert "you're the backup standup conductor on" in text

    def test_standup_second_half_leave_has_no_heads_up(self):
        DailyUserStandup.objects.create(date=self.tuesday, conductor=self.user, fallback_conductor=self.other_user)

        self.process(
            self.parent_event(),
            FakeParser(ranges=[AvailabilityRange(self.tuesday, self.tuesday, leave=Half.SECOND_HALF)]),
        )

        assert "Heads up" not in self.slack.posted[0]["text"]

    def test_thread_state_is_recorded(self):
        run = self.process(self.parent_event(), self.default_parser())

        assert run is not None
        thread = run.thread
        thread.refresh_from_db()
        assert thread.snapshot_at is not None
        assert thread.desired_state == {
            self.tuesday.isoformat(): {"leave_type": LT.FULL, "wfh_type": None},
            self.wednesday.isoformat(): {"leave_type": None, "wfh_type": WT.FULL},
        }

    def test_slack_failure_keeps_journal_and_notify_is_retried_once(self):
        message_event_ = classify_event(self.parent_event(), CHANNEL_ID)
        assert message_event_ is not None
        processor = AvailabilityProcessor(self.slack, parser_factory=self.default_parser)
        run = processor.process(message_event_)
        assert run is not None

        # Journal is committed before Slack is notified
        assert self.journal_state(self.tuesday) == DayState(leave_type=LT.FULL)
        assert run.reply_ts == ""
        assert self.slack.posted == []

        processor.notify(run)
        processor.notify(run)
        assert len(self.slack.posted) == 1
        assert self.slack.reactions.count((self.parent_ts, Reaction.DONE)) == 1
        run.refresh_from_db()
        assert run.reply_ts == "9999999999.000001"

    def test_mark_notify_failed(self):
        run = self.process(self.parent_event(), self.default_parser())
        assert run is not None

        with self.assertLogs("apps.slack_availability.processor", level="ERROR"):
            mark_notify_failed(self.slack, run, RuntimeError("Slack is down"))

        run.refresh_from_db()
        assert run.status == Status.APPLIED
        assert "Slack is down" in run.error
        assert (self.parent_ts, Reaction.FAILED) in self.slack.reactions
        assert self.journal_state(self.tuesday) == DayState(leave_type=LT.FULL)

    def test_stale_run_changes_nothing(self):
        run = self.process(self.parent_event(), self.default_parser())
        assert run is not None
        # A run that read the thread later already applied its result
        SlackAvailabilityThread.objects.filter(pk=run.thread_id).update(
            snapshot_at=timezone.now() + datetime.timedelta(minutes=5),
        )

        reply_ts = ts_at(self.monday, 11)
        self.slack.threads[self.parent_ts].append(
            slack_message("U-AUTHOR", "cancel all", reply_ts, thread_ts=self.parent_ts),
        )
        run = self.process(message_event("U-AUTHOR", "cancel all", reply_ts, thread_ts=self.parent_ts), FakeParser())

        assert run is not None
        assert run.status == Status.STALE
        assert self.journal_state(self.tuesday) == DayState(leave_type=LT.FULL)
        assert self.journal_state(self.wednesday) == DayState(wfh_type=WT.FULL)
        assert len(self.slack.posted) == 1
        assert (reply_ts, Reaction.DONE) not in self.slack.reactions

    def test_run_after_parent_deleted_changes_nothing(self):
        self.process(self.parent_event(), self.default_parser())
        self.process(self.delete_event(self.parent_ts, self.parent, ts_at(self.monday, 13)), self.default_parser())

        # A reply event processed after the delete, with a thread read before it
        reply_ts = ts_at(self.monday, 12)
        self.slack.threads[self.parent_ts].append(
            slack_message("U-AUTHOR", "make it thursday too", reply_ts, thread_ts=self.parent_ts),
        )
        run = self.process(
            message_event("U-AUTHOR", "make it thursday too", reply_ts, thread_ts=self.parent_ts),
            self.default_parser(),
        )

        assert run is not None
        assert run.status == Status.STALE
        assert self.journal_state(self.tuesday) == DayState()
        assert self.journal_state(self.wednesday) == DayState()
        assert not SlackAvailabilityJournalEntry.objects.exists()

    def _second_thread(self, text: str) -> tuple[str, dict]:
        second_ts = ts_at(self.monday, 10)
        second = slack_message("U-AUTHOR", text, second_ts)
        self.slack.threads[second_ts] = [second]
        return second_ts, second

    def test_deleting_duplicate_thread_keeps_value_of_first_thread(self):
        first = self.process(self.parent_event(), self.default_parser())
        assert first is not None

        # Same leave posted again: the second thread takes ownership of Tuesday
        second_ts, second = self._second_thread("Reminder: on leave tomorrow")
        self.process(
            message_event("U-AUTHOR", second["text"], second_ts),
            FakeParser(ranges=[AvailabilityRange(self.tuesday, self.tuesday, leave=Half.FULL)]),
        )
        assert SlackAvailabilityJournalEntry.objects.get(journal__date=self.tuesday).thread.thread_ts == second_ts

        self.process(self.delete_event(second_ts, second, ts_at(self.monday, 13)), FakeParser())

        assert self.journal_state(self.tuesday) == DayState(leave_type=LT.FULL)
        entry = SlackAvailabilityJournalEntry.objects.get(journal__date=self.tuesday)
        assert entry.thread_id == first.thread_id

    def test_deleting_overriding_thread_restores_value_of_first_thread(self):
        first = self.process(self.parent_event(), self.default_parser())
        assert first is not None

        second_ts, second = self._second_thread("WFH tomorrow instead")
        self.process(
            message_event("U-AUTHOR", second["text"], second_ts),
            FakeParser(ranges=[AvailabilityRange(self.tuesday, self.tuesday, wfh=Half.FULL)]),
        )
        assert self.journal_state(self.tuesday) == DayState(wfh_type=WT.FULL)

        self.process(self.delete_event(second_ts, second, ts_at(self.monday, 13)), FakeParser())

        assert self.journal_state(self.tuesday) == DayState(leave_type=LT.FULL)
        entry = SlackAvailabilityJournalEntry.objects.get(journal__date=self.tuesday)
        assert entry.thread_id == first.thread_id

    def test_mark_event_failed(self):
        message_event_ = classify_event(self.parent_event(), CHANNEL_ID)
        assert message_event_ is not None

        with self.assertLogs("apps.slack_availability.processor", level="ERROR"):
            mark_event_failed(self.slack, message_event_, RuntimeError("Ollama is down"))

        run = SlackAvailabilityRun.objects.get()
        assert run.status == Status.FAILED
        assert "Ollama is down" in run.error
        assert self.slack.reactions == [(self.parent_ts, Reaction.FAILED)]
