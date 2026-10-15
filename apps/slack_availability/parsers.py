import abc
import datetime
import json
import logging
import typing

import requests

from main import config
from main.logging import log_extra

from .structs import AvailabilityRange, Half, MissingDetail, ParseResult, ThreadMessage, UnclearPart

logger = logging.getLogger(__name__)


class AvailabilityParserError(Exception): ...


class AvailabilityParser(abc.ABC):
    """
    Extract the author's leave/WFH from a Slack thread
    """

    @abc.abstractmethod
    def parse(self, messages: list[ThreadMessage], today: datetime.date) -> ParseResult: ...


HALF_VALUES = [half.value for half in Half]
NONE_VALUE = "none"

ABOUT_AVAILABILITY_KEY = "is_about_poster_availability"
NEEDS_CARE_KEY = "needs_care"

OUTPUT_SCHEMA: dict[str, typing.Any] = {
    "type": "object",
    # The model fills properties in this order, so it decides relevance before anything else
    "properties": {
        ABOUT_AVAILABILITY_KEY: {"type": "boolean"},
        "availability": {
            "type": "array",
            "items": {
                "type": "object",
                # Quoting the words first ties the dates to them
                "properties": {
                    "source_phrase": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, inclusive"},
                    "leave": {"type": "string", "enum": [NONE_VALUE, *HALF_VALUES]},
                    "wfh": {"type": "string", "enum": [NONE_VALUE, *HALF_VALUES]},
                    "open_end": {"type": "boolean"},
                },
                "required": ["source_phrase", "start_date", "end_date", "leave", "wfh", "open_end"],
            },
        },
        "unclear": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phrase": {"type": "string"},
                    "missing": {"type": "string", "enum": [detail.value for detail in MissingDetail]},
                },
                "required": ["phrase", "missing"],
            },
        },
        NEEDS_CARE_KEY: {"type": "boolean"},
        "confidence": {"type": "number"},
    },
    "required": [ABOUT_AVAILABILITY_KEY, "availability", "unclear", NEEDS_CARE_KEY, "confidence"],
}

