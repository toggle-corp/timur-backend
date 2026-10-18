import datetime
import typing

import pytest
from django.utils import timezone

from apps.journal.factories import JournalFactory
from apps.journal.models import Journal
from apps.slack_availability.factories import (
    SlackAvailabilityJournalEntryFactory,
    SlackAvailabilityThreadFactory,
)
from apps.slack_availability.models import SlackAvailabilityJournalEntry
from apps.slack_availability.reconcile import (
    ChangeAction,
    OwnedState,
    PlannedChange,
    ReconcileConflictError,
    RequestedState,
    apply_changes,
    load_journal_state,
    load_other_requests,
    plan_changes,
    serialize_desired,
)
from apps.slack_availability.structs import EMPTY_DAY_STATE, DayState
from apps.user.factories import UserFactory
from main.tests import TestCase

LT = Journal.LeaveType
WT = Journal.WorkFromHomeType

TODAY = datetime.date(2026, 10, 12)  # Monday
D = [TODAY + datetime.timedelta(days=n) for n in range(10)]

LEAVE = DayState(leave_type=LT.FULL)
WFH = DayState(wfh_type=WT.FULL)
LEAVE_FH = DayState(leave_type=LT.FIRST_HALF)


def actions(changes: list[PlannedChange]) -> list[tuple[datetime.date, ChangeAction]]:
    return [(change.date, change.action) for change in changes]


