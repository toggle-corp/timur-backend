"""
Deterministic checks on the parser's ranges, applied before the ranges are expanded into journal dates

Each check works on the source phrase of a range and the sentences around it in the thread:
- conditional: plans stated with a condition or uncertainty ("if", "might") are dropped
- early departure: leaving early or at a time, with no leave or WFH words, is dropped
- weekday: dates of a phrase that names weekdays (and no other date) are resolved from the posting date
- confirmation: a later message that only restates the same type keeps the half an earlier message gave, whether
  the parser returned the earlier range or only the final state

The parser output stays as returned (ParseResult.raw); these checks only change what the run uses.
"""

import dataclasses
import datetime
import enum
import re

from .structs import AvailabilityRange, Half, ThreadMessage


class GuardKind(enum.StrEnum):
    CONDITIONAL = "conditional"
    EARLY_DEPARTURE = "early_departure"
    WEEKDAY = "weekday"
    CONFIRMATION = "confirmation"


@dataclasses.dataclass(frozen=True)
class IgnoredRange:
    availability_range: AvailabilityRange
    kind: GuardKind


@dataclasses.dataclass(frozen=True)
class Correction:
    index: int
    """Index of the corrected range in GuardResult.ranges"""
    before: AvailabilityRange
    kind: GuardKind


@dataclasses.dataclass
class GuardResult:
    ranges: list[AvailabilityRange]
    """Ranges to use, in parser order, corrections applied"""
    ignored: list[IgnoredRange]
    corrections: list[Correction]

    def corrections_for(self, index: int) -> list[Correction]:
        return [correction for correction in self.corrections if correction.index == index]


# -- Text helpers

_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTES)).strip().lower()


# A sentence ends at . ! ? or a line break
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*")


@dataclasses.dataclass(frozen=True)
class PhraseContext:
    sentences: list[str]
    """Normalized sentences of the message that the phrase overlaps (the phrase itself when not found)"""
    message_index: int | None
    """Index of the message containing the phrase"""
    posted_at: datetime.datetime | None


def locate_phrase(phrase: str, messages: list[ThreadMessage]) -> PhraseContext:
    needle = normalize(phrase)
    if needle:
        # Later messages first: a reply that repeats words of the original post is the one being quoted
        for index in reversed(range(len(messages))):
            message = messages[index]
            text = normalize(message.text)
            position = text.find(needle)
            if position < 0:
                continue
            end = position + len(needle)
            sentences = [
                match.group().strip()
                for match in _SENTENCE_RE.finditer(text)
                if match.start() < end and match.end() > position
            ]
            return PhraseContext(sentences=sentences or [needle], message_index=index, posted_at=message.posted_at)
    if len(messages) == 1 and needle:
        return PhraseContext(sentences=[needle], message_index=0, posted_at=messages[0].posted_at)
    return PhraseContext(sentences=[needle] if needle else [], message_index=None, posted_at=None)


# Words that make a sentence about leave/WFH. "leave" followed by an object or a time is leaving a place or a
# message ("leave a message", "leave at 4"), not a leave.
_AVAILABILITY_WORD_RE = re.compile(
    r"\b(?:"
    r"leave(?!\s+(?:a|an|the|it|them|me|you|your|my|this|that|now|early|earlier|at|by|office|work)\b)"
    r"|off|half|wfh|remote|remotely|from\s+home|sick|out\s+of\s+office|not\s+coming|day\s+off|bida|chh?utti|ghar"
    r")\b",
)

# Condition or uncertainty markers. "may" next to a day number is the month ("May 5", "5 May").
_CONDITIONAL_WORD_RE = re.compile(
    r"\b(?:if|might|maybe|probably|depending|in\s+case|unless|not\s+sure)\b"
    r"|(?<!\d\s)(?<!\d)\bmay\b(?!\s*\d)",
)
_LEADING_CONDITION_RE = re.compile(r"^(?:<[^>]*>\s*)*(?:and|but|so|also|then)?\s*(?:if|in\s+case|unless|depending)\b")
_CLAUSE_SPLIT_RE = re.compile(r"[,;:()]|\s(?:and|but|so|because|as|since|though|although)\s")


