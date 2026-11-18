import datetime
import hashlib
import hmac
import json
import time
import typing
from unittest import mock
from urllib.parse import urlencode

import pytest
from django.test import override_settings

from apps.journal.factories import JournalFactory
from apps.journal.models import Journal, JournalAvailabilityHistory
from apps.slack_availability.events import classify_event
from apps.slack_availability.factories import SlackAvailabilityRunFactory, SlackAvailabilityThreadFactory
from apps.slack_availability.messages import WHY_ACTION_ID, WHY_SHORTCUT_CALLBACK_ID
from apps.slack_availability.models import SlackAvailabilityRun
from apps.user.factories import UserFactory
from main.tests import TestCase

from . import AVAILABILITY_SETTINGS, CHANNEL_ID, SIGNING_SECRET, FakeSlack, message_event

URL = "/slack/events/"


def signed_headers(body: str, secret: str = SIGNING_SECRET, timestamp: int | None = None) -> dict[str, str]:
    timestamp = timestamp or int(time.time())
    signature = hmac.new(secret.encode(), f"v0:{timestamp}:{body}".encode(), hashlib.sha256).hexdigest()
    return {
        "X-Slack-Request-Timestamp": str(timestamp),
        "X-Slack-Signature": f"v0={signature}",
    }


def event_callback(event: dict, event_id: str = "Ev1") -> dict:
    return {"type": "event_callback", "event_id": event_id, "event": event}


@override_settings(**AVAILABILITY_SETTINGS)
@mock.patch("apps.slack_availability.views.process_slack_availability_event")
class TestSlackEventsView(TestCase):
    def post(self, payload: dict, headers: dict | None = None):
        body = json.dumps(payload)
        return self.client.post(
            URL,
            data=body,
            content_type="application/json",
            headers=headers if headers is not None else signed_headers(body),
        )

    def test_url_verification(self, task_mock):
        response = self.post({"type": "url_verification", "challenge": "abc"})
        assert response.status_code == 200
        assert response.json() == {"challenge": "abc"}
        task_mock.delay.assert_not_called()

    def test_invalid_signature(self, task_mock):
        payload = event_callback(message_event("U1", "Leave today", "1760000000.000100"))
        body = json.dumps(payload)
        for headers in [
            {},
            signed_headers(body, secret="wrong-secret"),
            # Too old
            signed_headers(body, timestamp=int(time.time()) - 60 * 10),
        ]:
            response = self.post(payload, headers=headers)
            assert response.status_code == 401
        task_mock.delay.assert_not_called()

    def test_event_is_queued_once(self, task_mock):
        event = message_event("U1", "Leave today", "1760000000.000100")
        assert self.post(event_callback(event)).status_code == 200
        # Slack retry of the same event
        assert self.post(event_callback(event)).status_code == 200
        message_event_ = classify_event(event, CHANNEL_ID)
        assert message_event_ is not None
        task_mock.delay.assert_called_once_with(message_event_.as_dict())

        assert self.post(event_callback(event, event_id="Ev2")).status_code == 200
        assert task_mock.delay.call_count == 2

    def test_other_events_are_not_queued(self, task_mock):
        for event in [
            {**message_event("U1", "Leave today", "1760000000.000100"), "channel": "C-OTHER"},
            {"type": "reaction_added", "channel": CHANNEL_ID},
            # Ignored by classify_event
            {**message_event("U1", "Leave today", "1760000000.000100"), "bot_id": "B1"},
            {**message_event("U1", "joined", "1760000000.000100"), "subtype": "channel_join"},
        ]:
            assert self.post(event_callback(event)).status_code == 200
        task_mock.delay.assert_not_called()

    def test_enqueue_failure_lets_slack_retry(self, task_mock):
        event = message_event("U1", "Leave today", "1760000000.000100")
        task_mock.delay.side_effect = ConnectionError("Broker is down")
        with pytest.raises(ConnectionError):
            self.post(event_callback(event))

        # Slack retry of the same event
        task_mock.delay.side_effect = None
        assert self.post(event_callback(event)).status_code == 200
        assert task_mock.delay.call_count == 2

    @override_settings(SLACK_AVAILABILITY_MODE="off")
    def test_off_mode(self, task_mock):
        response = self.post(event_callback(message_event("U1", "Leave today", "1760000000.000100")))
        assert response.status_code == 200
        task_mock.delay.assert_not_called()

        # URL verification is answered, with a valid signature only
        assert self.post({"type": "url_verification", "challenge": "abc"}).json() == {"challenge": "abc"}
        assert self.post({"type": "url_verification", "challenge": "abc"}, headers={}).status_code == 401

    def test_without_signing_secret(self, task_mock):
        for signing_secret in [None, ""]:
            with override_settings(SLACK_AVAILABILITY_MODE="off", SLACK_SIGNING_SECRET=signing_secret):
                response = self.post({"type": "url_verification", "challenge": "abc"})
            assert response.status_code == 200
            assert response.content == b""

    def test_get_is_not_allowed(self, task_mock):
        assert self.client.get(URL).status_code == 405


