import dataclasses
import datetime
import enum
import typing

from django.utils import timezone

from apps.journal.models import Journal
from apps.user.models import User

from .dates import MAX_DAYS_AHEAD
from .models import SlackAvailabilityJournalEntry, SlackAvailabilityThread
from .structs import EMPTY_DAY_STATE, DayState


class ReconcileConflictError(Exception):
    """
    The journal no longer matches the state the changes were planned from
    """


class ChangeAction(enum.StrEnum):
    ADD = "add"
    """Journal has no leave/WFH, set it"""
    UPDATE = "update"
    """Journal value is owned by Timur, replace it"""
    REMOVE = "remove"
    """Date is no longer in the thread, clear the value this thread wrote"""
    SKIP = "skip"
    """Journal has a manual value that differs, leave it"""
    MATCH = "match"
    """Journal has a manual value that already matches, leave it"""
    CLAIM = "claim"
    """Journal value already matches and is owned by another thread, take ownership"""
    DROP = "drop"
    """Value written by this thread was changed manually, forget ownership"""
    TRANSFER = "transfer"
    """Date is no longer in the thread but another thread still asks for the same value, hand ownership to it"""


JOURNAL_CHANGING_ACTIONS = {ChangeAction.ADD, ChangeAction.UPDATE, ChangeAction.REMOVE}
# Dates the user already set in the journal, which Timur leaves as is
MANUAL_VALUE_ACTIONS = {ChangeAction.SKIP, ChangeAction.MATCH}


@dataclasses.dataclass(frozen=True)
class PlannedChange:
    date: datetime.date
    action: ChangeAction
    before: DayState
    after: DayState
    owner_thread_id: int | None = None
    """Thread that owns the value after the change, when it is not the planning thread"""

    def as_dict(self) -> dict:
        data: dict[str, typing.Any] = {
            "date": self.date.isoformat(),
            "action": self.action.value,
            "before": self.before.as_dict(),
            "after": self.after.as_dict(),
        }
        if self.owner_thread_id is not None:
            data["owner_thread_id"] = self.owner_thread_id
        return data


@dataclasses.dataclass(frozen=True)
class OwnedState:
    """
    Values Timur last wrote for a date, and the thread that wrote them
    """

    thread_id: int
    state: DayState


@dataclasses.dataclass(frozen=True)
class RequestedState:
    """
    Values another live thread of the same user asks for on a date
    """

    thread_id: int
    state: DayState


def plan_changes(
    *,
    thread_id: int,
    today: datetime.date,
    desired: dict[datetime.date, DayState],
    current: dict[datetime.date, DayState],
    owned: dict[datetime.date, OwnedState],
    other_requests: dict[datetime.date, RequestedState] | None = None,
    held_dates: set[datetime.date] | None = None,
) -> list[PlannedChange]:
    """
    Compare the thread's desired state with the user's journal

    Timur only changes a date when the journal is empty or still holds the values Timur wrote.
    Dates before today are never touched.
    A date this thread owns but no longer asks for goes to another thread that still asks for it.
    Held dates (e.g. waiting for the user to say which half) keep their current value and ownership.
    """
    other_requests = other_requests or {}
    held_dates = held_dates or set()
    dates = set(desired.keys()) | {date for date, owned_state in owned.items() if owned_state.thread_id == thread_id}

    changes: list[PlannedChange] = []
    for date in sorted(dates):
        if date < today or date in held_dates:
            continue

        current_state = current.get(date, EMPTY_DAY_STATE)
        owned_state = owned.get(date)
        is_owned_by_timur = owned_state is not None and owned_state.state == current_state and not current_state.is_empty
        is_writable = current_state.is_empty or is_owned_by_timur

        desired_state = desired.get(date)
        if desired_state is None:
            # Owned by this thread but no longer in it
            if not is_owned_by_timur:
                changes.append(PlannedChange(date, ChangeAction.DROP, before=current_state, after=current_state))
                continue
            other_request = other_requests.get(date)
            if other_request is None:
                changes.append(PlannedChange(date, ChangeAction.REMOVE, before=current_state, after=EMPTY_DAY_STATE))
            elif other_request.state == current_state:
                changes.append(
                    PlannedChange(
                        date,
                        ChangeAction.TRANSFER,
                        before=current_state,
                        after=current_state,
                        owner_thread_id=other_request.thread_id,
                    ),
                )
            else:
                changes.append(
                    PlannedChange(
                        date,
                        ChangeAction.UPDATE,
                        before=current_state,
                        after=other_request.state,
                        owner_thread_id=other_request.thread_id,
                    ),
                )
            continue

        if desired_state == current_state:
            if is_owned_by_timur:
                if owned_state and owned_state.thread_id != thread_id:
                    changes.append(PlannedChange(date, ChangeAction.CLAIM, before=current_state, after=desired_state))
            elif not current_state.is_empty:
                changes.append(PlannedChange(date, ChangeAction.MATCH, before=current_state, after=desired_state))
            continue

        if is_writable:
            action = ChangeAction.ADD if current_state.is_empty else ChangeAction.UPDATE
        else:
            action = ChangeAction.SKIP
        changes.append(PlannedChange(date, action, before=current_state, after=desired_state))

    return changes