# Words of each type, to pick the clauses a range was read from
_LEAVE_WORD_RE = re.compile(
    r"\b(?:"
    r"leave(?!\s+(?:a|an|the|it|them|me|you|your|my|this|that|now|early|earlier|at|by|office|work)\b)"
    r"|off|sick|out\s+of\s+office|not\s+coming|bida|chh?utti"
    r")\b",
)
_WFH_WORD_RE = re.compile(r"\b(?:wfh|remote|remotely|from\s+home|ghar)\b")


def _clauses(sentence: str) -> tuple[bool, list[str]]:
    """
    Whether the sentence starts with a condition ("If X, I'll ..."), and its clauses
    """
    leading_condition = bool(_LEADING_CONDITION_RE.search(sentence))
    return leading_condition, [clause for clause in _CLAUSE_SPLIT_RE.split(sentence) if clause and clause.strip()]


def is_conditional_sentence(sentence: str) -> bool:
    """
    True when every leave/WFH clause of the sentence depends on a condition or is uncertain

    "If I don't feel better, I'll take the first half off" and "might WFH tomorrow" are conditional.
    "On leave tomorrow, if anything is urgent call me" is not: the condition is in another clause.
    """
    return is_conditional_text([sentence], _AVAILABILITY_WORD_RE)


def is_conditional_text(sentences: list[str], word_re: re.Pattern) -> bool:
    """
    True when the clauses matching word_re are all conditional, and there is at least one
    """
    matched = []
    for sentence in sentences:
        leading_condition, clauses = _clauses(sentence)
        matched.extend(
            leading_condition or bool(_CONDITIONAL_WORD_RE.search(clause)) for clause in clauses if word_re.search(clause)
        )
    return bool(matched) and all(matched)


def is_conditional(context: PhraseContext, availability_range: AvailabilityRange) -> bool:
    """
    True when the clauses the range was read from are all conditional

    Clauses with the range's own type (leave or WFH words) decide, so "WFH today, may take leave if needed" keeps
    the WFH. Without such clauses, any leave/WFH clause decides.
    """
    word_res = []
    if availability_range.leave:
        word_res.append(_LEAVE_WORD_RE)
    if availability_range.wfh:
        word_res.append(_WFH_WORD_RE)
    for word_re in word_res:
        if any(word_re.search(clause) for sentence in context.sentences for clause in _clauses(sentence)[1]):
            return is_conditional_text(context.sentences, word_re)
    return is_conditional_text(context.sentences, _AVAILABILITY_WORD_RE)


# Leaving the office early or at a time
_DEPARTURE_RE = re.compile(
    r"\b(?:"
    r"leav(?:e|ing)\s+(?:early|earlier|an?\s+hour\s+early|an?\s+hour\s+earlier|(?:at|by)\s+(?:about\s+|around\s+)?\d)"
    r"|left\s+(?:early|the\s+office)"
    r"|head(?:ing)?\s+out|step(?:ping)?\s+out"
    r")",
)
# End of the working day, a departure only when said after midday
_END_OF_DAY_RE = re.compile(r"\b(?:off\s+for\s+the\s+day|signing\s+off|logging\s+off|calling\s+it\s+a\s+day)\b")
# Words that make a departure a leave or WFH
_EXPLICIT_AVAILABILITY_RE = re.compile(
    r"\b(?:"
    r"on\s+leave|leave\s+(?:today|tomorrow|on|for|from)|take\s+(?:a\s+|the\s+)?(?:leave|day\s+off|half)"
    r"|(?:half|full)[\s-]?day|(?:1st|2nd|first|second)\s+half"
    r"|wfh|work(?:ing)?\s+(?:from\s+home|remotely)|remote|remotely|from\s+home|sick|day\s+off"
    r")\b",
)
MIDDAY_HOUR = 12