INTERACTIONS_URL = "/slack/interactions/"

TRACE = {
    "version": 1,
    "today": "2026-10-12",
    "model": "qwen3:8b",
    "confidence": 0.9,
    "is_about_availability": True,
    "low_confidence": False,
    "messages": [{"ts": "1.0", "posted_at": "2026-10-12T09:00:00+05:45", "text": "Leave tomorrow"}],
    "ranges": [],
    "unclear": [],
    "dates": [],
    "purged": False,
}


@override_settings(**AVAILABILITY_SETTINGS)
class TestSlackInteractionsView(TestCase):
    @typing.override
    def setUp(self):
        super().setUp()
        self.thread = SlackAvailabilityThreadFactory.create(slack_user_id="U-AUTHOR")
        self.availability_run = SlackAvailabilityRunFactory.create(
            thread=self.thread,
            today=datetime.date(2026, 10, 12),
            trace=TRACE,
        )
        self.slack = FakeSlack()
        patcher = mock.patch("apps.slack_availability.views.TimurSlack", return_value=self.slack)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, payload: dict, headers: dict | None = None):
        body = urlencode({"payload": json.dumps(payload)})
        return self.client.post(
            INTERACTIONS_URL,
            data=body,
            content_type="application/x-www-form-urlencoded",
            headers=headers if headers is not None else signed_headers(body),
        )

    def why_payload(self, user: str = "U-AUTHOR", value: str | None = None, action_id: str = WHY_ACTION_ID) -> dict:
        return {
            "type": "block_actions",
            "trigger_id": "trigger-1",
            "user": {"id": user},
            "actions": [{"action_id": action_id, "value": value or str(self.availability_run.pk)}],
        }

    def opened_text(self) -> str:
        assert len(self.slack.views) == 1
        trigger_id, view = self.slack.views[0]
        assert trigger_id == "trigger-1"
        return json.dumps(view)

    def test_poster_sees_trace(self):
        assert self.post(self.why_payload()).status_code == 200
        text = self.opened_text()
        assert "How Timur read your message" in text
        assert "Leave tomorrow" in text
        assert "Journal updated" in text

    def test_others_get_notice(self):
        UserFactory.create(slack_user_id="U-STAFF", is_staff=True)
        UserFactory.create(slack_user_id="U-INACTIVE-ADMIN", is_superuser=True, is_active=False)
        # Unmapped, a staff user who is not a superuser, an inactive superuser
        for user in ["U-OTHER", "U-STAFF", "U-INACTIVE-ADMIN", ""]:
            self.slack.views.clear()
            assert self.post(self.why_payload(user=user)).status_code == 200
            text = self.opened_text()
            assert "Only the person who posted (or a Timur admin) can view this." in text
            assert "Leave tomorrow" not in text

    def test_timur_admin_sees_trace(self):
        UserFactory.create(slack_user_id="U-ADMIN", is_superuser=True)
        assert self.post(self.why_payload(user="U-ADMIN")).status_code == 200
        text = self.opened_text()
        assert "How Timur read your message" in text
        assert "Leave tomorrow" in text

    def test_purged_trace(self):
        SlackAvailabilityRun.objects.filter(pk=self.availability_run.pk).update(trace={**TRACE, "purged": True})
        assert self.post(self.why_payload()).status_code == 200
        assert "Details expired after 90 days." in self.opened_text()

    def test_unknown_run(self):
        for value in ["999999", "not-a-number"]:
            self.slack.views.clear()
            assert self.post(self.why_payload(value=value)).status_code == 200
            assert "couldn't find the details" in self.opened_text()

    def test_ignored_payloads(self):
        for payload in [
            self.why_payload(action_id="other_action"),
            {**self.why_payload(), "type": "view_submission"},
            {**self.why_payload(), "trigger_id": None},
        ]:
            assert self.post(payload).status_code == 200
        assert self.slack.views == []

    def test_invalid_signature(self):
        assert self.post(self.why_payload(), headers={}).status_code == 401
        assert self.slack.views == []

    def test_off_mode(self):
        with override_settings(SLACK_AVAILABILITY_MODE="off"):
            assert self.post(self.why_payload()).status_code == 200
        assert self.slack.views == []

    def test_slack_error_still_answers(self):
        self.slack.open_view = mock.Mock(side_effect=ConnectionError("Slack is down"))
        assert self.post(self.why_payload()).status_code == 200


