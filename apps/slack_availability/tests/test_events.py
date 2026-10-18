import json

from apps.slack_availability.events import SlackMessageEvent, classify_event
from apps.slack_availability.models import SlackAvailabilityRun

from . import CHANNEL_ID, message_event, slack_message

Trigger = SlackAvailabilityRun.Trigger

PARENT_TS = "1760000000.000100"
REPLY_TS = "1760000100.000100"
EVENT_TS = "1760000200.000100"


def test_new_message():
    assert classify_event(message_event("U1", "Leave today", PARENT_TS), CHANNEL_ID) == SlackMessageEvent(
        trigger=Trigger.MESSAGE,
        channel_id=CHANNEL_ID,
        thread_ts=PARENT_TS,
        slack_user_id="U1",
        event_ts=PARENT_TS,
        trigger_ts=PARENT_TS,
    )


def test_thread_reply():
    event = message_event("U1", "second half", REPLY_TS, thread_ts=PARENT_TS, parent_user_id="U1")
    assert classify_event(event, CHANNEL_ID) == SlackMessageEvent(
        trigger=Trigger.REPLY,
        channel_id=CHANNEL_ID,
        thread_ts=PARENT_TS,
        slack_user_id="U1",
        event_ts=REPLY_TS,
        trigger_ts=REPLY_TS,
    )
    # Reply also sent to the channel
    event = message_event("U1", "second half", REPLY_TS, thread_ts=PARENT_TS, subtype="thread_broadcast")
    classified = classify_event(event, CHANNEL_ID)
    assert classified is not None
    assert classified.trigger == Trigger.REPLY


def test_ignored_events():
    for event in [
        # Other channel
        {**message_event("U1", "Leave today", PARENT_TS), "channel": "C-OTHER"},
        # Not a message
        {**message_event("U1", "Leave today", PARENT_TS), "type": "reaction_added"},
        # Bots (including Timur)
        message_event("U1", "Leave today", PARENT_TS, bot_id="B1"),
        message_event("U1", "Leave today", PARENT_TS, subtype="bot_message"),
        # Other subtypes
        message_event("U1", "joined", PARENT_TS, subtype="channel_join"),
        # No user
        {**message_event("U1", "Leave today", PARENT_TS), "user": None},
    ]:
        assert classify_event(event, CHANNEL_ID) is None, event


def test_edit():
    parent = slack_message("U1", "Leave today", PARENT_TS)
    event = {
        "type": "message",
        "subtype": "message_changed",
        "channel": CHANNEL_ID,
        "ts": EVENT_TS,
        "event_ts": EVENT_TS,
        "message": {**parent, "text": "Leave tomorrow"},
        "previous_message": parent,
    }
    assert classify_event(event, CHANNEL_ID) == SlackMessageEvent(
        trigger=Trigger.EDIT,
        channel_id=CHANNEL_ID,
        thread_ts=PARENT_TS,
        slack_user_id="U1",
        event_ts=EVENT_TS,
        trigger_ts=PARENT_TS,
    )

    # Edit of a reply
    reply = slack_message("U1", "second half", REPLY_TS, thread_ts=PARENT_TS)
    classified = classify_event(
        {**event, "message": {**reply, "text": "first half"}, "previous_message": reply},
        CHANNEL_ID,
    )
    assert classified is not None
    assert classified.thread_ts == PARENT_TS
    assert classified.trigger_ts == REPLY_TS

    # Metadata update without text change
    assert classify_event({**event, "message": {**parent, "reply_count": 2}}, CHANNEL_ID) is None


def test_delete():
    parent = slack_message("U1", "Leave today", PARENT_TS)
    event = {
        "type": "message",
        "subtype": "message_deleted",
        "channel": CHANNEL_ID,
        "ts": EVENT_TS,
        "event_ts": EVENT_TS,
        "deleted_ts": PARENT_TS,
        "previous_message": parent,
    }
    classified = classify_event(event, CHANNEL_ID)
    assert classified is not None
    assert classified == SlackMessageEvent(
        trigger=Trigger.DELETE,
        channel_id=CHANNEL_ID,
        thread_ts=PARENT_TS,
        slack_user_id="U1",
        event_ts=EVENT_TS,
        trigger_ts=None,
        deleted_ts=PARENT_TS,
    )
    assert classified.is_parent_deleted

    # Reply deleted
    reply = slack_message("U1", "second half", REPLY_TS, thread_ts=PARENT_TS)
    classified = classify_event({**event, "deleted_ts": REPLY_TS, "previous_message": reply}, CHANNEL_ID)
    assert classified is not None
    assert classified.thread_ts == PARENT_TS
    assert not classified.is_parent_deleted

    # Bot message deleted
    assert classify_event({**event, "previous_message": {**parent, "bot_id": "B1"}}, CHANNEL_ID) is None


def test_parent_with_replies_deleted():
    parent = slack_message("U1", "Leave today", PARENT_TS)
    event = {
        "type": "message",
        "subtype": "message_changed",
        "channel": CHANNEL_ID,
        "ts": EVENT_TS,
        "event_ts": EVENT_TS,
        "message": {
            "type": "message",
            "subtype": "tombstone",
            "text": "This message was deleted.",
            "ts": PARENT_TS,
            "thread_ts": PARENT_TS,
            "user": "USLACKBOT",
        },
        "previous_message": parent,
    }
    classified = classify_event(event, CHANNEL_ID)
    assert classified is not None
    assert classified.trigger == Trigger.DELETE
    assert classified.slack_user_id == "U1"
    assert classified.is_parent_deleted


def test_event_dict_round_trip():
    for event in [
        message_event("U1", "Leave today", "1760000000.000100"),
        {
            "type": "message",
            "subtype": "message_deleted",
            "channel": CHANNEL_ID,
            "ts": "1760000001.000100",
            "event_ts": "1760000001.000100",
            "deleted_ts": "1760000000.000200",
            "previous_message": slack_message(
                "U1",
                "Leave today",
                "1760000000.000200",
                thread_ts="1760000000.000100",
            ),
        },
    ]:
        message_event_ = classify_event(event, CHANNEL_ID)
        assert message_event_ is not None
        data = json.loads(json.dumps(message_event_.as_dict()))
        assert SlackMessageEvent.from_dict(data) == message_event_