class TestPlanChanges:
    THREAD = 1
    OTHER_THREAD = 2

    def test_new_dates_are_added(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={D[1]: LEAVE, D[2]: WFH},
            current={},
            owned={},
        )
        assert changes == [
            PlannedChange(D[1], ChangeAction.ADD, before=EMPTY_DAY_STATE, after=LEAVE),
            PlannedChange(D[2], ChangeAction.ADD, before=EMPTY_DAY_STATE, after=WFH),
        ]

    def test_owned_dates_are_updated(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={D[1]: WFH},
            current={D[1]: LEAVE},
            owned={D[1]: OwnedState(self.THREAD, LEAVE)},
        )
        assert changes == [PlannedChange(D[1], ChangeAction.UPDATE, before=LEAVE, after=WFH)]

    def test_dates_owned_by_another_thread_are_updated(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={D[1]: WFH},
            current={D[1]: LEAVE},
            owned={D[1]: OwnedState(self.OTHER_THREAD, LEAVE)},
        )
        assert actions(changes) == [(D[1], ChangeAction.UPDATE)]

    def test_dropped_dates_are_removed(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={D[1]: LEAVE},
            current={D[1]: LEAVE, D[2]: LEAVE},
            owned={
                D[1]: OwnedState(self.THREAD, LEAVE),
                D[2]: OwnedState(self.THREAD, LEAVE),
            },
        )
        assert changes == [PlannedChange(D[2], ChangeAction.REMOVE, before=LEAVE, after=EMPTY_DAY_STATE)]

    def test_dates_owned_by_another_thread_are_not_removed(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={},
            current={D[2]: LEAVE},
            owned={D[2]: OwnedState(self.OTHER_THREAD, LEAVE)},
        )
        assert changes == []

    def test_manual_values_are_skipped(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={D[1]: LEAVE, D[2]: LEAVE},
            current={D[1]: WFH, D[2]: LEAVE_FH},
            # User changed the value Timur wrote
            owned={D[2]: OwnedState(self.THREAD, LEAVE)},
        )
        assert changes == [
            PlannedChange(D[1], ChangeAction.SKIP, before=WFH, after=LEAVE),
            PlannedChange(D[2], ChangeAction.SKIP, before=LEAVE_FH, after=LEAVE),
        ]

    def test_manual_values_are_not_removed(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={},
            current={D[2]: WFH},
            owned={D[2]: OwnedState(self.THREAD, LEAVE)},
        )
        assert changes == [PlannedChange(D[2], ChangeAction.DROP, before=WFH, after=WFH)]

    def test_matching_values_are_unchanged_claimed_or_matched(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={D[1]: LEAVE, D[2]: LEAVE, D[3]: LEAVE, D[4]: WFH},
            current={D[1]: LEAVE, D[2]: LEAVE, D[3]: LEAVE, D[4]: WFH},
            owned={
                D[1]: OwnedState(self.THREAD, LEAVE),
                D[2]: OwnedState(self.OTHER_THREAD, LEAVE),
                # D[3]: manual value, same as desired
                # D[4]: user changed the value Timur wrote to the desired one
                D[4]: OwnedState(self.THREAD, LEAVE),
            },
        )
        assert changes == [
            PlannedChange(D[2], ChangeAction.CLAIM, before=LEAVE, after=LEAVE),
            PlannedChange(D[3], ChangeAction.MATCH, before=LEAVE, after=LEAVE),
            PlannedChange(D[4], ChangeAction.MATCH, before=WFH, after=WFH),
        ]

    def test_empty_desired_and_journal_is_not_a_match(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={D[1]: EMPTY_DAY_STATE},
            current={},
            owned={},
        )
        assert changes == []

    def test_past_dates_are_never_touched(self):
        yesterday = TODAY - datetime.timedelta(days=1)
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={yesterday: WFH},
            current={yesterday: LEAVE},
            owned={yesterday: OwnedState(self.THREAD, LEAVE)},
        )
        assert changes == []

    def test_empty_journal_with_stale_ownership_is_added(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={D[1]: LEAVE},
            current={D[1]: EMPTY_DAY_STATE},
            owned={D[1]: OwnedState(self.OTHER_THREAD, WFH)},
        )
        assert changes == [PlannedChange(D[1], ChangeAction.ADD, before=EMPTY_DAY_STATE, after=LEAVE)]

    def test_dropped_dates_go_to_another_thread_asking_for_them(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={},
            current={D[1]: LEAVE, D[2]: WFH, D[3]: LEAVE},
            owned={
                D[1]: OwnedState(self.THREAD, LEAVE),
                D[2]: OwnedState(self.THREAD, WFH),
                D[3]: OwnedState(self.THREAD, LEAVE),
            },
            other_requests={
                # Same value: only ownership moves
                D[1]: RequestedState(self.OTHER_THREAD, LEAVE),
                # Other value: the other thread's value is written
                D[2]: RequestedState(self.OTHER_THREAD, LEAVE),
            },
        )
        assert changes == [
            PlannedChange(D[1], ChangeAction.TRANSFER, before=LEAVE, after=LEAVE, owner_thread_id=self.OTHER_THREAD),
            PlannedChange(D[2], ChangeAction.UPDATE, before=WFH, after=LEAVE, owner_thread_id=self.OTHER_THREAD),
            PlannedChange(D[3], ChangeAction.REMOVE, before=LEAVE, after=EMPTY_DAY_STATE),
        ]

    def test_other_requests_do_not_override_manual_values(self):
        changes = plan_changes(
            thread_id=self.THREAD,
            today=TODAY,
            desired={},
            current={D[1]: WFH},
            owned={D[1]: OwnedState(self.THREAD, LEAVE)},
            other_requests={D[1]: RequestedState(self.OTHER_THREAD, LEAVE)},
        )
        assert actions(changes) == [(D[1], ChangeAction.DROP)]