def trace_with_message(text: str) -> dict:
    return {**TRACE, "messages": [{"ts": "1.0", "posted_at": "2026-10-12T09:00:00+05:45", "text": text}]}


@override_settings(**AVAILABILITY_SETTINGS)
class TestWhyShortcut(TestCase):
    @typing.override
    def setUp(self):
        super().setUp()
        self.poster = UserFactory.create(slack_user_id="U-AUTHOR", first_name="Sam", last_name="Poster")
        self.root_ts = "1760000000.000100"
        self.reply_ts = "1760000100.000200"
        self.thread = SlackAvailabilityThreadFactory.create(
            thread_ts=self.root_ts,
            slack_user_id="U-AUTHOR",
            user=self.poster,
        )
        self.date = datetime.date(2026, 10, 13)
        self.root_run = SlackAvailabilityRunFactory.create(
            thread=self.thread,
            trigger_ts=self.root_ts,
            today=datetime.date(2026, 10, 12),
            trace=trace_with_message("Root trace"),
        )
        self.reply_run = SlackAvailabilityRunFactory.create(
            thread=self.thread,
            trigger=SlackAvailabilityRun.Trigger.REPLY,
            trigger_ts=self.reply_ts,
            today=datetime.date(2026, 10, 12),
            status=SlackAvailabilityRun.Status.NOT_ABOUT_AVAILABILITY,
            planned_changes={
                "changes": [
                    {
                        "date": self.date.isoformat(),
                        "action": "drop",
                        "before": {"leave_type": 1, "wfh_type": None},
                        "after": {"leave_type": 1, "wfh_type": None},
                    },
                ],
            },
            trace=trace_with_message("Reply trace"),
        )
        self.slack = FakeSlack()
        patcher = mock.patch("apps.slack_availability.views.TimurSlack", return_value=self.slack)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, payload: dict):
        body = urlencode({"payload": json.dumps(payload)})
        return self.client.post(
            INTERACTIONS_URL,
            data=body,
            content_type="application/x-www-form-urlencoded",
            headers=signed_headers(body),
        )

    def shortcut_payload(
        self,
        ts: str,
        thread_ts: str | None = None,
        user: str = "U-AUTHOR",
        author: str = "U-AUTHOR",
        channel: str = CHANNEL_ID,
        **message_fields,
    ) -> dict:
        message = {"type": "message", "user": author, "ts": ts, "text": "Some text", **message_fields}
        if thread_ts:
            message["thread_ts"] = thread_ts
        return {
            "type": "message_action",
            "callback_id": WHY_SHORTCUT_CALLBACK_ID,
            "trigger_id": "trigger-1",
            "user": {"id": user},
            "channel": {"id": channel},
            "message_ts": ts,
            "message": message,
        }

    def opened_text(self, payload: dict) -> str:
        self.slack.views.clear()
        assert self.post(payload).status_code == 200
        assert len(self.slack.views) == 1
        trigger_id, view = self.slack.views[0]
        assert trigger_id == "trigger-1"
        return json.dumps(view, ensure_ascii=False)

    def test_reply_opens_its_run(self):
        text = self.opened_text(self.shortcut_payload(self.reply_ts, thread_ts=self.root_ts))
        assert "Reply trace" in text

    def test_root_message_opens_latest_run_of_thread(self):
        text = self.opened_text(self.shortcut_payload(self.root_ts))
        assert "Reply trace" in text
        # A root message with replies has its own ts as thread_ts
        text = self.opened_text(self.shortcut_payload(self.root_ts, thread_ts=self.root_ts))
        assert "Reply trace" in text

    def test_permissions(self):
        text = self.opened_text(self.shortcut_payload(self.reply_ts, thread_ts=self.root_ts, user="U-OTHER"))
        assert "Only the author of the message or a Timur admin can view this." in text
        assert "Reply trace" not in text

        UserFactory.create(slack_user_id="U-ADMIN", is_superuser=True)
        text = self.opened_text(self.shortcut_payload(self.reply_ts, thread_ts=self.root_ts, user="U-ADMIN"))
        assert "Reply trace" in text

    def test_outcome_and_history(self):
        journal = JournalFactory.create(user=self.poster, date=self.date, leave_type=Journal.LeaveType.FULL)
        other_user = UserFactory.create(first_name="Alex", last_name="Admin")
        History = JournalAvailabilityHistory
        History.objects.create(
            journal=journal,
            leave_type_after=Journal.LeaveType.FULL,
            source=History.Source.SLACK_TIMUR,
            slack_availability_run=self.root_run,
        )
        History.objects.create(
            journal=journal,
            leave_type_before=Journal.LeaveType.FULL,
            source=History.Source.MANUAL,
            changed_by=self.poster,
        )
        History.objects.create(
            journal=journal,
            leave_type_after=Journal.LeaveType.FULL,
            source=History.Source.MANUAL,
            changed_by=other_user,
        )

        text = self.opened_text(self.shortcut_payload(self.reply_ts, thread_ts=self.root_ts))
        assert "Kept a value set outside this thread" in text
        assert "Journal history" in text
        assert "No leave/WFH → Leave (full), by Alex Admin in Timur" in text
        assert "Leave (full) → No leave/WFH, by you in Timur" in text
        root_permalink = f"https://example.slack.com/archives/{CHANNEL_ID}/p{self.root_ts.replace('.', '')}"
        assert f"No leave/WFH → Leave (full), by Timur from <{root_permalink}|this thread>" in text

    def test_history_of_admin_change(self):
        journal = JournalFactory.create(user=self.poster, date=self.date, leave_type=Journal.LeaveType.FULL)
        JournalAvailabilityHistory.objects.create(
            journal=journal,
            leave_type_after=Journal.LeaveType.FULL,
            source=JournalAvailabilityHistory.Source.ADMIN,
            changed_by=UserFactory.create(first_name="Alex", last_name="Admin"),
        )
        text = self.opened_text(self.shortcut_payload(self.reply_ts, thread_ts=self.root_ts))
        assert "No leave/WFH → Leave (full), by Alex Admin in Timur admin, " in text

    def test_history_of_deleted_run(self):
        journal = JournalFactory.create(user=self.poster, date=self.date, leave_type=Journal.LeaveType.FULL)
        JournalAvailabilityHistory.objects.create(
            journal=journal,
            leave_type_after=Journal.LeaveType.FULL,
            source=JournalAvailabilityHistory.Source.SLACK_TIMUR,
        )
        text = self.opened_text(self.shortcut_payload(self.reply_ts, thread_ts=self.root_ts))
        assert "No leave/WFH → Leave (full), by Timur from a Slack thread" in text

    def test_no_run(self):
        SlackAvailabilityThreadFactory.create(thread_ts="1760000300.000100", slack_user_id="U-AUTHOR", is_deleted=True)
        old_ts = f"{time.time() - 60 * 60 * 24 * 100:.6f}"
        recent_ts = f"{time.time() - 60:.6f}"
        for payload, expected in [
            (self.shortcut_payload(recent_ts, channel="C-OTHER"), f"Timur only reads messages in <#{CHANNEL_ID}>."),
            (self.shortcut_payload(recent_ts, bot_id="B1"), "Timur doesn't read messages from bots or apps."),
            (
                self.shortcut_payload(recent_ts, thread_ts="1760000300.000100"),
                "The first message of this thread was deleted, so Timur stopped reading it.",
            ),
            (
                self.shortcut_payload(recent_ts, thread_ts=self.root_ts, user="U-REPLIER", author="U-REPLIER"),
                "Timur only reads messages from the person who started the thread.",
            ),
            (self.shortcut_payload(old_ts), "Timur keeps the details of a message for 90 days"),
            (self.shortcut_payload(recent_ts), "Timur has no record of reading this message."),
        ]:
            assert expected in self.opened_text(payload), expected

    def test_off_mode(self):
        with override_settings(SLACK_AVAILABILITY_MODE="off"):
            text = self.opened_text(self.shortcut_payload(self.reply_ts, thread_ts=self.root_ts))
        assert "Timur isn't reading availability messages right now." in text

    def test_other_shortcuts_are_ignored(self):
        assert self.post({**self.shortcut_payload(self.reply_ts), "callback_id": "other"}).status_code == 200
        assert self.slack.views == []

    def test_history_without_workspace_url(self):
        journal = JournalFactory.create(user=self.poster, date=self.date, leave_type=Journal.LeaveType.FULL)
        JournalAvailabilityHistory.objects.create(
            journal=journal,
            leave_type_after=Journal.LeaveType.FULL,
            source=JournalAvailabilityHistory.Source.SLACK_TIMUR,
            slack_availability_run=self.root_run,
        )
        self.slack.fetch_workspace_url = mock.Mock(side_effect=ConnectionError("Slack is down"))
        with self.assertLogs("apps.slack_availability.links", level="WARNING"):
            text = self.opened_text(self.shortcut_payload(self.reply_ts, thread_ts=self.root_ts))
        assert "No leave/WFH → Leave (full), by Timur from this thread" in text
