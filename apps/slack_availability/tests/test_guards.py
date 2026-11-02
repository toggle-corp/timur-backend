import datetime
import time

import pytest
from django.utils import timezone

from apps.slack_availability.guards import (
    GuardKind,
    WeekdayDates,
    apply_guards,
    is_conditional_sentence,
    locate_phrase,
    resolve_weekdays,
)
from apps.slack_availability.structs import AvailabilityRange, Half, ThreadMessage

# Thursday
THU = datetime.date(2026, 10, 1)
FRI = THU + datetime.timedelta(days=1)
MON = THU + datetime.timedelta(days=4)
NEXT_MON = MON + datetime.timedelta(days=7)


def message(text: str, date: datetime.date = THU, hour: int = 10, index: int = 0) -> ThreadMessage:
    posted_at = datetime.datetime(date.year, date.month, date.day, hour, tzinfo=timezone.get_current_timezone())
    return ThreadMessage(ts=f"{posted_at.timestamp() + index:.6f}", posted_at=posted_at, text=text)


def leave(date: datetime.date, phrase: str, half: Half = Half.FULL, end: datetime.date | None = None):
    return AvailabilityRange(start_date=date, end_date=end or date, leave=half, source_phrase=phrase)


def wfh(date: datetime.date, phrase: str, half: Half = Half.FULL, end: datetime.date | None = None):
    return AvailabilityRange(start_date=date, end_date=end or date, wfh=half, source_phrase=phrase)


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("if i don't feel better by then, i'll take the first half off.", True),
        ("<!channel> if it takes a while, we'll be working remotely.", True),
        ("might wfh tomorrow if the plumber comes", True),
        ("i may take leave tomorrow", True),
        ("i'll probably wfh tomorrow", True),
        ("on leave tomorrow, if anything is urgent call me", False),
        ("on leave on may 5", False),
        ("on leave 5 may", False),
        ("i'm on leave today and might be slow to respond", False),
        ("wfh tomorrow", False),
    ],
)
def test_is_conditional_sentence(sentence, expected):
    assert is_conditional_sentence(sentence) is expected


def test_locate_phrase_sentences():
    messages = [
        message("I'm joining late. If I don't feel better by then, I’ll take the first half off. Will update."),
        message("Done, working from home", hour=14, index=1),
    ]
    context = locate_phrase("I'll take the first half off", messages)
    assert context.message_index == 0
    assert context.sentences == ["if i don't feel better by then, i'll take the first half off."]

    context = locate_phrase("working from home", messages)
    assert context.message_index == 1

    context = locate_phrase("not in any message", messages)
    assert context.message_index is None
    assert context.posted_at is None


def test_conditional_guard():
    messages = [
        message("Joining late, fever. If I don't feel better by then, I'll take the first half off. Will update."),
    ]
    ranges = [leave(THU, "If I don't feel better by then, I'll take the first half off.", Half.FIRST_HALF)]
    result = apply_guards(ranges, messages)
    assert result.ranges == []
    assert [(ignored.availability_range, ignored.kind) for ignored in result.ignored] == [
        (ranges[0], GuardKind.CONDITIONAL),
    ]

    # The condition is about something else
    messages = [message("On leave tomorrow, if anything is urgent call me")]
    ranges = [leave(FRI, "On leave tomorrow")]
    assert apply_guards(ranges, messages).ranges == ranges

    # Only the clauses of the range's own type decide
    text = "I'll be working from home today, but I may need to take leave if I'm not feeling well."
    messages = [message(text)]
    ranges = [wfh(THU, "I'll be working from home today"), leave(THU, "I may need to take leave")]
    result = apply_guards(ranges, messages)
    assert result.ranges == [ranges[0]]
    assert [ignored.availability_range for ignored in result.ignored] == [ranges[1]]
    messages = [message("I will be working from home, and may be on 2nd half leave if I need to go to hospital")]
    ranges = [wfh(THU, messages[0].text), leave(THU, messages[0].text, Half.SECOND_HALF)]
    result = apply_guards(ranges, messages)
    assert result.ranges == [ranges[0]]
    assert [ignored.availability_range for ignored in result.ignored] == [ranges[1]]

    # May the month
    messages = [message("On leave on May 5")]
    ranges = [leave(datetime.date(2027, 5, 5), "On leave on May 5")]
    assert apply_guards(ranges, messages).ranges == ranges


