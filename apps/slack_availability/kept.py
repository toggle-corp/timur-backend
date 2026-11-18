"""
Days of a thread that Timur leaves as they are, because their value was set outside the thread

Stored on the run (planned_changes["kept"]) and told to the poster when they reply in the thread.
"""

import dataclasses
import datetime
import enum
import typing

from apps.journal.models import Journal, JournalAvailabilityHistory
from apps.user.models import User
from utils.slack import TimurSlack

from .history import format_datetime
from .links import thread_permalink, workspace_url
from .messages import KeptNoticeDay, build_kept_notice
from .models import SlackAvailabilityRun, SlackAvailabilityThread
from .reconcile import ChangeAction, PlannedChange, load_owned
from .structs import DayState

Status = SlackAvailabilityRun.Status

# Changes after which the thread holds a value of its own
THREAD_VALUE_ACTIONS = {ChangeAction.ADD.value, ChangeAction.UPDATE.value, ChangeAction.CLAIM.value}
# Planned changes that leave a value the thread doesn't own
KEPT_ACTIONS = {ChangeAction.DROP, ChangeAction.SKIP}


class KeptSource(enum.StrEnum):
    MANUAL = "manual"
    """Changed in Timur"""
    ADMIN = "admin"
    """Changed in the Timur admin"""
    THREAD = "thread"
    """Written by Timur from another thread"""
    UNKNOWN = "unknown"
    """No history that matches the value, e.g. a change before the history was recorded"""


KEPT_SOURCE_BY_HAND_SOURCE = {
    JournalAvailabilityHistory.Source.MANUAL: KeptSource.MANUAL,
    JournalAvailabilityHistory.Source.ADMIN: KeptSource.ADMIN,
}
# Where a person changed the value
HAND_SOURCE_PLACE = {
    KeptSource.MANUAL: "Timur",
    KeptSource.ADMIN: "Timur admin",
}


@dataclasses.dataclass(frozen=True)
class KeptDay:
    date: datetime.date
    state: DayState
    source: KeptSource
    changed_at: datetime.datetime | None = None
    changed_by_id: int | None = None
    thread_id: int | None = None

    def as_dict(self) -> dict[str, typing.Any]:
        return {
            "date": self.date.isoformat(),
            "state": self.state.as_dict(),
            "source": self.source.value,
            "changed_at": self.changed_at and self.changed_at.isoformat(),
            "changed_by_id": self.changed_by_id,
            "thread_id": self.thread_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, typing.Any]) -> typing.Self:
        return cls(
            date=datetime.date.fromisoformat(data["date"]),
            state=DayState(**data["state"]),
            source=KeptSource(data["source"]),
            changed_at=data.get("changed_at") and datetime.datetime.fromisoformat(data["changed_at"]),
            changed_by_id=data.get("changed_by_id"),
            thread_id=data.get("thread_id"),
        )


def _thread_dates(thread: SlackAvailabilityThread, today: datetime.date) -> set[datetime.date]:
    """
    Dates from today on that a live run of the thread wrote or took over
    """
    dates: set[datetime.date] = set()
    for planned_changes in thread.runs.filter(mode="live", status=Status.APPLIED).values_list(
        "planned_changes",
        flat=True,
    ):
        for change in (planned_changes or {}).get("changes") or []:
            date = datetime.date.fromisoformat(change["date"])
            if change["action"] in THREAD_VALUE_ACTIONS and date >= today:
                dates.add(date)
    return dates


