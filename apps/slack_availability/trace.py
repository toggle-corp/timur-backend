"""
How Timur read a thread: the steps of a run, stored on the run and shown to the poster in a Slack modal

The trace is built by code from what the run did. The only parser-written text is the source phrase of each range.
"""

import datetime
import html
import re
import typing

from apps.common.models import Event

from .dates import MAX_DAYS_AHEAD
from .guards import GuardKind, GuardResult
from .messages import escape, format_date
from .reconcile import ChangeAction, PlannedChange
from .structs import AvailabilityRange, DayState, Half, MissingDetail, ParseResult, ThreadMessage, UnclearPart

TRACE_VERSION = 1

# https://docs.slack.dev/reference/block-kit/blocks/section-block/
MAX_TEXT_LENGTH = 3000
# https://docs.slack.dev/surfaces/modals/
MAX_MODAL_BLOCKS = 100
# Longest range expanded in the trace, to bound the work on parser output like a year-long range
MAX_TRACE_RANGE_DAYS = 400

HALF_LABEL = {
    Half.FULL.value: "full",
    Half.FIRST_HALF.value: "first half",
    Half.SECOND_HALF.value: "second half",
    Half.UNKNOWN.value: "half day, which half unknown",
}


IGNORED_REASON = {
    GuardKind.CONDITIONAL.value: "depends on a condition or is not certain",
    GuardKind.EARLY_DEPARTURE.value: "only says you leave early, not a leave or WFH",
}


class SkipReason:
    BEFORE_TODAY = "before the message date"
    TOO_FAR = f"more than {MAX_DAYS_AHEAD} days ahead"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"


def _holiday_names(start_date: datetime.date, end_date: datetime.date) -> dict[datetime.date, str]:
    holiday_dates = set(Event.get_relative_event_dates())
    names: dict[datetime.date, str] = {}
    for name, event_start, event_end in (
        Event.get_relative_non_working_events()
        .filter(start_date__lte=end_date, end_date__gte=start_date)
        .order_by("start_date")
        .values_list("name", "start_date", "end_date")
    ):
        for x in range((event_end - event_start).days + 1):
            date = event_start + datetime.timedelta(days=x)
            if date in holiday_dates:
                names.setdefault(date, name)
    return names


def _group_skipped(skipped: list[tuple[datetime.date, str]]) -> list[dict]:
    """
    Collapse consecutive dates with the same reason into ranges
    """
    groups: list[dict] = []
    for date, reason in skipped:
        last = groups[-1] if groups else None
        if (
            last is not None
            and last["reason"] == reason
            and datetime.date.fromisoformat(last["end_date"]) + datetime.timedelta(days=1) == date
        ):
            last["end_date"] = date.isoformat()
            continue
        groups.append({"start_date": date.isoformat(), "end_date": date.isoformat(), "reason": reason})
    return groups


def _range_note(availability_range: AvailabilityRange) -> str | None:
    if availability_range.open_end:
        return "no end date yet, so I set it from today and asked"
    if availability_range.has_unknown_half:
        return "which half is unknown, so I asked"
    state = availability_range.as_day_state()
    if state.is_empty:
        return "no leave or WFH"
    if not state.is_valid:
        return "this leave + WFH combination is not allowed in the journal, so I ignored it"
    return None


def _range_dict(availability_range: AvailabilityRange) -> dict:
    return {
        "source_phrase": availability_range.source_phrase,
        "start_date": availability_range.start_date.isoformat(),
        "end_date": availability_range.end_date.isoformat(),
        "leave": availability_range.leave.value if availability_range.leave else None,
        "wfh": availability_range.wfh.value if availability_range.wfh else None,
    }