SYSTEM_PROMPT = """
You read Slack messages that one person (the author) posted in their team's availability channel.
Work out the author's own leave and work-from-home (WFH) days.

Input:
- A calendar listing every date with its weekday. Always look dates up in it; never compute weekdays yourself.
- The messages of one thread, oldest first. The first message is the original post, the rest are the author's replies.
- Each message starts with [time it was posted | today = ... | tomorrow = ... | day after tomorrow = ...].

First decide is_about_poster_availability:
- true only if the author states, as a decision, that they take leave (leave, off, half day, sick, out of office,
  not coming in) or work from home (WFH, work from home, remote), or changes or cancels such a plan.
- false when none of those is stated: being late, missing the standup or a meeting, stepping out, heading out or
  leaving early, resting, errands, appointments, being in office, greetings, posts about other people.
- A visit, errand or appointment (a doctor or hospital visit included) for part of the day, with a time they will be
  back, in or online ("back by noon", "in by 11", "online once it's done"), is not leave or WFH for that day, and
  neither is working remotely only until they get to the office. Return no range for it. An explicit half-day
  leave or WFH for one half ("WFH for the second half after the appointment") is still a range.
- false for conditional or uncertain plans ("might", "may", "maybe", "if", "depending on", "will decide").
  When a message has both a definite plan and a conditional one, it is true: return the definite part as ranges
  and leave out only the conditional part.
- true when the absence itself is decided but its details are still open: the dates are not given yet
  ("off for a few days later this month, dates to follow"), or the author only says they will not be at the office
  without saying whether they take leave or work from home. These go in "unclear" (see Rules).
- When false, return an empty "availability" and an empty "unclear".

Resolve dates:
- Take each range's dates only from its source_phrase, resolved against the header of the message containing it.
- A phrase with no date word is the posting date of its message ("today" in the header), whatever the time of day.
  "tomorrow" and "day after tomorrow" are also in the header.
- A weekday name ("Monday", "on Thursday", "next Tuesday", "this Friday") means the first date with that weekday
  after the posting date. In a range ("Thursday to next Tuesday"), the end is the first such weekday after the start.
- "This week" / "this entire week" means the posting date to Friday of that week, never later.
- "Next week" means Monday to Friday of the week after the posting date. Saturday and Sunday are the weekend.
- Dates far in the future are fine: output them with the correct year. They are never unclear.
- An absence with a start but no end ("till further notice", "until I recover", "for a while") is a range for its
  start day only (the posting date unless a start is given) with open_end true, plus an "unclear" entry for the
  rest with missing "end_date". Every other range has open_end false.
- Dates are inclusive ranges. A single day has start_date equal to end_date. Output dates as YYYY-MM-DD.

Romanized Nepali:
- aaja / aja = today, bholi = tomorrow, parsi = day after tomorrow
- bida / chhutti / chutti = leave, ghar bata kaam / ghar bata = WFH
- bihana = morning (first half), diuso / beluka = afternoon / evening (second half)

For each date range, set:
- source_phrase: the exact words from the messages this range comes from, copied as written (keep it short).
- leave: "full" (whole day off, sick, out of office), "first_half", "second_half", "half_unknown" or "none".
- wfh: "full", "first_half", "second_half", "half_unknown" or "none", with the same meaning for working from home.
- A day can combine a half-day leave with WFH for the other half.
- Any half marker sets that half: "first half", "1st half", "morning", "bihana" -> first_half; "second half",
  "2nd half", "afternoon", "after lunch", "rest of the day", "beluka" -> second_half. This includes "leave for the
  second half", "first half leave", "heading home for the second half".
- "half_unknown" only when "half day" is stated with no marker at all. Never guess the half from the posting time.
- WFH with no half ("WFH today", "working remotely today", "WFH in limited capacity") is wfh "full".
- Leaving the office during the day and continuing remotely or from home for the rest of the day is wfh
  "second_half".

The answer is the final state of the whole thread:
- Read the replies as corrections to the earlier messages and apply them in order.
- A reply that changes the type ("make it WFH instead") changes those days and keeps the dates.
- A reply that limits the dates ("only Aug 24 and 25") keeps exactly those dates and drops the others.
- A reply that cancels days ("cancel that", "no leave on Wed", "I'm coming in after all") drops only those days.
- A reply that names a half ("second half", "morning") resolves an earlier "half_unknown" day.
- Days the replies do not mention keep what the earlier messages said.

Rules:
- Only the author. Ignore anything about other people (mentions like <@U123>). If the author writes about someone
  else and also about themselves, return only the author's part.
- "unclear" is for a decided absence of the author that cannot be written as a range. Each entry quotes the
  phrase from the message and says what is missing:
  - "end_date": it starts on a known day but has no end (see Resolve dates).
  - "dates": its dates cannot be worked out ("next week sometime", "a few days").
  - "type": they will not be at the office but nothing says whether they are off or working from home.
  - "dates_and_type": both.
  Words that mean not working (off, leave, sick, unwell, away, out of office, not available) are leave, so the type
  is stated. So is the author's own illness or medical reason when they say or imply they will not work that
  day; not when they give a time they will be back or say they are working. A half day with no half marker is
  leave "half_unknown", not unclear.
  Do not guess and do not return a range for the unclear part; still return ranges for the parts whose dates and
  type are clear.
- needs_care: true when the author or their family is going through something hard: being sick or injured,
  a hospital stay, a medical emergency, a pregnancy or childbirth complication, a death or another emergency.
  False for routine checkups, follow-ups, tests and planned appointments, and for everything else.
- confidence: 0 to 1, how sure you are about the whole answer.

Examples (posted on Mon 2026-10-12 at 14:00), as source_phrase -> start_date..end_date leave/wfh:
- "On leave tomorrow" -> 2026-10-13..2026-10-13 leave full
- "bholi ghar bata kaam" -> 2026-10-13..2026-10-13 wfh full
- "Sick, not coming in" -> 2026-10-12..2026-10-12 leave full
- "I'll be on leave for the second half" -> 2026-10-12..2026-10-12 leave second_half
- "Train got cancelled, so first half leave" -> 2026-10-12..2026-10-12 leave first_half
- "Half day leave today" -> 2026-10-12..2026-10-12 leave half_unknown
- "WFH today, limited availability" -> 2026-10-12..2026-10-12 wfh full
- "Leaving at 3, will continue from home" -> 2026-10-12..2026-10-12 wfh second_half
- "WFH second half today, leave tomorrow" -> 2026-10-12..2026-10-12 wfh second_half and
  2026-10-13..2026-10-13 leave full
- "Working from home this entire week" -> 2026-10-12..2026-10-16 wfh full
- "Taking half day leave on Thursday", then reply "second half" -> 2026-10-15..2026-10-15 leave second_half
- "Leave Tue to Thu", then reply "only Tue and Wed" -> 2026-10-13..2026-10-14 leave full
- "Off on Thursday, plus a few more days later this month, dates to follow" -> 2026-10-15..2026-10-15 leave full,
  and unclear "a few more days later this month" missing "dates"
- "Won't be at the office tomorrow, have to sort out some things at home" -> no range, unclear "Won't be at the
  office tomorrow" missing "type"
- "My father is in the ICU, I'm off until things settle" -> 2026-10-12..2026-10-12 leave full open_end, unclear
  "off until things settle" missing "end_date", needs_care true
- "Down with the flu since Friday, off until I recover" -> 2026-10-09..2026-10-09 leave full open_end, unclear
  "off until I recover" missing "end_date", needs_care true
- is_about_poster_availability false: "Running 30 mins late", "Will miss the standup today", "Heading out early
  to rest", "In office today but leaving at 4", "Might WFH tomorrow if the plumber comes",
  "<@U0123> is sick today, they asked me to post"
""".strip()