def find_kept_days(
    user: User,
    thread: SlackAvailabilityThread,
    today: datetime.date,
    changes: list[PlannedChange],
    held_dates: set[datetime.date],
) -> list[KeptDay]:
    """
    Days of a thread with applied runs that hold a value the thread doesn't own

    These are the planned changes that leave a manual value (DROP, SKIP), and the dates the thread wrote before
    that now hold a value set manually or by another thread. Run before the changes are applied.
    """
    thread_dates = _thread_dates(thread, today)
    if not thread_dates:
        return []

    states = {change.date: change.before for change in changes if change.action in KEPT_ACTIONS}
    changed_dates = {change.date for change in changes}
    other_dates = thread_dates - changed_dates - held_dates
    journals = {
        journal.date: journal
        for journal in Journal.objects.filter(user=user, date__in=set(states) | other_dates).only(
            "id",
            "date",
            "leave_type",
            "wfh_type",
        )
    }
    owned = load_owned(user, set(journals))
    for date in other_dates:
        journal = journals.get(date)
        if journal is None:
            continue
        state = DayState.from_journal(journal)
        owned_state = owned.get(date)
        owned_by_thread = (
            owned_state is not None
            and owned_state.thread_id == thread.pk
            and owned_state.state == state
            and not owned_state.manually_changed
        )
        if not state.is_empty and not owned_by_thread:
            states[date] = state
    if not states:
        return []

    latest_history: dict[int, JournalAvailabilityHistory] = {}
    for row in (
        JournalAvailabilityHistory.objects.filter(journal__in=[journals[date] for date in states if date in journals])
        .select_related("slack_availability_run")
        .order_by("-created_at", "-id")
    ):
        latest_history.setdefault(row.journal_id, row)

    kept = []
    for date, state in sorted(states.items()):
        owned_state = owned.get(date)
        journal = journals.get(date)
        row = latest_history.get(journal.pk) if journal else None
        if (
            owned_state is not None
            and owned_state.thread_id != thread.pk
            and owned_state.state == state
            and not owned_state.manually_changed
        ):
            kept.append(KeptDay(date, state, KeptSource.THREAD, thread_id=owned_state.thread_id))
        elif row is None or DayState(row.leave_type_after, row.wfh_type_after) != state:
            kept.append(KeptDay(date, state, KeptSource.UNKNOWN))
        elif row.source in KEPT_SOURCE_BY_HAND_SOURCE:
            kept.append(
                KeptDay(
                    date,
                    state,
                    KEPT_SOURCE_BY_HAND_SOURCE[row.source],
                    changed_at=row.created_at,
                    changed_by_id=row.changed_by_id,
                ),
            )
        elif row.slack_availability_run is not None and row.slack_availability_run.thread_id != thread.pk:
            kept.append(
                KeptDay(
                    date,
                    state,
                    KeptSource.THREAD,
                    changed_at=row.created_at,
                    thread_id=row.slack_availability_run.thread_id,
                ),
            )
        else:
            kept.append(KeptDay(date, state, KeptSource.UNKNOWN))
    return kept


def render_kept_notice(run: SlackAvailabilityRun, slack: TimurSlack) -> str | None:
    """
    Notice for the poster about the kept days of the run, None when there are none
    """
    kept = [KeptDay.from_dict(item) for item in (run.planned_changes or {}).get("kept") or []]
    if not kept:
        return None
    user_names = dict(
        User.objects.filter(pk__in={day.changed_by_id for day in kept if day.changed_by_id}).values_list(
            "pk",
            "display_name",
        ),
    )
    threads = SlackAvailabilityThread.objects.in_bulk({day.thread_id for day in kept if day.thread_id})
    base_url = workspace_url(slack) if threads else None

    def source(day: KeptDay) -> str:
        if day.source in HAND_SOURCE_PLACE and day.changed_at is not None:
            if day.changed_by_id is not None and day.changed_by_id == run.thread.user_id:
                who = "you"
            else:
                who = user_names.get(day.changed_by_id or 0, "someone")
            return f"set by {who} in {HAND_SOURCE_PLACE[day.source]} at {format_datetime(day.changed_at)}"
        thread = threads.get(day.thread_id) if day.thread_id else None
        if day.source == KeptSource.THREAD:
            label = "another Slack thread"
            if thread is not None and base_url:
                label = f"<{thread_permalink(base_url, thread)}|{label}>"
            return f"set by {label}"
        return "I don't know who set it"

    return build_kept_notice([KeptNoticeDay(day.date, day.state, source(day)) for day in kept])