def is_early_departure(context: PhraseContext) -> bool:
    """
    True when the phrase only says the author leaves early or at a time ("leaving at 4:15", "heading out early")

    Departures that state a leave or WFH ("leaving at 3, will continue from home") are kept.
    """
    text = " ".join(context.sentences)
    if not text or _EXPLICIT_AVAILABILITY_RE.search(text):
        return False
    if _DEPARTURE_RE.search(text):
        return True
    return bool(
        _END_OF_DAY_RE.search(text) and context.posted_at is not None and context.posted_at.hour >= MIDDAY_HOUR,
    )


# -- Weekdays

_WEEKDAYS_FULL = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WEEKDAY_RE = re.compile(
    r"\b(?:(next|this|coming)\s+)?(" + "|".join(_WEEKDAYS_FULL) + r")\b",
)
_WEEKDAY_RANGE_RE = re.compile(
    r"\b("
    + "|".join(_WEEKDAYS_FULL)
    + r")\s*(?:to|till|until|through|thru|-|–)\s*(?:(?:next|this|coming)\s+)?("
    + "|".join(_WEEKDAYS_FULL)
    + r")\b",
)
_MONTHS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?"
    r"|nov(?:ember)?|dec(?:ember)?"
)
# Anything that dates the phrase without a weekday, or a week other than the coming one
_OTHER_DATE_RE = re.compile(
    r"\b(?:today|tonight|tomorrow|yesterday|day\s+after|aaja|aja|bholi|parsi"
    r"|next\s+week|following\s+week|week\s+after|last|previous)\b"
    rf"|\b(?:{_MONTHS})\s*\d|\b\d{{1,2}}\s*(?:st|nd|rd|th)?\s*(?:{_MONTHS})\b"
    r"|\b\d{1,2}(?:st|nd|rd|th)\b|\b\d{1,2}/\d{1,2}\b|\b\d{4}-\d{2}-\d{2}\b",
)


def _weekday_after(weekday: int, after: datetime.date, inclusive: bool = False) -> datetime.date:
    days = (weekday - after.weekday()) % 7
    if days == 0 and not inclusive:
        days = 7
    return after + datetime.timedelta(days=days)


@dataclasses.dataclass(frozen=True)
class WeekdayDates:
    named: list[int]
    """Weekdays named in the phrase, in order"""
    dates: dict[int, datetime.date]
    """Each named weekday resolved from the posting date"""
    span: tuple[int, int] | None
    """Start and end weekday of a "X to Y" range"""


def resolve_weekdays(text: str, posted_on: datetime.date) -> WeekdayDates | None:
    """
    Dates of the weekdays named in the text

    The first weekday is the first such date after the posting date ("this Friday" posted on a Friday is that day).
    Each following weekday is the first such date on or after the previous one. None when the text has no weekday
    or also dates itself another way ("tomorrow", "Oct 5", "next week").
    """
    if _OTHER_DATE_RE.search(text):
        return None
    named: list[int] = []
    qualifiers: dict[int, str | None] = {}
    for match in _WEEKDAY_RE.finditer(text):
        weekday = _WEEKDAYS_FULL.index(match.group(2))
        if weekday not in named:
            named.append(weekday)
            qualifiers[weekday] = match.group(1)
    if not named:
        return None

    dates: dict[int, datetime.date] = {}
    previous: datetime.date | None = None
    for weekday in named:
        if previous is None:
            same_day = qualifiers[weekday] == "this" and posted_on.weekday() == weekday
            previous = _weekday_after(weekday, posted_on, inclusive=same_day)
        else:
            previous = _weekday_after(weekday, previous, inclusive=True)
        dates[weekday] = previous

    span = None
    if match := _WEEKDAY_RANGE_RE.search(text):
        span = (_WEEKDAYS_FULL.index(match.group(1)), _WEEKDAYS_FULL.index(match.group(2)))
    return WeekdayDates(named=named, dates=dates, span=span)


