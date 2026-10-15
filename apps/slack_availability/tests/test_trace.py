import datetime
import typing

from django.utils import timezone

from apps.common.factories import EventFactory
from apps.common.models import Event
from apps.journal.models import Journal
from apps.slack_availability.guards import apply_guards
from apps.slack_availability.reconcile import ChangeAction, PlannedChange
from apps.slack_availability.structs import (
    EMPTY_DAY_STATE,
    AvailabilityRange,
    DayState,
    Half,
    MissingDetail,
    ParseResult,
    ThreadMessage,
    UnclearPart,
)
from apps.slack_availability.trace import (
    MAX_MODAL_BLOCKS,
    MAX_TEXT_LENGTH,
    build_notice_view,
    build_trace,
    build_trace_view,
    describe_range,
    has_viewable_trace,
    plain_slack_text,
    purge_trace,
)
from apps.user.factories import UserFactory
from main.tests import TestCase

from . import next_monday

LT = Journal.LeaveType
WT = Journal.WorkFromHomeType


def days(date: datetime.date, count: int) -> datetime.date:
    return date + datetime.timedelta(days=count)


def local_dt(date: datetime.date, hour: int = 9) -> datetime.datetime:
    return datetime.datetime(date.year, date.month, date.day, hour, tzinfo=timezone.get_current_timezone())


def section_texts(view: dict) -> list[str]:
    texts = []
    for block in view["blocks"]:
        if block["type"] in ("section", "header"):
            texts.append(block["text"]["text"])
        elif block["type"] == "context":
            texts.extend(element["text"] for element in block["elements"])
    return texts