def load_journal_state(
    user: User,
    thread: SlackAvailabilityThread,
    dates: set[datetime.date],
) -> tuple[dict[datetime.date, DayState], dict[datetime.date, OwnedState]]:
    """
    Return the user's journal values and Timur's ownership for the given dates
    and for every date owned by the thread

    Locks the user's journal rows for these dates. Callers run this inside a transaction.
    """
    thread_dates = set(
        SlackAvailabilityJournalEntry.objects.filter(thread=thread).values_list("journal__date", flat=True),
    )
    all_dates = dates | thread_dates

    current = {
        journal.date: DayState.from_journal(journal)
        for journal in Journal.objects.select_for_update()
        .filter(user=user, date__in=all_dates)
        .order_by("date")
        .only("date", "leave_type", "wfh_type")
    }
    owned = {
        date: OwnedState(thread_id, DayState(leave_type, wfh_type))
        for date, thread_id, leave_type, wfh_type in SlackAvailabilityJournalEntry.objects.filter(
            journal__user=user,
            journal__date__in=all_dates,
        ).values_list("journal__date", "thread_id", "leave_type", "wfh_type")
    }
    return current, owned


def load_other_requests(
    user: User,
    thread: SlackAvailabilityThread,
    today: datetime.date,
) -> dict[datetime.date, RequestedState]:
    """
    Return what the user's other live threads ask for, from today onwards

    The most recently read thread wins when several ask for the same date.
    """
    # A thread only asks for dates up to MAX_DAYS_AHEAD after it was last read
    recent_cutoff = timezone.now() - datetime.timedelta(days=MAX_DAYS_AHEAD + 1)
    other_threads = (
        SlackAvailabilityThread.objects.filter(user=user, is_deleted=False, snapshot_at__gte=recent_cutoff)
        .exclude(pk=thread.pk)
        .order_by("snapshot_at")
        .only("id", "desired_state")
    )
    requests: dict[datetime.date, RequestedState] = {}
    for other_thread in other_threads:
        for date_str, state in (other_thread.desired_state or {}).items():
            date = datetime.date.fromisoformat(date_str)
            if date >= today:
                requests[date] = RequestedState(other_thread.pk, DayState(state["leave_type"], state["wfh_type"]))
    return requests


def serialize_desired(desired: dict[datetime.date, DayState]) -> dict[str, dict[str, int | None]]:
    return {date.isoformat(): state.as_dict() for date, state in sorted(desired.items())}


def apply_changes(user: User, thread: SlackAvailabilityThread, changes: list[PlannedChange]):
    """
    Write planned changes to the journal and record ownership

    Callers run this inside a transaction.
    Raises ReconcileConflictError when a journal no longer holds the value the change was planned from.
    """
    dates = [change.date for change in changes if change.action not in MANUAL_VALUE_ACTIONS]
    journals = {
        journal.date: journal
        for journal in Journal.objects.select_for_update().filter(user=user, date__in=dates).order_by("date")
    }

    for change in changes:
        if change.action in MANUAL_VALUE_ACTIONS:
            continue

        journal = journals.get(change.date)
        current_state = EMPTY_DAY_STATE if journal is None else DayState.from_journal(journal)
        if current_state != change.before:
            raise ReconcileConflictError(f"Journal changed for {change.date}")

        if change.action in JOURNAL_CHANGING_ACTIONS:
            if journal is None:
                journal = Journal(user=user, date=change.date)
            journal.leave_type = change.after.leave_type
            journal.wfh_type = change.after.wfh_type
            journal.leave_wfh_check()
            journal.save()

        if journal is None:
            continue

        if change.action in (ChangeAction.REMOVE, ChangeAction.DROP):
            SlackAvailabilityJournalEntry.objects.filter(journal=journal).delete()
        else:
            SlackAvailabilityJournalEntry.objects.update_or_create(
                journal=journal,
                defaults={
                    "thread_id": change.owner_thread_id or thread.pk,
                    "leave_type": change.after.leave_type,
                    "wfh_type": change.after.wfh_type,
                },
            )