@pytest.mark.parametrize(
    ("text", "hour", "ignored"),
    [
        ("I will be leaving at about 4:15 today due to some urgent personal work.", 16, True),
        ("Heading out early today", 15, True),
        ("I'll be leaving an hour early today", 14, True),
        ("I'm off for the day. Please leave a message if anything.", 16, True),
        # Said in the morning, a day off
        ("I'm off for the day", 9, False),
        ("Leaving at 3, will continue from home", 14, False),
        ("Leaving early, taking second half leave", 12, False),
        ("Leaving early, feeling sick", 12, False),
    ],
)
def test_early_departure_guard(text, hour, ignored):
    messages = [message(text, hour=hour)]
    ranges = [wfh(THU, text, Half.SECOND_HALF)]
    result = apply_guards(ranges, messages)
    if ignored:
        assert result.ranges == []
        assert result.ignored[0].kind == GuardKind.EARLY_DEPARTURE
    else:
        assert result.ranges == ranges
        assert result.ignored == []


def weekday_dates(text: str, posted_on: datetime.date = THU) -> WeekdayDates:
    result = resolve_weekdays(text, posted_on)
    assert result is not None
    return result


def test_resolve_weekdays():
    # Posted Thursday
    assert weekday_dates("wfh on monday").dates == {0: MON}
    assert weekday_dates("next monday").dates == {0: MON}
    assert weekday_dates("leave on thursday").dates == {3: THU + datetime.timedelta(days=7)}
    assert weekday_dates("leave this thursday").dates == {3: THU}
    span_dates = weekday_dates("leave from friday to tuesday")
    assert span_dates.dates == {4: FRI, 1: MON + datetime.timedelta(days=1)}
    assert span_dates.span == (4, 1)
    # Each extra "next" is one more week
    assert weekday_dates("leave next next monday").dates == {0: NEXT_MON}
    assert weekday_dates("leave next next next monday").dates == {0: NEXT_MON + datetime.timedelta(days=7)}
    assert weekday_dates("leave next next thursday").dates == {3: THU + datetime.timedelta(days=14)}
    assert weekday_dates("leave from next next monday to wednesday").dates == {
        0: NEXT_MON,
        2: NEXT_MON + datetime.timedelta(days=2),
    }
    # "next to next" is "next next"
    assert weekday_dates("leave next to next monday").dates == {0: NEXT_MON}
    assert weekday_dates("leave next to next next monday").dates == {0: NEXT_MON + datetime.timedelta(days=7)}
    # Dated another way
    assert resolve_weekdays("leave tomorrow (friday)", THU) is None
    assert resolve_weekdays("leave on monday oct 12", THU) is None
    assert resolve_weekdays("leave next week monday", THU) is None
    assert resolve_weekdays("leave on the 12th, a monday", THU) is None
    assert resolve_weekdays("leave tomorrow", THU) is None


def test_weekday_guard():
    messages = [message("On leave tomorrow (Friday) and remotely working on Monday first half.", hour=16)]
    ranges = [
        leave(FRI, "on leave tomorrow (Friday)"),
        wfh(NEXT_MON, "remotely working on Monday first half", Half.FIRST_HALF),
    ]
    result = apply_guards(ranges, messages)
    assert result.ranges == [ranges[0], wfh(MON, "remotely working on Monday first half", Half.FIRST_HALF)]
    assert [(correction.index, correction.before, correction.kind) for correction in result.corrections] == [
        (1, ranges[1], GuardKind.WEEKDAY),
    ]

    # Range across the weekend, shifted by a week
    messages = [message("Leave from Friday to Tuesday")]
    ranges = [
        leave(FRI + datetime.timedelta(days=7), "Leave from Friday to Tuesday", end=NEXT_MON + datetime.timedelta(days=1)),
    ]
    result = apply_guards(ranges, messages)
    assert result.ranges == [leave(FRI, "Leave from Friday to Tuesday", end=MON + datetime.timedelta(days=1))]

    # Already right
    messages = [message("WFH on Monday")]
    ranges = [wfh(MON, "WFH on Monday")]
    result = apply_guards(ranges, messages)
    assert result.ranges == ranges
    assert result.corrections == []

    # Dates that don't fall on the named weekday are left alone
    ranges = [wfh(MON + datetime.timedelta(days=1), "WFH on Monday")]
    assert apply_guards(ranges, messages).ranges == ranges