class TestTrace(TestCase):
    @classmethod
    @typing.override
    def setUpTestData(cls):
        user = UserFactory.create()
        cls.monday = next_monday()
        cls.wednesday = days(cls.monday, 2)
        EventFactory.create(
            name="Dashain",
            type=Event.Type.HOLIDAY,
            start_date=cls.wednesday,
            end_date=cls.wednesday,
            created_by=user,
            modified_by=user,
        )

    @typing.override
    def setUp(self):
        super().setUp()
        Event.reload_cache()

    def test_describe_range_skips(self):
        # Sat before the week, through Tue of the next week
        availability_range = AvailabilityRange(
            days(self.monday, -2),
            days(self.monday, 8),
            leave=Half.FULL,
            source_phrase="leave all next week",
        )
        described = describe_range(availability_range, today=self.monday)
        assert described["source_phrase"] == "leave all next week"
        assert described["leave"] == "full"
        assert described["wfh"] is None
        assert described["note"] is None
        assert described["dates"] == [
            date.isoformat()
            for date in [
                self.monday,
                days(self.monday, 1),
                days(self.monday, 3),
                days(self.monday, 4),
                days(self.monday, 7),
                days(self.monday, 8),
            ]
        ]
        assert described["skipped"] == [
            {
                "start_date": days(self.monday, -2).isoformat(),
                "end_date": days(self.monday, -1).isoformat(),
                "reason": "before the message date",
            },
            {"start_date": self.wednesday.isoformat(), "end_date": self.wednesday.isoformat(), "reason": "holiday: Dashain"},
            {
                "start_date": days(self.monday, 5).isoformat(),
                "end_date": days(self.monday, 6).isoformat(),
                "reason": "weekend",
            },
        ]

    def test_describe_range_too_far_and_notes(self):
        far = describe_range(
            AvailabilityRange(days(self.monday, 95), days(self.monday, 95), leave=Half.FULL),
            today=self.monday,
        )
        assert far["dates"] == []
        assert far["skipped"][0]["reason"] == "more than 90 days ahead"

        unknown = describe_range(
            AvailabilityRange(self.monday, self.monday, leave=Half.UNKNOWN),
            today=self.monday,
        )
        assert unknown["note"] == "which half is unknown, so I asked"

        invalid = describe_range(
            AvailabilityRange(self.monday, self.monday, leave=Half.FULL, wfh=Half.FULL),
            today=self.monday,
        )
        assert "not allowed" in invalid["note"]

    def build(self, with_changes: bool = True, low_confidence: bool = False) -> dict:
        parse_result = ParseResult(
            is_about_availability=True,
            ranges=[
                AvailabilityRange(self.monday, days(self.monday, 1), leave=Half.FULL, source_phrase="off Mon & Tue"),
                AvailabilityRange(
                    days(self.monday, 3),
                    days(self.monday, 3),
                    leave=Half.UNKNOWN,
                    source_phrase="half day Thu",
                ),
            ],
            unclear=[UnclearPart("sometime next month", MissingDetail.DATES)],
            confidence=0.92,
            raw={},
            model="qwen3:8b",
        )
        changes = [
            PlannedChange(self.monday, ChangeAction.ADD, before=EMPTY_DAY_STATE, after=DayState(leave_type=LT.FULL)),
            PlannedChange(
                days(self.monday, 1),
                ChangeAction.UPDATE,
                before=DayState(wfh_type=WT.FULL),
                after=DayState(leave_type=LT.FULL),
            ),
            PlannedChange(
                days(self.monday, 4),
                ChangeAction.REMOVE,
                before=DayState(leave_type=LT.FULL),
                after=EMPTY_DAY_STATE,
            ),
            PlannedChange(
                days(self.monday, 7),
                ChangeAction.SKIP,
                before=DayState(wfh_type=WT.FULL),
                after=DayState(leave_type=LT.FULL),
            ),
            PlannedChange(
                days(self.monday, 8),
                ChangeAction.MATCH,
                before=DayState(leave_type=LT.FULL),
                after=DayState(leave_type=LT.FULL),
            ),
            PlannedChange(
                days(self.monday, 9),
                ChangeAction.DROP,
                before=DayState(wfh_type=WT.FULL),
                after=DayState(wfh_type=WT.FULL),
            ),
        ]
        return build_trace(
            messages=[
                ThreadMessage(
                    ts="1.0",
                    posted_at=local_dt(days(self.monday, -3), 18),
                    text="off Mon & Tue, half day Thu",
                ),
            ],
            parse_result=parse_result,
            today=self.monday,
            changes=changes if with_changes else None,
            unknown_half_dates=[days(self.monday, 3)],
            unclear=[UnclearPart("sometime next month", MissingDetail.DATES)],
            low_confidence=low_confidence,
        )

    def test_build_trace(self):
        trace = self.build()
        assert trace["version"] == 1
        assert trace["today"] == self.monday.isoformat()
        assert trace["model"] == "qwen3:8b"
        assert trace["confidence"] == 0.92
        assert trace["is_about_availability"] is True
        assert trace["low_confidence"] is False
        assert trace["purged"] is False
        assert trace["messages"][0]["text"] == "off Mon & Tue, half day Thu"
        assert [availability_range["source_phrase"] for availability_range in trace["ranges"]] == [
            "off Mon & Tue",
            "half day Thu",
        ]
        assert trace["unclear"] == [{"phrase": "sometime next month", "missing": "dates"}]
        assert [item["action"] for item in trace["dates"]] == ["add", "update", "remove", "skip", "match", "drop", "held"]

    def test_build_trace_not_about_availability(self):
        parse_result = ParseResult(
            is_about_availability=False,
            ranges=[AvailabilityRange(self.monday, self.monday, leave=Half.FULL)],
            unclear=[],
            confidence=0.9,
            raw={},
            model="qwen3:8b",
        )
        trace = build_trace(
            messages=[],
            parse_result=parse_result,
            today=self.monday,
            changes=[],
            unknown_half_dates=[],
            unclear=[],
        )
        assert trace["ranges"] == []
        view_text = "\n".join(section_texts(build_trace_view(trace)))
        assert "About your leave or WFH?* No" in view_text
        assert "Understood" not in view_text

    def test_build_trace_needs_care(self):
        parse_result = ParseResult(
            is_about_availability=True,
            ranges=[],
            unclear=[UnclearPart("off until things settle", MissingDetail.END_DATE)],
            confidence=0.9,
            raw={},
            model="qwen3:8b",
            needs_care=True,
        )
        trace = build_trace(
            messages=[],
            parse_result=parse_result,
            today=self.monday,
            changes=[],
            unknown_half_dates=[],
            unclear=parse_result.unclear,
        )
        assert trace["needs_care"] is True
        view_text = "\n".join(section_texts(build_trace_view(trace)))
        assert '• "off until things settle" → no end date, so I asked' in view_text
        assert "so the reply starts with a care line" in view_text

        # Not about availability: no care line
        parse_result.is_about_availability = False
        trace = build_trace(
            messages=[],
            parse_result=parse_result,
            today=self.monday,
            changes=[],
            unknown_half_dates=[],
            unclear=[],
        )
        assert trace["needs_care"] is False

    def test_build_trace_view(self):
        view = build_trace_view(self.build())
        assert view["type"] == "modal"
        assert view["title"]["text"] == "How Timur decided"
        texts = section_texts(view)
        assert texts[0] == "How Timur read your message"
        text = "\n".join(texts)
        assert "> off Mon &amp; Tue, half day Thu" in text
        assert "*1. About your leave or WFH?* Yes" in text
        monday = self.monday.strftime("%a, %b %-d")
        tuesday = days(self.monday, 1).strftime("%a, %b %-d")
        assert f'• "off Mon &amp; Tue" → Leave (full) on {monday} to {tuesday}' in text
        assert "Leave (half day, which half unknown)" in text
        assert "which half is unknown, so I asked" in text
        assert '• "sometime next month" → dates unclear, so I asked' in text
        assert "*3. Working days:*" in text
        assert f"• {monday}: empty → set Leave (full)" in text
        assert f"• {tuesday}: WFH (full) → updated to Leave (full)" in text
        assert "→ removed" in text
        assert "you set WFH (full) → left as is (I read Leave (full))" in text
        assert "you already set Leave (full) → left as is" in text
        assert "you changed it to WFH (full) → left as is" in text
        assert "waiting for which half → left as is" in text
        assert "Model: qwen3:8b · confidence 0.92" in text

    def test_build_trace_view_low_confidence(self):
        trace = self.build(with_changes=False, low_confidence=True)
        text = "\n".join(section_texts(build_trace_view(trace)))
        assert "I wasn't sure enough" in text

    def test_build_trace_view_limits(self):
        trace = self.build()
        trace["messages"] = [{**trace["messages"][0], "text": "x" * 5000}] * 30
        trace["dates"] = trace["dates"] * 200
        view = build_trace_view(trace)
        assert len(view["blocks"]) <= MAX_MODAL_BLOCKS
        assert view["blocks"][-1]["type"] == "context"
        for text in section_texts(view):
            assert len(text) <= MAX_TEXT_LENGTH

    def test_purge_trace(self):
        trace = self.build()
        purged = purge_trace(trace)
        assert purged is not None
        assert purged["purged"] is True
        assert [message["text"] for message in purged["messages"]] == [""]
        assert [availability_range["source_phrase"] for availability_range in purged["ranges"]] == ["", ""]
        assert purged["unclear"] == []
        # Dates and types are kept
        assert purged["dates"] == trace["dates"]
        assert purged["ranges"][0]["dates"] == trace["ranges"][0]["dates"]
        assert not has_viewable_trace(purged)
        assert has_viewable_trace(trace)
        assert purge_trace(None) is None


