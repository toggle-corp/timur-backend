import datetime
import typing
import zoneinfo

from django.test import override_settings

from apps.common.factories import EventFactory
from apps.common.models import Event
from apps.journal.models import Journal
from apps.slack_availability.dates import MAX_DAYS_AHEAD, expand_ranges, local_datetime_from_ts
from apps.slack_availability.structs import AvailabilityRange, DayState, Half
from apps.user.factories import UserFactory
from main.tests import TestCase

LT = Journal.LeaveType
WT = Journal.WorkFromHomeType


def next_monday() -> datetime.date:
    today = datetime.date.today()
    return today + datetime.timedelta(days=7 - today.weekday())


def days(date: datetime.date, n: int) -> datetime.date:
    return date + datetime.timedelta(days=n)


class TestLocalDatetimeFromTs(TestCase):
    @override_settings(TIME_ZONE="Asia/Kathmandu")
    def test_local_datetime_from_ts(self):
        # 2026-10-14 18:20 UTC is 2026-10-15 00:05 in Kathmandu (+05:45)
        ts = f"{datetime.datetime(2026, 10, 14, 18, 20, tzinfo=datetime.UTC).timestamp():.6f}"
        local_dt = local_datetime_from_ts(ts)
        assert local_dt.tzinfo == zoneinfo.ZoneInfo("Asia/Kathmandu")
        assert local_dt.date() == datetime.date(2026, 10, 15)

        # Just before midnight stays on the same day
        ts = f"{datetime.datetime(2026, 10, 14, 18, 13, tzinfo=datetime.UTC).timestamp():.6f}"
        assert local_datetime_from_ts(ts).date() == datetime.date(2026, 10, 14)


class TestExpandRanges(TestCase):
    @classmethod
    @typing.override
    def setUpTestData(cls):
        user = UserFactory.create()
        cls.monday = next_monday()
        cls.wednesday = days(cls.monday, 2)
        EventFactory.create(
            type=Event.Type.HOLIDAY,
            start_date=cls.wednesday,
            end_date=cls.wednesday,
            created_by=user,
            modified_by=user,
        )

    def test_range_skips_weekends_and_holidays(self):
        result = expand_ranges(
            [AvailabilityRange(self.monday, days(self.monday, 7), leave=Half.FULL)],
            today=self.monday,
        )
        assert list(result.desired.keys()) == [
            self.monday,
            days(self.monday, 1),
            days(self.monday, 3),
            days(self.monday, 4),
            days(self.monday, 7),
        ]
        assert set(result.desired.values()) == {DayState(leave_type=LT.FULL)}

    def test_open_ended_range_started_before_today_covers_today(self):
        tuesday = days(self.monday, 1)
        friday_before = days(self.monday, -3)
        result = expand_ranges(
            [AvailabilityRange(friday_before, friday_before, leave=Half.FULL, open_end=True)],
            today=tuesday,
        )
        assert result.desired == {tuesday: DayState(leave_type=LT.FULL)}

        # Today a holiday: nothing to write
        result = expand_ranges(
            [AvailabilityRange(friday_before, friday_before, leave=Half.FULL, open_end=True)],
            today=self.wednesday,
        )
        assert result.desired == {}

        # Not open-ended: a past range writes nothing
        result = expand_ranges([AvailabilityRange(friday_before, friday_before, leave=Half.FULL)], today=tuesday)
        assert result.desired == {}

    def test_single_holiday_and_weekend_are_dropped(self):
        result = expand_ranges(
            [
                AvailabilityRange(self.wednesday, self.wednesday, leave=Half.FULL),
                AvailabilityRange(days(self.monday, 5), days(self.monday, 5), wfh=Half.FULL),
            ],
            today=self.monday,
        )
        assert result.desired == {}

    def test_past_dates_are_dropped(self):
        result = expand_ranges(
            [
                AvailabilityRange(days(self.monday, -7), days(self.monday, -3), leave=Half.FULL),
                AvailabilityRange(days(self.monday, -7), days(self.monday, 1), wfh=Half.FULL),
            ],
            today=self.monday,
        )
        assert result.desired == {
            self.monday: DayState(wfh_type=WT.FULL),
            days(self.monday, 1): DayState(wfh_type=WT.FULL),
        }

    def test_dates_beyond_cap_are_dropped(self):
        last_allowed = days(self.monday, MAX_DAYS_AHEAD)
        result = expand_ranges(
            [
                AvailabilityRange(days(last_allowed, -6), days(last_allowed, 10), leave=Half.FULL),
                AvailabilityRange(days(last_allowed, 1), days(last_allowed, 3), wfh=Half.FULL),
            ],
            today=self.monday,
        )
        assert result.desired
        assert max(result.desired.keys()) <= last_allowed
        assert all(state == DayState(leave_type=LT.FULL) for state in result.desired.values())

    def test_reversed_range_is_swapped(self):
        result = expand_ranges(
            [AvailabilityRange(days(self.monday, 1), self.monday, leave=Half.FIRST_HALF)],
            today=self.monday,
        )
        assert result.desired == {
            self.monday: DayState(leave_type=LT.FIRST_HALF),
            days(self.monday, 1): DayState(leave_type=LT.FIRST_HALF),
        }

    def test_split_halves_are_merged(self):
        result = expand_ranges(
            [
                AvailabilityRange(self.monday, self.monday, leave=Half.FIRST_HALF),
                AvailabilityRange(self.monday, self.monday, wfh=Half.SECOND_HALF),
                # Same date, mixed in one range
                AvailabilityRange(days(self.monday, 1), days(self.monday, 1), leave=Half.SECOND_HALF, wfh=Half.FIRST_HALF),
            ],
            today=self.monday,
        )
        assert result.desired == {
            self.monday: DayState(leave_type=LT.FIRST_HALF, wfh_type=WT.SECOND_HALF),
            days(self.monday, 1): DayState(leave_type=LT.SECOND_HALF, wfh_type=WT.FIRST_HALF),
        }

    def test_conflicting_values_use_the_later_range(self):
        result = expand_ranges(
            [
                AvailabilityRange(self.monday, self.monday, leave=Half.FULL),
                AvailabilityRange(self.monday, self.monday, wfh=Half.FULL),
            ],
            today=self.monday,
        )
        assert result.desired == {self.monday: DayState(wfh_type=WT.FULL)}

    def test_invalid_combination_is_dropped(self):
        invalid_range = AvailabilityRange(self.monday, self.monday, leave=Half.FULL, wfh=Half.FULL)
        result = expand_ranges([invalid_range], today=self.monday)
        assert result.desired == {}
        assert result.invalid_ranges == [invalid_range]

    def test_empty_range_is_ignored(self):
        result = expand_ranges([AvailabilityRange(self.monday, self.monday)], today=self.monday)
        assert result.desired == {}
        assert result.invalid_ranges == []

    def test_unknown_half_is_held_back(self):
        result = expand_ranges(
            [
                AvailabilityRange(self.monday, days(self.monday, 1), leave=Half.UNKNOWN),
                AvailabilityRange(days(self.monday, 3), days(self.monday, 3), leave=Half.FULL),
                # A definite value for the same date wins
                AvailabilityRange(days(self.monday, 1), days(self.monday, 1), wfh=Half.FULL),
            ],
            today=self.monday,
        )
        assert result.desired == {
            days(self.monday, 1): DayState(wfh_type=WT.FULL),
            days(self.monday, 3): DayState(leave_type=LT.FULL),
        }
        assert result.unknown_half_dates == [self.monday]