def test_weekday_guard_single_weekday_keeps_end():
    fri = datetime.date(2026, 10, 30)
    mon, next_mon = datetime.date(2026, 11, 2), datetime.date(2026, 11, 9)

    # The end comes from elsewhere ("till Tihar") and happens to fall on the named weekday
    messages = [message("WFH from Monday till Tihar", date=fri)]
    ranges = [wfh(mon, "WFH from Monday till Tihar", end=next_mon)]
    result = apply_guards(ranges, messages)
    assert result.ranges == ranges
    assert result.corrections == []

    # A single day on the wrong week is still corrected
    messages = [message("Leave on Monday", date=fri)]
    ranges = [leave(next_mon, "Leave on Monday")]
    assert apply_guards(ranges, messages).ranges == [leave(mon, "Leave on Monday")]

    # Without an end word after the weekday, the range is that one day
    ranges = [leave(mon, "Leave on Monday", end=next_mon)]
    assert apply_guards(ranges, messages).ranges == [leave(mon, "Leave on Monday")]
    ranges = [leave(next_mon, "Leave on Monday", end=next_mon + datetime.timedelta(days=7))]
    assert apply_guards(ranges, messages).ranges == [leave(mon, "Leave on Monday")]


@pytest.mark.parametrize(
    ("phrase", "posted_on", "start", "end"),
    [
        # Working days across the weekend
        (
            "Leave from Thursday for 3 days",
            datetime.date(2026, 10, 12),
            datetime.date(2026, 10, 15),
            datetime.date(2026, 10, 19),
        ),
        # The end falls on the named weekday
        (
            "Leave from Monday for 6 days",
            datetime.date(2026, 10, 30),
            datetime.date(2026, 11, 2),
            datetime.date(2026, 11, 9),
        ),
        ("6 days leave from Monday", datetime.date(2026, 10, 30), datetime.date(2026, 11, 2), datetime.date(2026, 11, 9)),
        (
            "Off from Thursday for six days",
            datetime.date(2026, 10, 12),
            datetime.date(2026, 10, 15),
            datetime.date(2026, 10, 22),
        ),
    ],
)
def test_weekday_guard_single_weekday_with_day_count_keeps_end(phrase, posted_on, start, end):
    ranges = [leave(start, phrase, end=end)]
    result = apply_guards(ranges, [message(phrase, date=posted_on)])
    assert result.ranges == ranges
    assert result.corrections == []


def test_weekday_guard_next_next():
    wed = datetime.date(2026, 10, 14)
    next_mon, next_next_mon = datetime.date(2026, 10, 19), datetime.date(2026, 10, 26)

    messages = [message("WFH next Monday", date=wed)]
    ranges = [wfh(next_next_mon, "WFH next Monday")]
    assert apply_guards(ranges, messages).ranges == [wfh(next_mon, "WFH next Monday")]

    # Already right
    messages = [message("Leave on Next  next Monday", date=wed)]
    ranges = [leave(next_next_mon, "Leave on Next  next Monday")]
    result = apply_guards(ranges, messages)
    assert result.ranges == ranges
    assert result.corrections == []

    # A week early
    ranges = [leave(next_mon, "Leave on Next  next Monday")]
    assert apply_guards(ranges, messages).ranges == [leave(next_next_mon, "Leave on Next  next Monday")]


def test_weekday_guard_next_next_span():
    wed = datetime.date(2026, 10, 14)
    mon, next_next_fri = datetime.date(2026, 10, 19), datetime.date(2026, 10, 30)
    messages = [message("Leave from Monday to next next Friday", date=wed)]

    # Already right
    ranges = [leave(mon, "Leave from Monday to next next Friday", end=next_next_fri)]
    result = apply_guards(ranges, messages)
    assert result.ranges == ranges
    assert result.corrections == []

    # The end a week early
    ranges = [leave(mon, "Leave from Monday to next next Friday", end=datetime.date(2026, 10, 23))]
    assert apply_guards(ranges, messages).ranges == [
        leave(mon, "Leave from Monday to next next Friday", end=next_next_fri),
    ]


def test_weekday_guard_next_to_next():
    wed = datetime.date(2026, 10, 14)
    next_mon, next_next_mon = datetime.date(2026, 10, 19), datetime.date(2026, 10, 26)
    messages = [message("Leave next to next Monday", date=wed)]

    ranges = [leave(next_next_mon, "Leave next to next Monday")]
    result = apply_guards(ranges, messages)
    assert result.ranges == ranges
    assert result.corrections == []

    ranges = [leave(next_mon, "Leave next to next Monday")]
    assert apply_guards(ranges, messages).ranges == [leave(next_next_mon, "Leave next to next Monday")]


def test_resolve_weekdays_long_next_run_is_fast():
    for ending in ["monday", "month"]:
        start = time.perf_counter()
        resolve_weekdays("next " * 5000 + ending, THU)
        assert time.perf_counter() - start < 0.5


