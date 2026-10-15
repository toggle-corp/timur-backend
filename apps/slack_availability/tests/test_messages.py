import datetime

from apps.journal.models import Journal
from apps.slack_availability.messages import (
    MAX_SECTION_TEXT_LENGTH,
    WHY_ACTION_ID,
    StandupNote,
    StandupRole,
    build_reply,
    build_reply_blocks,
)
from apps.slack_availability.reconcile import ChangeAction, PlannedChange
from apps.slack_availability.structs import EMPTY_DAY_STATE, DayState, MissingDetail, UnclearPart
from utils import frontend_urls


def link(date: datetime.date, label: str) -> str:
    return f"<{frontend_urls.daily_journal(date)}|{label}>"


LT = Journal.LeaveType
WT = Journal.WorkFromHomeType

THU = datetime.date(2026, 10, 15)
FRI = datetime.date(2026, 10, 16)
MON = datetime.date(2026, 10, 19)
TUE = datetime.date(2026, 10, 20)
WED = datetime.date(2026, 10, 21)

DISCLAIMER = "> _LLM-interpreted (test-model). Please double-check._"


def test_build_reply():
    text = build_reply(
        slack_user_id="U123",
        changes=[
            PlannedChange(THU, ChangeAction.ADD, before=EMPTY_DAY_STATE, after=DayState(leave_type=LT.FULL)),
            PlannedChange(
                FRI,
                ChangeAction.UPDATE,
                before=DayState(leave_type=LT.FULL),
                after=DayState(leave_type=LT.FIRST_HALF, wfh_type=WT.SECOND_HALF),
            ),
            PlannedChange(MON, ChangeAction.REMOVE, before=DayState(leave_type=LT.FULL), after=EMPTY_DAY_STATE),
            PlannedChange(WED, ChangeAction.SKIP, before=DayState(wfh_type=WT.FULL), after=DayState(leave_type=LT.FULL)),
            # Manual values that match are thanked together with skipped ones, sorted by date
            PlannedChange(TUE, ChangeAction.MATCH, before=DayState(wfh_type=WT.FULL), after=DayState(wfh_type=WT.FULL)),
            # Bookkeeping actions are not shown
            PlannedChange(TUE, ChangeAction.CLAIM, before=EMPTY_DAY_STATE, after=EMPTY_DAY_STATE),
        ],
        unknown_half_dates=[THU, FRI],
        unclear=[UnclearPart("leave <next week>")],
        standup_notes=[
            StandupNote(THU, StandupRole.CONDUCTOR, other_slack_user_id="U456"),
            StandupNote(FRI, StandupRole.FALLBACK_CONDUCTOR, other_slack_user_id="U789"),
        ],
        llm_model="test-model",
    )
    assert text == "\n".join(
        [
            "<@U123> I've updated your Timur journal:",
            f"• {link(THU, 'Thu, Oct 15')}: Leave (full)",
            f"• {link(FRI, 'Fri, Oct 16')}: Leave (first half) + WFH (second half)",
            "Removed from your Timur journal:",
            f"• {link(MON, 'Mon, Oct 19')}",
            f"Thanks for already updating {link(TUE, 'Tue, Oct 20')} and {link(WED, 'Wed, Oct 21')}"
            " in your journal, I left it as is.",
            "Heads up: you're conducting standup on Thu, Oct 15, <@U456> will take over.",
            "Heads up: you're the backup standup conductor on Fri, Oct 16.",
            "Which half on Thu, Oct 15 and Fri, Oct 16: first or second? Reply here and I'll update it.",
            "I couldn't work out \"leave &lt;next week&gt;\". Reply here with the dates and whether it's leave or WFH,"
            " and I'll update it.",
            "",
            DISCLAIMER,
        ],
    )


def test_build_reply_only_removed():
    text = build_reply(
        slack_user_id="U123",
        changes=[
            PlannedChange(MON, ChangeAction.REMOVE, before=DayState(leave_type=LT.FULL), after=EMPTY_DAY_STATE),
        ],
        unknown_half_dates=[],
        unclear=[],
        standup_notes=[],
        llm_model="test-model",
    )
    assert text == "\n".join(
        [
            "<@U123> Removed from your Timur journal:",
            f"• {link(MON, 'Mon, Oct 19')}",
            "",
            DISCLAIMER,
        ],
    )


def test_build_reply_nothing_to_say():
    assert (
        build_reply(
            slack_user_id="U123",
            changes=[PlannedChange(TUE, ChangeAction.DROP, before=EMPTY_DAY_STATE, after=EMPTY_DAY_STATE)],
            unknown_half_dates=[],
            unclear=[],
            standup_notes=[],
            llm_model="test-model",
        )
        is None
    )


def test_build_reply_question_only():
    text = build_reply(
        slack_user_id="U123",
        changes=[],
        unknown_half_dates=[THU],
        unclear=[],
        standup_notes=[],
        llm_model="qwen3:8b",
    )
    assert text == "\n".join(
        [
            "<@U123> Which half on Thu, Oct 15: first or second? Reply here and I'll update it.",
            "",
            "> _LLM-interpreted (qwen3:8b). Please double-check._",
        ],
    )


def test_build_reply_unclear_questions():
    text = build_reply(
        slack_user_id="U123",
        changes=[PlannedChange(MON, ChangeAction.ADD, before=EMPTY_DAY_STATE, after=DayState(leave_type=LT.FULL))],
        unknown_half_dates=[],
        unclear=[
            UnclearPart("on leave till further notice", MissingDetail.END_DATE),
            UnclearPart("off until I recover", MissingDetail.END_DATE),
            UnclearPart("a few days later this month", MissingDetail.DATES),
            UnclearPart("won't be at the office tomorrow", MissingDetail.TYPE),
        ],
        standup_notes=[],
        llm_model="test-model",
        needs_care=True,
    )
    assert text == "\n".join(
        [
            "<@U123> Sorry to hear that, take care.",
            "I've updated your Timur journal:",
            f"• {link(MON, 'Mon, Oct 19')}: Leave (full)",
            # One question per missing end date
            "No rush, reply here when you know how long you'll be out and I'll update the remaining days.",
            "I couldn't work out the dates for \"a few days later this month\". Reply here with them and I'll update it.",
            "Is \"won't be at the office tomorrow\" leave or WFH? Reply here and I'll update it.",
            "",
            DISCLAIMER,
        ],
    )


def test_build_reply_care_needs_a_reply():
    assert (
        build_reply(
            slack_user_id="U123",
            changes=[],
            unknown_half_dates=[],
            unclear=[],
            standup_notes=[],
            llm_model="test-model",
            needs_care=True,
        )
        is None
    )


def test_build_reply_blocks():
    assert build_reply_blocks("<@U123> line 1\n\n> _quote_", 42) == [
        {"type": "section", "text": {"type": "mrkdwn", "text": "<@U123> line 1\n\n> _quote_"}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "How did Timur decide?"},
                    "action_id": WHY_ACTION_ID,
                    "value": "42",
                },
            ],
        },
    ]


def test_build_reply_blocks_long_text():
    lines = [f"• line {x} " + "x" * 100 for x in range(100)]
    text = "\n".join([*lines, "y" * (MAX_SECTION_TEXT_LENGTH + 10)])
    blocks = build_reply_blocks(text, 1)
    sections = [block["text"]["text"] for block in blocks if block["type"] == "section"]
    assert len(sections) > 1
    assert all(len(section) <= MAX_SECTION_TEXT_LENGTH for section in sections)
    assert "".join(sections).replace("\n", "") == text.replace("\n", "")
