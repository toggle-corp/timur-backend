import dataclasses
import datetime

from django.utils import timezone

from apps.common.models import Event

from .structs import AvailabilityRange, DayState

MAX_DAYS_AHEAD = 90


def local_datetime_from_ts(ts: str) -> datetime.datetime:
    """
    Convert a Slack message ts (epoch seconds) to a datetime in the app timezone
    """
    return timezone.localtime(datetime.datetime.fromtimestamp(float(ts), tz=datetime.UTC))


@dataclasses.dataclass
class ExpandedAvailability:
    desired: dict[datetime.date, DayState]
    """Working dates (today onwards) with the leave/WFH values to set, sorted by date"""
    unknown_half_dates: list[datetime.date]
    """Dates held back because the half (first/second) is unknown"""
    invalid_ranges: list[AvailabilityRange]
    """Ranges with a leave/WFH combination the Journal does not allow"""


def expand_ranges(ranges: list[AvailabilityRange], today: datetime.date) -> ExpandedAvailability:
    """
    Expand ranges into working dates between today and MAX_DAYS_AHEAD

    Weekends and holidays are skipped. When ranges overlap, their values are merged if the
    combination is valid, otherwise the later range wins. An open-ended range that started before
    today still covers today.
    """
    last_date = today + datetime.timedelta(days=MAX_DAYS_AHEAD)
    desired: dict[datetime.date, DayState] = {}
    unknown_half_dates: set[datetime.date] = set()
    invalid_ranges: list[AvailabilityRange] = []

    for availability_range in ranges:
        start_date, end_date = sorted([availability_range.start_date, availability_range.end_date])
        if availability_range.open_end:
            end_date = max(end_date, today)
        start_date = max(start_date, today)
        end_date = min(end_date, last_date)
        if start_date > end_date:
            continue

        dates = Event.generate_dates(start_date, end_date)

        if availability_range.has_unknown_half:
            unknown_half_dates.update(dates)
            continue

        state = availability_range.as_day_state()
        if state.is_empty:
            continue
        if not state.is_valid:
            invalid_ranges.append(availability_range)
            continue

        for date in dates:
            existing_state = desired.get(date)
            if existing_state is None:
                desired[date] = state
                continue
            merged_state = DayState(
                leave_type=state.leave_type if state.leave_type is not None else existing_state.leave_type,
                wfh_type=state.wfh_type if state.wfh_type is not None else existing_state.wfh_type,
            )
            desired[date] = merged_state if merged_state.is_valid else state

    return ExpandedAvailability(
        desired=dict(sorted(desired.items())),
        unknown_half_dates=sorted(unknown_half_dates - desired.keys()),
        invalid_ranges=invalid_ranges,
    )