def test_confirmation_guard():
    messages = [
        message("Going to hospital. I'll work from home for the second half after I return.", hour=13),
        message("Done with my appointment and am working from home.", hour=14, index=1),
    ]
    ranges = [
        wfh(THU, "I'll work from home for the second half after I return.", Half.SECOND_HALF),
        wfh(THU, "Done with my appointment and am working from home."),
    ]
    result = apply_guards(ranges, messages)
    assert result.ranges == [ranges[0], wfh(THU, ranges[1].source_phrase, Half.SECOND_HALF)]
    assert [(correction.index, correction.kind) for correction in result.corrections] == [
        (1, GuardKind.CONFIRMATION),
    ]

    # A reply that says the whole day changes it
    messages[1] = message("Actually working from home the whole day.", hour=14, index=1)
    ranges[1] = wfh(THU, "Actually working from home the whole day.")
    assert apply_guards(ranges, messages).ranges == ranges

    # Different type
    messages[1] = message("Taking leave instead.", hour=14, index=1)
    ranges[1] = leave(THU, "Taking leave instead.")
    assert apply_guards(ranges, messages).ranges == ranges


def test_confirmation_guard_with_final_state_only():
    # The parser returns only the reply's range; the half comes from the earlier message
    messages = [
        message("Off to a checkup this morning. I'll work from home for the second half after I'm back.", hour=9),
        message("All done there, working from home now.", hour=13, index=1),
    ]
    ranges = [wfh(THU, "working from home now")]
    result = apply_guards(ranges, messages)
    assert result.ranges == [wfh(THU, "working from home now", Half.SECOND_HALF)]
    assert [(correction.index, correction.kind) for correction in result.corrections] == [
        (0, GuardKind.CONFIRMATION),
    ]

    # Leave and a weekday in the earlier message
    messages = [
        message("Taking leave on Friday morning for a family thing.", hour=9),
        message("Confirming the leave on Friday.", date=THU, hour=15, index=1),
    ]
    assert apply_guards([leave(FRI, "Confirming the leave on Friday")], messages).ranges == [
        leave(FRI, "Confirming the leave on Friday", Half.FIRST_HALF),
    ]


@pytest.mark.parametrize(
    ("earlier", "reply", "date"),
    [
        # The reply says the whole day
        ("WFH for the second half today.", "Working from home the whole day after all.", THU),
        # The earlier half is for another day
        ("WFH tomorrow afternoon.", "Working from home now.", THU),
        # The earlier half is for the other type
        ("Leave for the second half today.", "Working from home now.", THU),
        # The earlier half was conditional
        ("If the plumber is late, I'll WFH in the afternoon.", "Working from home now.", THU),
        # Both halves named earlier
        ("WFH in the morning and leave after lunch.", "Working from home today.", THU),
    ],
)
def test_confirmation_guard_with_final_state_only_leaves_full(earlier, reply, date):
    messages = [message(earlier, hour=9), message(reply, hour=13, index=1)]
    ranges = [wfh(date, reply)]
    assert apply_guards(ranges, messages).ranges == ranges


@pytest.mark.parametrize(
    ("earlier", "reply", "make"),
    [
        ("First half leave today", "Still not better, taking leave for today too", leave),
        ("WFH in the morning", "Will WFH the rest of today also", wfh),
        ("WFH in the morning", "Working from home in the afternoon as well", wfh),
    ],
)
def test_confirmation_guard_reply_adding_the_other_half(earlier, reply, make):
    messages = [message(earlier, hour=9), message(reply, hour=13, index=1)]
    half = Half.FIRST_HALF

    # The parser returns only the final state
    ranges = [make(THU, reply)]
    result = apply_guards(ranges, messages)
    assert result.ranges == ranges
    assert result.corrections == []

    # The parser returns the earlier half and the reply
    ranges = [make(THU, earlier, half), make(THU, reply)]
    result = apply_guards(ranges, messages)
    assert result.ranges == ranges
    assert result.corrections == []


def test_confirmation_guard_needs_a_reply():
    # A single message has no earlier message to take a half from
    messages = [message("Working from home in the afternoon. Working from home today.", hour=9)]
    ranges = [wfh(THU, "Working from home today.")]
    assert apply_guards(ranges, messages).ranges == ranges


def test_empty_and_unknown_phrases():
    # No phrase: nothing to check
    ranges = [leave(THU, "")]
    assert apply_guards(ranges, [message("whatever")]).ranges == ranges
    # Phrase not found in a multi-message thread: weekday is not corrected
    messages = [message("a"), message("b", hour=11, index=1)]
    ranges = [wfh(NEXT_MON, "WFH on Monday")]
    assert apply_guards(ranges, messages).ranges == ranges
