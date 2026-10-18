import dataclasses
import datetime
import enum

from utils import frontend_urls

from .reconcile import MANUAL_VALUE_ACTIONS, ChangeAction, PlannedChange
from .structs import MissingDetail, UnclearPart


class StandupRole(enum.StrEnum):
    CONDUCTOR = "conductor"
    FALLBACK_CONDUCTOR = "fallback_conductor"


@dataclasses.dataclass(frozen=True)
class StandupNote:
    date: datetime.date
    role: StandupRole
    other_slack_user_id: str | None
    """Slack user id of the other conductor"""


def format_date(date: datetime.date) -> str:
    return date.strftime("%a, %b %-d")


def format_journal_date(date: datetime.date) -> str:
    """
    Date label linked to the user's journal for that date
    """
    return f"<{frontend_urls.daily_journal(date)}|{format_date(date)}>"


def _join_labels(labels: list[str]) -> str:
    if len(labels) <= 1:
        return "".join(labels)
    return f"{', '.join(labels[:-1])} and {labels[-1]}"


def format_dates(dates: list[datetime.date]) -> str:
    return _join_labels([format_date(date) for date in dates])


def format_journal_dates(dates: list[datetime.date]) -> str:
    return _join_labels([format_journal_date(date) for date in sorted(dates)])


def escape(text: str) -> str:
    """
    https://docs.slack.dev/messaging/formatting-message-text/#escaping
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _standup_line(note: StandupNote) -> str:
    date = format_date(note.date)
    if note.role == StandupRole.CONDUCTOR:
        if note.other_slack_user_id:
            return f"Heads up: you're conducting standup on {date}, <@{note.other_slack_user_id}> will take over."
        return f"Heads up: you're conducting standup on {date}."
    return f"Heads up: you're the backup standup conductor on {date}."


# Added by code, never written by the LLM
CARE_LINE = "Sorry to hear that, take care."


def _unclear_question(part: UnclearPart) -> str:
    phrase = escape(part.phrase)
    if part.missing == MissingDetail.END_DATE:
        return "No rush, reply here when you know how long you'll be out and I'll update the remaining days."
    if part.missing == MissingDetail.DATES:
        return f"I couldn't work out the dates for \"{phrase}\". Reply here with them and I'll update it."
    if part.missing == MissingDetail.TYPE:
        return f'Is "{phrase}" leave or WFH? Reply here and I\'ll update it.'
    return f"I couldn't work out \"{phrase}\". Reply here with the dates and whether it's leave or WFH, and I'll update it."


def build_reply(
    *,
    slack_user_id: str,
    changes: list[PlannedChange],
    unknown_half_dates: list[datetime.date],
    unclear: list[UnclearPart],
    standup_notes: list[StandupNote],
    llm_model: str,
    needs_care: bool = False,
) -> str | None:
    """
    Thread reply text, or None when there is nothing to tell the user
    """
    updated = [change for change in changes if change.action in (ChangeAction.ADD, ChangeAction.UPDATE)]
    removed = [change for change in changes if change.action == ChangeAction.REMOVE]
    already_set = [change for change in changes if change.action in MANUAL_VALUE_ACTIONS]

    sections: list[str] = []
    if updated:
        sections.append(
            "\n".join(
                [
                    "I've updated your Timur journal:",
                    *(f"• {format_journal_date(change.date)}: {change.after.label}" for change in updated),
                ],
            ),
        )
    if removed:
        sections.append(
            "\n".join(
                [
                    "Removed from your Timur journal:",
                    *(f"• {format_journal_date(change.date)}" for change in removed),
                ],
            ),
        )
    if already_set:
        sections.append(
            f"Thanks for already updating {format_journal_dates([change.date for change in already_set])}"
            " in your journal, I left it as is.",
        )
    sections.extend(_standup_line(note) for note in standup_notes)
    if unknown_half_dates:
        sections.append(
            f"Which half on {format_dates(unknown_half_dates)}: first or second? Reply here and I'll update it.",
        )
    sections.extend(dict.fromkeys(_unclear_question(part) for part in unclear))

    if not sections:
        return None
    if needs_care:
        sections.insert(0, CARE_LINE)

    disclaimer = f"> _LLM-interpreted ({escape(llm_model)}). Please double-check._"
    return f"<@{slack_user_id}> " + "\n".join(sections) + f"\n\n{disclaimer}"


def build_delete_notice(slack_user_id: str, channel_id: str, *, parent_deleted: bool) -> str:
    """
    Thread reply when the poster deletes a message of a thread that changed their journal

    A thread whose top-level message is deleted is no longer read. A new thread can set its dates, but only
    removes dates it wrote itself, so cancelling them is done in Timur.
    A thread with a deleted reply is read again on its next event, without that reply.
    """
    if parent_deleted:
        return (
            f"<@{slack_user_id}> I don't handle deleted messages, so your Timur journal wasn't changed."
            f" I no longer read this thread. To change it, post a new message in <#{channel_id}>."
            " To cancel, update it in Timur."
        )
    return (
        f"<@{slack_user_id}> I don't handle deleted messages, so your Timur journal wasn't changed now."
        " I'll leave that message out the next time I read this thread. To change or cancel, reply in this thread."
    )


WHY_ACTION_ID = "slack_availability_why"
# https://docs.slack.dev/reference/block-kit/blocks/section-block/
MAX_SECTION_TEXT_LENGTH = 3000


def _split_text(text: str, limit: int = MAX_SECTION_TEXT_LENGTH) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def build_reply_blocks(text: str, run_id: int) -> list[dict]:
    """
    Reply text with a button that shows how Timur read the thread (see trace.py)
    """
    return [
        *({"type": "section", "text": {"type": "mrkdwn", "text": chunk}} for chunk in _split_text(text)),
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "How did Timur decide?"},
                    "action_id": WHY_ACTION_ID,
                    "value": str(run_id),
                },
            ],
        },
    ]