CALENDAR_DAYS_AHEAD = 21


def format_date(date: datetime.date) -> str:
    return date.strftime("%a %Y-%m-%d")


def format_calendar(start_date: datetime.date, end_date: datetime.date) -> str:
    """
    One line per week (Monday to Sunday) covering start_date to end_date
    """
    first_day = start_date - datetime.timedelta(days=start_date.weekday())
    lines = []
    week_start = first_day
    while week_start <= end_date:
        week = [week_start + datetime.timedelta(days=x) for x in range(7)]
        lines.append(", ".join(format_date(date) for date in week))
        week_start += datetime.timedelta(days=7)
    return "\n".join(lines)


def format_message(message: ThreadMessage) -> str:
    posted_on = message.posted_at.date()
    tomorrow = posted_on + datetime.timedelta(days=1)
    day_after_tomorrow = posted_on + datetime.timedelta(days=2)
    header = " | ".join(
        [
            message.posted_at.strftime("%a %Y-%m-%d %H:%M"),
            f"today = {format_date(posted_on)}",
            f"tomorrow = {format_date(tomorrow)}",
            f"day after tomorrow = {format_date(day_after_tomorrow)}",
        ],
    )
    return f"[{header}] {message.text}"


def format_thread(messages: list[ThreadMessage]) -> str:
    return "\n".join(format_message(message) for message in messages)


def build_user_prompt(messages: list[ThreadMessage], today: datetime.date) -> str:
    posted_dates = [message.posted_at.date() for message in messages]
    calendar_start = min([today, *posted_dates])
    calendar_end = max([today, *posted_dates]) + datetime.timedelta(days=CALENDAR_DAYS_AHEAD)
    return (
        f"Today is {format_date(today)} ({config.TIME_ZONE}).\n\n"
        f"Calendar:\n{format_calendar(calendar_start, calendar_end)}\n\n"
        f"Messages:\n{format_thread(messages)}"
    )


def _parse_half(value: typing.Any) -> Half | None:
    if value in (None, NONE_VALUE):
        return None
    try:
        return Half(value)
    except ValueError as e:
        raise AvailabilityParserError(f"Invalid leave/wfh value: {value}") from e


