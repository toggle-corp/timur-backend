import dataclasses
import typing

from .models import SlackAvailabilityRun

Trigger = SlackAvailabilityRun.Trigger

# Message subtypes that carry a user's own text
USER_MESSAGE_SUBTYPES = {None, "thread_broadcast", "file_share"}


@dataclasses.dataclass(frozen=True)
class SlackMessageEvent:
    """
    A Slack message event that can change a thread's availability
    """

    trigger: Trigger
    channel_id: str
    thread_ts: str
    slack_user_id: str
    event_ts: str
    """When the event happened. Sets "today" for the run"""
    trigger_ts: str | None
    """Message to react on. None when the message is deleted"""
    deleted_ts: str | None = None

    @property
    def is_parent_deleted(self) -> bool:
        return self.trigger == Trigger.DELETE and self.thread_ts == self.deleted_ts

    def as_dict(self) -> dict[str, typing.Any]:
        """
        JSON-serializable form, used as the Celery task argument
        """
        return {**dataclasses.asdict(self), "trigger": self.trigger.value}

    @classmethod
    def from_dict(cls, data: dict[str, typing.Any]) -> typing.Self:
        return cls(**{**data, "trigger": Trigger(data["trigger"])})


def _is_user_message(message: dict) -> bool:
    return bool(message.get("user")) and not message.get("bot_id") and message.get("subtype") in USER_MESSAGE_SUBTYPES


def classify_event(event: dict, channel_id: str) -> SlackMessageEvent | None:
    """
    Return the event to process, or None when it is ignored

    https://docs.slack.dev/reference/events/message
    """
    if event.get("type") != "message" or event.get("channel") != channel_id:
        return None

    subtype = event.get("subtype")
    event_ts = event.get("event_ts") or event.get("ts")
    if not event_ts:
        return None

    if subtype in USER_MESSAGE_SUBTYPES:
        if not _is_user_message(event):
            return None
        ts = event["ts"]
        thread_ts = event.get("thread_ts") or ts
        return SlackMessageEvent(
            trigger=Trigger.REPLY if thread_ts != ts else Trigger.MESSAGE,
            channel_id=channel_id,
            thread_ts=thread_ts,
            slack_user_id=event["user"],
            event_ts=event_ts,
            trigger_ts=ts,
        )

    if subtype == "message_changed":
        message = event.get("message") or {}
        previous_message = event.get("previous_message") or {}
        ts = message.get("ts")
        if not ts:
            return None
        thread_ts = message.get("thread_ts") or ts

        if message.get("subtype") == "tombstone":
            # A top-level message with replies is replaced by a tombstone when deleted
            if not _is_user_message(previous_message):
                return None
            return SlackMessageEvent(
                trigger=Trigger.DELETE,
                channel_id=channel_id,
                thread_ts=thread_ts,
                slack_user_id=previous_message["user"],
                event_ts=event_ts,
                trigger_ts=None,
                deleted_ts=ts,
            )

        if not _is_user_message(message):
            return None
        # Slack also sends message_changed for metadata updates (e.g. reply count)
        if message.get("text") == previous_message.get("text"):
            return None
        return SlackMessageEvent(
            trigger=Trigger.EDIT,
            channel_id=channel_id,
            thread_ts=thread_ts,
            slack_user_id=message["user"],
            event_ts=event_ts,
            trigger_ts=ts,
        )

    if subtype == "message_deleted":
        previous_message = event.get("previous_message") or {}
        deleted_ts = event.get("deleted_ts") or previous_message.get("ts")
        if not deleted_ts or not _is_user_message(previous_message):
            return None
        return SlackMessageEvent(
            trigger=Trigger.DELETE,
            channel_id=channel_id,
            thread_ts=previous_message.get("thread_ts") or deleted_ts,
            slack_user_id=previous_message["user"],
            event_ts=event_ts,
            trigger_ts=None,
            deleted_ts=deleted_ts,
        )

    return None