def correct_weekdays(availability_range: AvailabilityRange, context: PhraseContext) -> AvailabilityRange | None:
    """
    The range with dates resolved from the weekdays its phrase names, or None when nothing changes

    Only corrects when the parser's dates fall on the named weekdays, so a range the parser built some other
    way is left alone.
    """
    if context.posted_at is None:
        return None
    phrase = normalize(availability_range.source_phrase)
    weekday_dates = resolve_weekdays(phrase, context.posted_at.date())
    if weekday_dates is None:
        return None

    start_date, end_date = availability_range.start_date, availability_range.end_date
    if weekday_dates.span is not None:
        first, last = weekday_dates.span
    else:
        first, last = weekday_dates.named[0], weekday_dates.named[-1]

    if start_date == end_date and start_date.weekday() in weekday_dates.dates:
        new_start = new_end = weekday_dates.dates[start_date.weekday()]
    elif start_date < end_date and start_date.weekday() == first and end_date.weekday() == last:
        new_start = weekday_dates.dates[first]
        new_end = _weekday_after(last, new_start, inclusive=True)
    else:
        return None

    if (new_start, new_end) == (start_date, end_date):
        return None
    return dataclasses.replace(availability_range, start_date=new_start, end_date=new_end)


# -- Confirmation replies

_FULL_DAY_RE = re.compile(r"\b(?:full|whole|all|entire)\s+day\b")
_HALF_MARKER_RE = re.compile(
    r"\b(?:half|morning|afternoon|after\s+lunch|rest\s+of\s+the\s+day|bihana|diuso|beluka)\b",
)


_FIRST_HALF_RE = re.compile(r"\b(?:first|1st)\s+half\b|\bmorning\b|\bbihana\b")
_SECOND_HALF_RE = re.compile(
    r"\b(?:second|2nd)\s+half\b|\bafternoon\b|\bafter\s+lunch\b|\brest\s+of\s+the\s+day\b|\bdiuso\b|\bbeluka\b",
)
_TODAY_RE = re.compile(r"\b(?:today|aaja|aja)\b")
_TOMORROW_RE = re.compile(r"\b(?:tomorrow|bholi)\b")
_TYPE_WORD_RE = {"leave": _LEAVE_WORD_RE, "wfh": _WFH_WORD_RE}


def _sentence_date(sentence: str, posted_on: datetime.date) -> datetime.date | None:
    """
    The day a sentence is about: the posting date, "tomorrow", or one named weekday; None when it dates itself
    another way
    """
    if _TOMORROW_RE.search(sentence):
        rest = _TOMORROW_RE.sub(" ", sentence)
        return None if _OTHER_DATE_RE.search(rest) or _WEEKDAY_RE.search(rest) else posted_on + datetime.timedelta(days=1)
    rest = _TODAY_RE.sub(" ", sentence)
    if weekday_dates := resolve_weekdays(rest, posted_on):
        return next(iter(weekday_dates.dates.values())) if len(weekday_dates.named) == 1 else None
    if _OTHER_DATE_RE.search(rest):
        return None
    return posted_on


def _sentence_half(sentence: str) -> Half | None:
    first, second = bool(_FIRST_HALF_RE.search(sentence)), bool(_SECOND_HALF_RE.search(sentence))
    if first == second:
        return None
    return Half.FIRST_HALF if first else Half.SECOND_HALF