def _parse_date(value: typing.Any) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise AvailabilityParserError(f"Invalid date: {value}") from e


def _parse_unclear(item: typing.Any) -> UnclearPart | None:
    if isinstance(item, str):
        return UnclearPart(phrase=item.strip()) if item.strip() else None
    if not isinstance(item, dict):
        raise AvailabilityParserError("Invalid unclear item")
    phrase = str(item.get("phrase") or "").strip()
    if not phrase:
        return None
    try:
        missing = MissingDetail(item.get("missing"))
    except ValueError:
        missing = MissingDetail.DATES_AND_TYPE
    return UnclearPart(phrase=phrase, missing=missing)


def parse_output(data: typing.Any, prompt: str = "", model: str = "") -> ParseResult:
    """
    Validate the parser output (OUTPUT_SCHEMA)
    """
    if not isinstance(data, dict):
        raise AvailabilityParserError("Output is not an object")

    is_about_availability = data.get(ABOUT_AVAILABILITY_KEY)
    availability = data.get("availability")
    unclear = data.get("unclear") or []
    confidence = data.get("confidence")
    if not isinstance(is_about_availability, bool):
        raise AvailabilityParserError(f"Invalid {ABOUT_AVAILABILITY_KEY}")
    if not isinstance(availability, list) or not isinstance(unclear, list):
        raise AvailabilityParserError("Invalid availability/unclear")
    if not isinstance(confidence, int | float):
        raise AvailabilityParserError("Invalid confidence")

    ranges = []
    for item in availability:
        if not isinstance(item, dict):
            raise AvailabilityParserError("Invalid availability item")
        ranges.append(
            AvailabilityRange(
                start_date=_parse_date(item.get("start_date")),
                end_date=_parse_date(item.get("end_date")),
                leave=_parse_half(item.get("leave")),
                wfh=_parse_half(item.get("wfh")),
                source_phrase=str(item.get("source_phrase") or "").strip(),
                open_end=item.get("open_end") is True,
            ),
        )

    return ParseResult(
        is_about_availability=is_about_availability,
        ranges=ranges,
        unclear=[part for part in map(_parse_unclear, unclear) if part],
        confidence=float(confidence),
        raw=data,
        prompt=prompt,
        model=model,
        needs_care=data.get(NEEDS_CARE_KEY) is True,
    )


class OllamaAvailabilityParser(AvailabilityParser):
    """
    Uses Ollama's chat API with structured outputs
    https://github.com/ollama/ollama/blob/main/docs/api.md#generate-a-chat-completion
    """

    def __init__(self, ollama_config: config.SlackAvailability.OllamaConfig):
        self.config = ollama_config

    @typing.override
    def parse(self, messages: list[ThreadMessage], today: datetime.date) -> ParseResult:
        prompt = build_user_prompt(messages, today)
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        try:
            response = requests.post(
                f"{self.config.base_url.rstrip('/')}/api/chat",
                headers=headers,
                json={
                    "model": self.config.model,
                    "stream": False,
                    "format": OUTPUT_SCHEMA,
                    # A fixed num_ctx avoids model reloads on the shared GPU server
                    "options": {"temperature": 0, "num_ctx": self.config.num_ctx},
                    "think": False,
                    "keep_alive": self.config.keep_alive,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            data = json.loads(content)
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            logger.warning("Ollama request failed", exc_info=True, extra=log_extra({"model": self.config.model}))
            raise AvailabilityParserError("Ollama request failed") from e

        return parse_output(data, prompt=prompt, model=self.config.model)


PARSERS: dict[str, typing.Callable[[], AvailabilityParser]] = {
    "ollama": lambda: OllamaAvailabilityParser(config.SlackAvailability.load_ollama_config()),
}


def get_parser() -> AvailabilityParser:
    parser_name = config.SlackAvailability.load_config().parser
    if parser_name not in PARSERS:
        raise AvailabilityParserError(f"Unknown parser: {parser_name}")
    return PARSERS[parser_name]()