class TestTraceGuards(TestCase):
    @typing.override
    def setUp(self):
        super().setUp()
        Event.reload_cache()
        self.monday = next_monday()
        self.thursday = days(self.monday, -4)

    def build(self) -> dict:
        messages = [
            ThreadMessage(
                ts="1.0",
                posted_at=local_dt(self.thursday, 16),
                text="<!channel> WFH on Monday first half. If the car takes long, I might take Tuesday off.",
            ),
        ]
        parse_result = ParseResult(
            is_about_availability=True,
            ranges=[
                AvailabilityRange(
                    days(self.monday, 7),
                    days(self.monday, 7),
                    wfh=Half.FIRST_HALF,
                    source_phrase="WFH on Monday first half",
                ),
                AvailabilityRange(
                    days(self.monday, 1),
                    days(self.monday, 1),
                    leave=Half.FULL,
                    source_phrase="If the car takes long, I might take Tuesday off.",
                ),
            ],
            unclear=[],
            confidence=0.9,
            raw={},
            model="qwen3:8b",
        )
        guard_result = apply_guards(parse_result.ranges, messages)
        return build_trace(
            messages=messages,
            parse_result=parse_result,
            today=self.thursday,
            changes=[],
            unknown_half_dates=[],
            unclear=[],
            guard_result=guard_result,
        )

    def test_build_trace_with_guards(self):
        trace = self.build()
        assert [(item["start_date"], item["wfh"]) for item in trace["ranges"]] == [
            (self.monday.isoformat(), "first_half"),
        ]
        assert trace["ranges"][0]["corrections"] == [
            {
                "kind": "weekday",
                "before": {
                    "source_phrase": "WFH on Monday first half",
                    "start_date": days(self.monday, 7).isoformat(),
                    "end_date": days(self.monday, 7).isoformat(),
                    "leave": None,
                    "wfh": "first_half",
                },
            },
        ]
        assert [(item["reason"], item["start_date"]) for item in trace["ignored"]] == [
            ("conditional", days(self.monday, 1).isoformat()),
        ]

        text = "\n".join(section_texts(build_trace_view(trace)))
        monday = self.monday.strftime("%a, %b %-d")
        next_week_monday = days(self.monday, 7).strftime("%a, %b %-d")
        tuesday = days(self.monday, 1).strftime("%a, %b %-d")
        assert "> @channel WFH on Monday first half." in text
        assert (
            f'• "WFH on Monday first half" → WFH (first half) on {monday} (weekday checked, I first read {next_week_monday})'
        ) in text
        assert (
            f'• "If the car takes long, I might take Tuesday off." → Leave (full) on {tuesday}: '
            "ignored, depends on a condition or is not certain"
        ) in text

    def test_purge_trace_with_guards(self):
        purged = purge_trace(self.build())
        assert purged is not None
        assert [item["source_phrase"] for item in purged["ignored"]] == [""]
        assert purged["ranges"][0]["corrections"][0]["before"]["source_phrase"] == ""
        assert purged["ignored"][0]["start_date"] == days(self.monday, 1).isoformat()

    def test_working_days_listed_once(self):
        parse_result = ParseResult(
            is_about_availability=True,
            ranges=[
                AvailabilityRange(self.monday, days(self.monday, 1), wfh=Half.SECOND_HALF),
                AvailabilityRange(self.monday, self.monday, leave=Half.FIRST_HALF),
            ],
            unclear=[],
            confidence=0.9,
            raw={},
        )
        trace = build_trace(
            messages=[],
            parse_result=parse_result,
            today=self.monday,
            changes=[],
            unknown_half_dates=[],
            unclear=[],
        )
        text = "\n".join(section_texts(build_trace_view(trace)))
        monday = self.monday.strftime("%a, %b %-d")
        assert text.count(monday) == 3  # Understood twice, working days once


def test_plain_slack_text():
    assert plain_slack_text("<!channel> hi <@U123> &amp; <#C1|general>") == "@channel hi <@U123> &amp; <#C1>"
    assert plain_slack_text("<!subteam^S1|@devs> see <https://x.test|this> or <https://y.test>") == (
        "@devs see this or https://y.test"
    )
    assert plain_slack_text("a < b &lt; c") == "a &lt; b &lt; c"
    assert plain_slack_text("1 &gt; 0 *bold*") == "1 &gt; 0 *bold*"


def test_build_notice_view():
    view = build_notice_view("Only the person who posted can view this.")
    assert view["blocks"] == [
        {"type": "section", "text": {"type": "mrkdwn", "text": "Only the person who posted can view this."}},
    ]
