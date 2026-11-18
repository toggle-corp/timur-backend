"""
Journal history of the dates of a run, as shown to the poster in Slack
"""

import datetime
import itertools

from django.utils import timezone

from apps.journal.models import JournalAvailabilityHistory
from utils.slack import TimurSlack

from .links import run_permalink, workspace_url
from .messages import format_date
from .models import SlackAvailabilityRun
from .structs import DayState

# Bounds the modal for runs over long ranges
MAX_HISTORY_DATES = 15
HISTORY_ROWS_PER_DATE = 3

Source = JournalAvailabilityHistory.Source


# Changes made by a person, and where they made them
HAND_SOURCES = {
    Source.MANUAL: "Timur",
    Source.ADMIN: "Timur admin",
}


def changed_by_label(row: JournalAvailabilityHistory, run: SlackAvailabilityRun) -> str:
    if row.changed_by_id is not None and row.changed_by_id == run.thread.user_id:
        return "you"
    return row.changed_by.display_name if row.changed_by else "someone"


def format_datetime(value: datetime.datetime) -> str:
    return timezone.localtime(value).strftime("%a, %b %-d %H:%M")


def run_dates(run: SlackAvailabilityRun) -> list[datetime.date]:
    """
    Dates the run planned a change for, or left as they were
    """
    planned_changes = run.planned_changes or {}
    dates = {
        datetime.date.fromisoformat(item["date"])
        for item in [*(planned_changes.get("changes") or []), *(planned_changes.get("kept") or [])]
    }
    return sorted(dates)[:MAX_HISTORY_DATES]


def describe_history_row(row: JournalAvailabilityHistory, run: SlackAvailabilityRun, base_url: str | None) -> str:
    """
    What changed, who or what changed it, and when
    """
    before = DayState(row.leave_type_before, row.wfh_type_before).label
    after = DayState(row.leave_type_after, row.wfh_type_after).label
    change = f"{before} → {after}"
    at = format_datetime(row.created_at)
    if row.source in HAND_SOURCES:
        return f"{change}, by {changed_by_label(row, run)} in {HAND_SOURCES[row.source]}, {at}"

    source_run = row.slack_availability_run
    if source_run is None:
        return f"{change}, by Timur from a Slack thread, {at}"
    label = "this thread" if source_run.thread_id == run.thread_id else "another thread"
    if base_url:
        label = f"<{run_permalink(base_url, source_run)}|{label}>"
    return f"{change}, by Timur from {label}, {at}"


def history_lines(run: SlackAvailabilityRun, slack: TimurSlack) -> list[str]:
    """
    Latest journal changes of the run's dates, newest first per date
    """
    user_id = run.thread.user_id
    dates = run_dates(run)
    if user_id is None or not dates:
        return []
    rows = list(
        JournalAvailabilityHistory.objects.filter(journal__user_id=user_id, journal__date__in=dates)
        .select_related("journal", "changed_by", "slack_availability_run__thread")
        .order_by("journal__date", "-created_at", "-id"),
    )
    base_url = workspace_url(slack) if any(row.slack_availability_run_id for row in rows) else None
    lines = []
    for date, date_rows in itertools.groupby(rows, key=lambda row: row.journal.date):
        lines.extend(
            f"• {format_date(date)}: {describe_history_row(row, run, base_url)}"
            for row in list(date_rows)[:HISTORY_ROWS_PER_DATE]
        )
    return lines