def describe_range(
    availability_range: AvailabilityRange,
    today: datetime.date,
    corrections: list[dict] | None = None,
) -> dict:
    """
    The range as read, and the working days it covers (same rules as dates.expand_ranges)

    corrections lists what the guards changed, each with the range before the change.
    """
    start_date, end_date = sorted([availability_range.start_date, availability_range.end_date])
    if availability_range.open_end:
        end_date = max(end_date, today)
    end_date = min(end_date, start_date + datetime.timedelta(days=MAX_TRACE_RANGE_DAYS - 1))
    last_date = today + datetime.timedelta(days=MAX_DAYS_AHEAD)
    holiday_names = _holiday_names(start_date, end_date)

    dates: list[str] = []
    skipped: list[tuple[datetime.date, str]] = []
    for x in range((end_date - start_date).days + 1):
        date = start_date + datetime.timedelta(days=x)
        if date < today:
            skipped.append((date, SkipReason.BEFORE_TODAY))
        elif date > last_date:
            skipped.append((date, SkipReason.TOO_FAR))
        elif Event.is_weekend(date):
            skipped.append((date, SkipReason.WEEKEND))
        elif date in holiday_names:
            skipped.append((date, f"{SkipReason.HOLIDAY}: {holiday_names[date]}"))
        else:
            dates.append(date.isoformat())

    return {
        **_range_dict(availability_range),
        "dates": dates,
        "skipped": _group_skipped(skipped),
        "note": _range_note(availability_range),
        "corrections": corrections or [],
    }


def _describe_ranges(
    parse_result: ParseResult,
    guard_result: GuardResult | None,
    today: datetime.date,
) -> list[dict]:
    if guard_result is None:
        return [describe_range(availability_range, today) for availability_range in parse_result.ranges]
    return [
        describe_range(
            availability_range,
            today,
            corrections=[
                {"kind": correction.kind.value, "before": _range_dict(correction.before)}
                for correction in guard_result.corrections_for(index)
            ],
        )
        for index, availability_range in enumerate(guard_result.ranges)
    ]


def build_trace(
    *,
    messages: list[ThreadMessage],
    parse_result: ParseResult,
    today: datetime.date,
    changes: list[PlannedChange] | None,
    unknown_half_dates: list[datetime.date],
    unclear: list[UnclearPart],
    low_confidence: bool = False,
    guard_result: GuardResult | None = None,
) -> dict:
    """
    JSON-serializable steps of a run

    changes is None when the run stopped before the journal step (e.g. low confidence).
    guard_result holds the ranges the run used, when the guards ran.
    """
    is_about_availability = parse_result.is_about_availability
    return {
        "version": TRACE_VERSION,
        "today": today.isoformat(),
        "model": parse_result.model,
        "confidence": parse_result.confidence,
        "is_about_availability": is_about_availability,
        "needs_care": parse_result.needs_care and is_about_availability,
        "low_confidence": low_confidence,
        "messages": [
            {"ts": message.ts, "posted_at": message.posted_at.isoformat(), "text": message.text} for message in messages
        ],
        "ranges": _describe_ranges(parse_result, guard_result, today) if is_about_availability else [],
        "ignored": [
            {**_range_dict(ignored.availability_range), "reason": ignored.kind.value}
            for ignored in (guard_result.ignored if guard_result and is_about_availability else [])
        ],
        "unclear": [part.as_dict() for part in unclear],
        "dates": None
        if changes is None
        else [
            *(change.as_dict() for change in changes),
            *(
                {"date": date.isoformat(), "action": "held"}
                for date in unknown_half_dates
                if date not in {change.date for change in changes}
            ),
        ],
        "purged": False,
    }


def _purge_range(availability_range: dict) -> dict:
    purged = {**availability_range, "source_phrase": ""}
    if "corrections" in availability_range:
        purged["corrections"] = [
            {**correction, "before": {**correction["before"], "source_phrase": ""}}
            for correction in availability_range["corrections"]
        ]
    return purged


def purge_trace(trace: dict | None) -> dict | None:
    """
    Blank message-derived text, keep dates and types
    """
    if not trace:
        return trace
    return {
        **trace,
        "messages": [{**message, "text": ""} for message in trace.get("messages") or []],
        "ranges": [_purge_range(availability_range) for availability_range in trace.get("ranges") or []],
        **({"ignored": [{**ignored, "source_phrase": ""} for ignored in trace["ignored"]]} if "ignored" in trace else {}),
        "unclear": [],
        "purged": True,
    }


# -- Rendering

MISSING_DETAIL_LABEL = {
    MissingDetail.END_DATE: "no end date",
    MissingDetail.DATES: "dates unclear",
    MissingDetail.TYPE: "leave or WFH not stated",
    MissingDetail.DATES_AND_TYPE: "dates or type unclear",
}


def _unclear_line(part: dict | str) -> str:
    # Traces store a phrase string or an UnclearPart dict
    if isinstance(part, str):
        part = {"phrase": part}
    try:
        missing = MissingDetail(part.get("missing"))
    except ValueError:
        missing = MissingDetail.DATES_AND_TYPE
    return f'• "{plain_slack_text(part.get("phrase") or "")}" → {MISSING_DETAIL_LABEL[missing]}, so I asked'