def _half_from_earlier_messages(
    kind: str,
    date: datetime.date,
    messages: list[ThreadMessage],
    before_index: int,
) -> Half | None:
    """
    The half an earlier message of the thread gave for this type on this date (latest message first)
    """
    for message in reversed(messages[:before_index]):
        for sentence in (match.group().strip() for match in _SENTENCE_RE.finditer(normalize(message.text))):
            if not _TYPE_WORD_RE[kind].search(sentence) or is_conditional_sentence(sentence):
                continue
            half = _sentence_half(sentence)
            if half is not None and _sentence_date(sentence, message.posted_at.date()) == date:
                return half
    return None


def _single_type(availability_range: AvailabilityRange) -> tuple[str, Half] | None:
    """
    ("leave", half) or ("wfh", half) for a range that sets only one of them
    """
    if availability_range.leave and not availability_range.wfh:
        return "leave", availability_range.leave
    if availability_range.wfh and not availability_range.leave:
        return "wfh", availability_range.wfh
    return None


def keep_specific_half(
    availability_range: AvailabilityRange,
    context: PhraseContext,
    earlier: list[tuple[AvailabilityRange, PhraseContext]],
    messages: list[ThreadMessage] | None = None,
) -> AvailabilityRange | None:
    """
    The range with the half from an earlier message when it only confirms the same type for the same days

    "I'll work from home for the second half", then "done, working from home" stays WFH second half. The half
    comes from an earlier range of the same parse, or, when the parser returned only the final state, from an
    earlier message of the thread that gives a half for that type and day.
    """
    current = _single_type(availability_range)
    if current is None or current[1] != Half.FULL or context.message_index is None:
        return None
    text = " ".join(context.sentences)
    if _FULL_DAY_RE.search(text) or _HALF_MARKER_RE.search(text):
        return None
    for earlier_range, earlier_context in reversed(earlier):
        earlier_type = _single_type(earlier_range)
        if (
            earlier_type is None
            or earlier_type[0] != current[0]
            or earlier_type[1] not in (Half.FIRST_HALF, Half.SECOND_HALF)
            or earlier_context.message_index is None
            or earlier_context.message_index >= context.message_index
        ):
            continue
        if earlier_range.start_date <= availability_range.start_date and availability_range.end_date <= (
            earlier_range.end_date
        ):
            return _with_half(availability_range, current[0], earlier_type[1])
    if messages and context.message_index > 0 and availability_range.start_date == availability_range.end_date:
        half = _half_from_earlier_messages(current[0], availability_range.start_date, messages, context.message_index)
        if half is not None:
            return _with_half(availability_range, current[0], half)
    return None


def _with_half(availability_range: AvailabilityRange, kind: str, half: Half) -> AvailabilityRange:
    if kind == "leave":
        return dataclasses.replace(availability_range, leave=half)
    return dataclasses.replace(availability_range, wfh=half)


def apply_guards(ranges: list[AvailabilityRange], messages: list[ThreadMessage]) -> GuardResult:
    result = GuardResult(ranges=[], ignored=[], corrections=[])
    kept: list[tuple[AvailabilityRange, PhraseContext]] = []
    for availability_range in ranges:
        # Ranges that set nothing have nothing to check
        if not availability_range.has_unknown_half and availability_range.as_day_state().is_empty:
            result.ranges.append(availability_range)
            continue
        context = locate_phrase(availability_range.source_phrase, messages)

        if is_conditional(context, availability_range):
            result.ignored.append(IgnoredRange(availability_range, GuardKind.CONDITIONAL))
            continue
        if is_early_departure(context):
            result.ignored.append(IgnoredRange(availability_range, GuardKind.EARLY_DEPARTURE))
            continue

        index = len(result.ranges)
        corrected = availability_range
        if weekday_range := correct_weekdays(corrected, context):
            result.corrections.append(Correction(index, corrected, GuardKind.WEEKDAY))
            corrected = weekday_range
        if half_range := keep_specific_half(corrected, context, kept, messages):
            result.corrections.append(Correction(index, corrected, GuardKind.CONFIRMATION))
            corrected = half_range

        result.ranges.append(corrected)
        kept.append((corrected, context))
    return result
