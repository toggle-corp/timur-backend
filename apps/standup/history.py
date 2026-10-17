import dataclasses
import datetime
from collections import defaultdict

from django.db import models
from django.db.models.functions import TruncMonth

from apps.journal.models import Journal
from apps.standup.occupancy import (
    get_leave_days,
    get_occupancy,
    get_work_from_home_days,
    get_working_dates,
)
from apps.track.models import TimeEntry
from apps.user.models import User

# Months of history of a person, ending with the month of the end date
PERSON_HISTORY_MONTHS = 12


def get_ratio(value: float, total: float) -> float | None:
    return round(value / total, 4) if total else None


def add_months(month: datetime.date, count: int) -> datetime.date:
    index = month.year * 12 + month.month - 1 + count
    return datetime.date(index // 12, index % 12 + 1, 1)


@dataclasses.dataclass
class PersonMonth:
    start_date: datetime.date
    hours: float = 0
    capacity_hours: float = 0
    working_days: int = 0
    missing_days: int = 0
    leave_conflict_days: int = 0
    # Leave on working days, with a half day counted as half
    leave_days: float = 0
    # With a half day counted as half
    work_from_home_days: float = 0
    due_days: int = 0
    late_days: int = 0

    @property
    def occupancy(self) -> float | None:
        return get_ratio(self.hours, self.capacity_hours)

    @property
    def late_share(self) -> float | None:
        return get_ratio(self.late_days, self.due_days)


def get_month_starts(start_date: datetime.date, end_date: datetime.date) -> list[datetime.date]:
    month_starts = []
    month_start = start_date.replace(day=1)
    while month_start <= end_date:
        month_starts.append(month_start)
        month_start = add_months(month_start, 1)
    return month_starts


def get_person_months(
    user_qs: models.QuerySet[User],
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[tuple[User, dict[datetime.date, PersonMonth]]]:
    """Each person's figures for every month from the month of start_date up to end_date, by month start."""
    occupancy = get_occupancy(start_date, end_date, get_working_dates(start_date, end_date), user_qs, with_pending=True)

    month_minutes_rows = (
        TimeEntry.get_logged_qs()
        .order_by()
        .filter(user__in=user_qs, date__range=(start_date, end_date))
        .annotate(month=TruncMonth("date"))
        .values_list("user_id", "month")
        .annotate(minutes=models.Sum("duration"))
    )
    minutes_map: dict[tuple[int, datetime.date], int] = defaultdict(int)
    for user_id, month, minutes in month_minutes_rows:
        minutes_map[(user_id, month)] += minutes

    month_starts = get_month_starts(start_date, end_date)
    person_months = []
    for user_occupancy in occupancy.users:
        user_id = user_occupancy.user.pk
        months = {
            month_start: PersonMonth(
                start_date=month_start,
                hours=round(minutes_map[(user_id, month_start)] / 60, 2),
            )
            for month_start in month_starts
        }
        for day in user_occupancy.days:
            person_month = months[day.date.replace(day=1)]
            person_month.capacity_hours += day.expected_hours
            person_month.working_days += day.expected_hours > 0
            person_month.missing_days += day.occupancy is None and day.expected_hours > 0
            person_month.leave_conflict_days += day.leave == Journal.LeaveType.FULL and day.hours is not None
            person_month.leave_days += get_leave_days(day.leave)
            person_month.work_from_home_days += get_work_from_home_days(day.work_from_home)
            person_month.due_days += day.is_due
            person_month.late_days += day.is_late
        person_months.append((user_occupancy.user, months))
    return person_months


@dataclasses.dataclass
class PersonHistory:
    # Oldest first, ending with the month of the end date
    months: list[PersonMonth]
    leave_days_this_year: float


def get_person_history(user_id: int, end_date: datetime.date) -> PersonHistory | None:
    """A person's figures for PERSON_HISTORY_MONTHS months up to end_date, and their leave in its year up to it."""
    year_start_date = end_date.replace(month=1, day=1)
    start_date = min(add_months(end_date.replace(day=1), 1 - PERSON_HISTORY_MONTHS), year_start_date)
    person_months = get_person_months(User.objects.filter(pk=user_id), start_date, end_date)
    if not person_months:
        return None
    ((_, months),) = person_months
    return PersonHistory(
        months=list(months.values())[-PERSON_HISTORY_MONTHS:],
        leave_days_this_year=sum(month.leave_days for month in months.values() if month.start_date >= year_start_date),
    )