def _date(value: str) -> str:
    return format_date(datetime.date.fromisoformat(value))


def _date_range(start_date: str, end_date: str) -> str:
    if start_date == end_date:
        return _date(start_date)
    return f"{_date(start_date)} to {_date(end_date)}"


def _state_label(state: dict | None) -> str:
    if not state:
        return "empty"
    day_state = DayState(leave_type=state.get("leave_type"), wfh_type=state.get("wfh_type"))
    return "empty" if day_state.is_empty else day_state.label


def _range_type_label(availability_range: dict) -> str:
    parts = []
    if availability_range.get("leave"):
        parts.append(f"Leave ({HALF_LABEL.get(availability_range['leave'], availability_range['leave'])})")
    if availability_range.get("wfh"):
        parts.append(f"WFH ({HALF_LABEL.get(availability_range['wfh'], availability_range['wfh'])})")
    return " + ".join(parts) or "No leave/WFH"


# Slack markup in message text: <@U123>, <#C123|name>, <!channel>, <!subteam^S1|@team>, <https://url|label>
_SLACK_TOKEN_RE = re.compile(r"<([^<>]*)>")


def plain_slack_text(text: str) -> str:
    """
    Message text from Slack (or copied from it by the parser) as mrkdwn safe to quote

    User and channel mentions stay mentions, special mentions and links become plain text, anything else is
    escaped once.
    """
    parts = []
    position = 0
    for match in _SLACK_TOKEN_RE.finditer(text):
        parts.append(escape(html.unescape(text[position : match.start()])))
        token = match.group(1)
        target, _, label = token.partition("|")
        if target.startswith(("@U", "@W", "#C")):
            parts.append(f"<{target}>")
        elif target.startswith("!"):
            name = label or target[1:].split("^")[0]
            parts.append(escape(name if name.startswith("@") else f"@{name}"))
        else:
            parts.append(escape(html.unescape(label or target)))
        position = match.end()
    parts.append(escape(html.unescape(text[position:])))
    return "".join(parts)


def _quote(text: str) -> str:
    return "\n".join(f"> {plain_slack_text(line)}" for line in (text.strip() or " ").splitlines())


def _correction_note(correction: dict) -> str:
    before = correction.get("before") or {}
    if correction.get("kind") == GuardKind.WEEKDAY.value and before.get("start_date"):
        return f"weekday checked, I first read {_date_range(before['start_date'], before['end_date'])}"
    if correction.get("kind") == GuardKind.CONFIRMATION.value:
        return "kept the half from your earlier message"
    return "corrected"


def _date_line(item: dict) -> str | None:
    date = _date(item["date"])
    before = _state_label(item.get("before"))
    after = _state_label(item.get("after"))
    action = item["action"]
    if action == ChangeAction.ADD:
        return f"• {date}: {before} → set {after}"
    if action == ChangeAction.UPDATE:
        return f"• {date}: {before} → updated to {after}"
    if action == ChangeAction.REMOVE:
        return f"• {date}: {before} → removed"
    if action == ChangeAction.SKIP:
        return f"• {date}: you set {before} → left as is (I read {after})"
    if action == ChangeAction.MATCH:
        return f"• {date}: you already set {before} → left as is"
    if action in (ChangeAction.CLAIM, ChangeAction.TRANSFER):
        return f"• {date}: {before}, set from another of your messages → left as is"
    if action == ChangeAction.DROP:
        return f"• {date}: you changed it to {before} → left as is"
    if action == "held":
        return f"• {date}: waiting for which half → left as is"
    return None


def _truncate(text: str, limit: int = MAX_TEXT_LENGTH) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _chunk_lines(lines: list[str], limit: int = MAX_TEXT_LENGTH) -> list[str]:
    """
    Join lines into texts within the Slack text limit
    """
    chunks: list[str] = []
    current = ""
    for line in lines:
        line = _truncate(line, limit)
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _context(text: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": _truncate(text)}]}


def _modal(blocks: list[dict]) -> dict:
    if len(blocks) > MAX_MODAL_BLOCKS:
        blocks = [*blocks[: MAX_MODAL_BLOCKS - 1], _context("_Some steps are not shown._")]
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "How Timur decided"},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": blocks,
    }