class TestApplyChanges(TestCase):
    @classmethod
    @typing.override
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.thread = SlackAvailabilityThreadFactory.create(user=cls.user, slack_user_id=cls.user.slack_user_id)
        cls.other_thread = SlackAvailabilityThreadFactory.create(user=cls.user, slack_user_id=cls.user.slack_user_id)

    def journal_state(self, date: datetime.date) -> DayState | None:
        journal = Journal.objects.filter(user=self.user, date=date).first()
        return journal and DayState.from_journal(journal)

    def entry_of(self, date: datetime.date) -> SlackAvailabilityJournalEntry | None:
        return SlackAvailabilityJournalEntry.objects.filter(journal__user=self.user, journal__date=date).first()

    def test_load_journal_state(self):
        j1 = JournalFactory.create(user=self.user, date=D[1], leave_type=LT.FULL)
        JournalFactory.create(user=self.user, date=D[2], wfh_type=WT.FULL)
        JournalFactory.create(user=UserFactory.create(), date=D[1], wfh_type=WT.FULL)
        SlackAvailabilityJournalEntryFactory.create(journal=j1, thread=self.other_thread, leave_type=LT.FULL)
        SlackAvailabilityJournalEntryFactory.create(
            journal=JournalFactory.create(user=self.user, date=D[5], wfh_type=WT.FULL),
            thread=self.thread,
            leave_type=LT.FULL,
        )

        current, owned = load_journal_state(self.user, self.thread, dates={D[1], D[2], D[3]})
        # Dates owned by this thread are always included
        assert current == {D[1]: LEAVE, D[2]: WFH, D[5]: WFH}
        assert owned == {
            D[1]: OwnedState(self.other_thread.pk, LEAVE),
            D[5]: OwnedState(self.thread.pk, LEAVE),
        }

    def test_apply_changes(self):
        JournalFactory.create(user=self.user, date=D[1], journal_text="Did things")
        j2 = JournalFactory.create(user=self.user, date=D[2], leave_type=LT.FULL)
        j3 = JournalFactory.create(user=self.user, date=D[3], leave_type=LT.FULL, journal_text="Notes")
        j4 = JournalFactory.create(user=self.user, date=D[4], leave_type=LT.FULL)
        j5 = JournalFactory.create(user=self.user, date=D[5], wfh_type=WT.FULL)
        JournalFactory.create(user=self.user, date=D[6], leave_type=LT.FULL)
        JournalFactory.create(user=self.user, date=D[7], wfh_type=WT.FULL)
        SlackAvailabilityJournalEntryFactory.create(journal=j2, thread=self.thread, leave_type=LT.FULL)
        SlackAvailabilityJournalEntryFactory.create(journal=j3, thread=self.thread, leave_type=LT.FULL)
        SlackAvailabilityJournalEntryFactory.create(journal=j4, thread=self.other_thread, leave_type=LT.FULL)
        SlackAvailabilityJournalEntryFactory.create(journal=j5, thread=self.thread, leave_type=LT.FULL)

        apply_changes(
            self.user,
            self.thread,
            [
                PlannedChange(D[0], ChangeAction.ADD, before=EMPTY_DAY_STATE, after=LEAVE),
                PlannedChange(D[1], ChangeAction.ADD, before=EMPTY_DAY_STATE, after=WFH),
                PlannedChange(D[2], ChangeAction.UPDATE, before=LEAVE, after=LEAVE_FH),
                PlannedChange(D[3], ChangeAction.REMOVE, before=LEAVE, after=EMPTY_DAY_STATE),
                PlannedChange(D[4], ChangeAction.CLAIM, before=LEAVE, after=LEAVE),
                PlannedChange(D[5], ChangeAction.DROP, before=WFH, after=WFH),
                PlannedChange(D[6], ChangeAction.MATCH, before=LEAVE, after=LEAVE),
                PlannedChange(D[7], ChangeAction.SKIP, before=WFH, after=LEAVE),
            ],
        )

        # New journal is created
        assert self.journal_state(D[0]) == LEAVE
        # Existing journal is updated, journal_text untouched
        assert self.journal_state(D[1]) == WFH
        assert Journal.objects.get(user=self.user, date=D[1]).journal_text == "Did things"
        assert self.journal_state(D[2]) == LEAVE_FH
        # Removed: values cleared, row kept
        assert self.journal_state(D[3]) == EMPTY_DAY_STATE
        assert Journal.objects.get(user=self.user, date=D[3]).journal_text == "Notes"
        # Claimed: values unchanged
        assert self.journal_state(D[4]) == LEAVE
        # Dropped: values unchanged
        assert self.journal_state(D[5]) == WFH
        # Matched and skipped manual values: unchanged, not owned
        assert self.journal_state(D[6]) == LEAVE
        assert self.journal_state(D[7]) == WFH

        # Ownership
        for date, state in [(D[0], LEAVE), (D[1], WFH), (D[2], LEAVE_FH), (D[4], LEAVE)]:
            entry = self.entry_of(date)
            assert entry is not None
            assert entry.thread_id == self.thread.pk
            assert DayState(entry.leave_type, entry.wfh_type) == state
        assert self.entry_of(D[3]) is None
        assert self.entry_of(D[5]) is None
        assert self.entry_of(D[6]) is None
        assert self.entry_of(D[7]) is None

    def test_apply_changes_with_new_owner(self):
        j1 = JournalFactory.create(user=self.user, date=D[1], leave_type=LT.FULL)
        j2 = JournalFactory.create(user=self.user, date=D[2], wfh_type=WT.FULL)
        SlackAvailabilityJournalEntryFactory.create(journal=j1, thread=self.thread, leave_type=LT.FULL)
        SlackAvailabilityJournalEntryFactory.create(journal=j2, thread=self.thread, wfh_type=WT.FULL)

        apply_changes(
            self.user,
            self.thread,
            [
                PlannedChange(
                    D[1],
                    ChangeAction.TRANSFER,
                    before=LEAVE,
                    after=LEAVE,
                    owner_thread_id=self.other_thread.pk,
                ),
                PlannedChange(D[2], ChangeAction.UPDATE, before=WFH, after=LEAVE, owner_thread_id=self.other_thread.pk),
            ],
        )

        assert self.journal_state(D[1]) == LEAVE
        assert self.journal_state(D[2]) == LEAVE
        for date in [D[1], D[2]]:
            entry = self.entry_of(date)
            assert entry is not None
            assert entry.thread_id == self.other_thread.pk
            assert DayState(entry.leave_type, entry.wfh_type) == LEAVE

    def test_apply_changes_conflict(self):
        # Planned from an empty journal, but the user set WFH in the meantime
        JournalFactory.create(user=self.user, date=D[1], wfh_type=WT.FULL)

        with pytest.raises(ReconcileConflictError):
            apply_changes(
                self.user,
                self.thread,
                [PlannedChange(D[1], ChangeAction.ADD, before=EMPTY_DAY_STATE, after=LEAVE)],
            )
        assert self.journal_state(D[1]) == WFH

    def test_load_other_requests(self):
        now = timezone.now()
        older = SlackAvailabilityThreadFactory.create(
            user=self.user,
            snapshot_at=now - datetime.timedelta(hours=2),
            desired_state=serialize_desired({D[1]: WFH, D[2]: WFH, TODAY - datetime.timedelta(days=1): WFH}),
        )
        newer = SlackAvailabilityThreadFactory.create(
            user=self.user,
            snapshot_at=now - datetime.timedelta(hours=1),
            desired_state=serialize_desired({D[2]: LEAVE}),
        )
        # Not considered: deleted, read too long ago, the thread itself, another user
        SlackAvailabilityThreadFactory.create(
            user=self.user,
            snapshot_at=now,
            is_deleted=True,
            desired_state=serialize_desired({D[3]: LEAVE}),
        )
        SlackAvailabilityThreadFactory.create(
            user=self.user,
            snapshot_at=now - datetime.timedelta(days=200),
            desired_state=serialize_desired({D[4]: LEAVE}),
        )
        self.thread.snapshot_at = now
        self.thread.desired_state = serialize_desired({D[5]: LEAVE})
        self.thread.save()
        SlackAvailabilityThreadFactory.create(
            user=UserFactory.create(),
            snapshot_at=now,
            desired_state=serialize_desired({D[6]: LEAVE}),
        )

        assert load_other_requests(self.user, self.thread, TODAY) == {
            D[1]: RequestedState(older.pk, WFH),
            D[2]: RequestedState(newer.pk, LEAVE),
        }
