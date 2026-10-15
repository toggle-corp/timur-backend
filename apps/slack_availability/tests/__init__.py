import datetime
import typing

from django.utils import timezone
from slack_sdk.models.blocks.blocks import Block
from slack_sdk.web.slack_response import SlackResponse

from apps.slack_availability.parsers import AvailabilityParser, build_user_prompt
from apps.slack_availability.structs import AvailabilityRange, ParseResult, ThreadMessage, UnclearPart
from utils.slack import TimurSlack

CHANNEL_ID = "C-AVAILABILITY"
SIGNING_SECRET = "test-signing-secret"

AVAILABILITY_SETTINGS = dict(
    SLACK_AVAILABILITY_MODE="live",
    SLACK_AVAILABILITY_CHANNEL_ID=CHANNEL_ID,
    SLACK_SIGNING_SECRET=SIGNING_SECRET,
    SLACK_AVAILABILITY_PARSER="ollama",
    OLLAMA_BASE_URL="http://ollama.test",
    OLLAMA_MODEL="test-model",
    OLLAMA_API_KEY="test-api-key",
    OLLAMA_TIMEOUT_SECONDS=5,
    OLLAMA_NUM_CTX=4096,
    OLLAMA_KEEP_ALIVE="5m",
)


def next_monday() -> datetime.date:
    today = datetime.date.today()
    return today + datetime.timedelta(days=7 - today.weekday())


def ts_at(date: datetime.date, hour: int = 9, minute: int = 0, second: int = 0) -> str:
    """
    Slack ts for a local (app timezone) time
    """
    local_dt = datetime.datetime(
        date.year,
        date.month,
        date.day,
        hour,
        minute,
        second,
        tzinfo=timezone.get_current_timezone(),
    )
    return f"{local_dt.timestamp():.6f}"


def slack_message(user: str, text: str, ts: str, thread_ts: str | None = None, **kwargs) -> dict:
    message = {"type": "message", "user": user, "text": text, "ts": ts, **kwargs}
    if thread_ts:
        message["thread_ts"] = thread_ts
    return message


def message_event(user: str, text: str, ts: str, thread_ts: str | None = None, **kwargs) -> dict:
    return {
        **slack_message(user, text, ts, thread_ts),
        "channel": CHANNEL_ID,
        "channel_type": "channel",
        "event_ts": ts,
        **kwargs,
    }


class FakeSlack(TimurSlack):
    def __init__(
        self,
        threads: dict[str, list[dict]] | None = None,
        emails: dict[str, str] | None = None,
    ):
        self.threads = threads or {}
        self.emails = emails or {}
        self.reactions: list[tuple[str, str]] = []
        self.posted: list[dict] = []
        self.views: list[tuple[str, dict]] = []
        self.channel = "C-STANDUP"

    @typing.override
    def fetch_thread_messages(self, channel: str, thread_ts: str) -> list[dict]:
        return list(self.threads.get(thread_ts, []))

    @typing.override
    def fetch_user_email(self, slack_user_id: str) -> str | None:
        return self.emails.get(slack_user_id)

    @typing.override
    def add_reaction(self, channel: str, ts: str, name: str):
        if (ts, name) not in self.reactions:
            self.reactions.append((ts, name))

    @typing.override
    def open_view(self, trigger_id: str, view: dict):
        self.views.append((trigger_id, view))

    @typing.override
    def send_slack_message(
        self,
        text: str | None = None,
        blocks: str | typing.Sequence[dict | Block] | None = None,
        thread_ts: str | None = None,
        channel: str | None = None,
    ) -> SlackResponse:
        self.posted.append({"text": text, "blocks": blocks, "thread_ts": thread_ts, "channel": channel})
        return typing.cast("SlackResponse", {"ts": f"9999999999.{len(self.posted):06d}"})


class FakeParser(AvailabilityParser):
    def __init__(
        self,
        ranges: list[AvailabilityRange] | None = None,
        unclear: list[str | UnclearPart] | None = None,
        confidence: float = 0.9,
        is_about_availability: bool = True,
        needs_care: bool = False,
    ):
        self.is_about_availability = is_about_availability
        self.ranges = ranges or []
        self.unclear = [UnclearPart(part) if isinstance(part, str) else part for part in unclear or []]
        self.needs_care = needs_care
        self.confidence = confidence
        self.calls: list[tuple[list[ThreadMessage], datetime.date]] = []

    @typing.override
    def parse(self, messages: list[ThreadMessage], today: datetime.date) -> ParseResult:
        self.calls.append((messages, today))
        return ParseResult(
            is_about_availability=self.is_about_availability,
            ranges=self.ranges,
            unclear=self.unclear,
            confidence=self.confidence,
            raw={"fake": True},
            prompt=build_user_prompt(messages, today),
            model="fake-model",
            needs_care=self.needs_care,
        )