def build_notice_view(text: str) -> dict:
    return _modal([_section(text)])


def build_trace_view(trace: dict) -> dict:
    """
    Slack modal view of a trace
    """
    blocks: list[dict] = [{"type": "header", "text": {"type": "plain_text", "text": "How Timur read your message"}}]

    message_lines = []
    for message in trace.get("messages") or []:
        posted_at = datetime.datetime.fromisoformat(message["posted_at"])
        message_lines.append(f"*{posted_at.strftime('%a, %b %-d %H:%M')}*")
        message_lines.append(_quote(message.get("text") or ""))
    blocks.extend(_section(text) for text in _chunk_lines(message_lines or ["_No messages_"]))
    blocks.append({"type": "divider"})

    is_about_availability = trace.get("is_about_availability")
    blocks.append(
        _section(
            "*1. About your leave or WFH?* " + ("Yes" if is_about_availability else "No, so I left your journal as it was"),
        ),
    )

    if is_about_availability:
        understood = []
        for availability_range in trace.get("ranges") or []:
            phrase = availability_range.get("source_phrase")
            target = _date_range(availability_range["start_date"], availability_range["end_date"])
            line = f"• {_range_type_label(availability_range)} on {target}"
            if phrase:
                line = f'• "{plain_slack_text(phrase)}" → {line[2:]}'
            notes = [_correction_note(correction) for correction in availability_range.get("corrections") or []]
            if availability_range.get("note"):
                notes.append(availability_range["note"])
            if notes:
                line += f" ({'; '.join(notes)})"
            understood.append(line)
        for ignored in trace.get("ignored") or []:
            label = f"{_range_type_label(ignored)} on {_date_range(ignored['start_date'], ignored['end_date'])}"
            if ignored.get("source_phrase"):
                label = f'"{plain_slack_text(ignored["source_phrase"])}" → {label}'
            reason = IGNORED_REASON.get(ignored.get("reason"), "ignored")
            understood.append(f"• {label}: ignored, {reason}")
        understood.extend(_unclear_line(part) for part in trace.get("unclear") or [])
        if trace.get("needs_care"):
            understood.append("• A health or family situation is mentioned, so the reply starts with a care line")
        blocks.extend(
            _section(text) for text in _chunk_lines(["*2. Understood:*", *(understood or ["• Nothing to change"])])
        )

        working_days = []
        # Overlapping ranges list each date once
        listed_dates: set[str] = set()
        listed_skipped: set[tuple] = set()
        for availability_range in trace.get("ranges") or []:
            if availability_range.get("note") and not availability_range.get("dates"):
                continue
            all_dates = availability_range.get("dates") or []
            dates = [date for date in all_dates if date not in listed_dates]
            skipped_groups = [
                group
                for group in availability_range.get("skipped") or []
                if (group["start_date"], group["end_date"], group["reason"]) not in listed_skipped
            ]
            if all_dates and not dates and not skipped_groups:
                continue
            listed_dates.update(dates)
            listed_skipped.update((group["start_date"], group["end_date"], group["reason"]) for group in skipped_groups)
            line = "• " + (", ".join(_date(date) for date in dates) if dates else "no working days")
            skipped = [
                f"{_date_range(group['start_date'], group['end_date'])}: {group['reason']}" for group in skipped_groups
            ]
            if skipped:
                line += f" (skipped {'; '.join(skipped)})"
            working_days.append(line)
        if working_days:
            blocks.extend(_section(text) for text in _chunk_lines(["*3. Working days:*", *working_days]))

    if trace.get("low_confidence"):
        blocks.append(_section("*4. Journal:* I wasn't sure enough about this message, so I left your journal as it was"))
    elif trace.get("dates") is not None:
        journal_lines = [line for item in trace["dates"] if (line := _date_line(item))]
        blocks.extend(_section(text) for text in _chunk_lines(["*4. Journal:*", *(journal_lines or ["• No changes"])]))

    confidence = trace.get("confidence")
    details = [f"Model: {escape(trace.get('model') or 'unknown')}"]
    if isinstance(confidence, int | float):
        details.append(f"confidence {confidence:.2f}")
    blocks.append(_context(" · ".join(details)))
    return _modal(blocks)


def has_viewable_trace(trace: typing.Any) -> bool:
    return isinstance(trace, dict) and not trace.get("purged")
