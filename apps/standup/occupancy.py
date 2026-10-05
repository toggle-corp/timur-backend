import dataclasses
import datetime

from django.db import models

from apps.common.models import Event
from apps.journal.models import Journal
from apps.track.models import TimeEntry
from apps.user.models import User

WORKING_HOURS_PER_DAY = 7
# Number of days into a month during which the previous month is also included
PREVIOUS_MONTH_GRACE_DAYS = 7


@dataclasses.dataclass
class UserDayOccupancy:
    date: datetime.date
    hours: float | None
    leave: Journal.LeaveType | None
    # None when there are no time entries and no full day leave
    occupancy: float | None


@dataclasses.dataclass
class UserOccupancy:
    user: User
    days: list[UserDayOccupancy]


@dataclasses.dataclass
class Occupancy:
    start_date: datetime.date
    end_date: datetime.date
    dates: list[datetime.date]
    users: list[UserOccupancy]


def get_occupancy_date_range(date: datetime.date) -> tuple[datetime.date, datetime.date]:
    """
    Return (start_date, end_date) for the occupancy shown on the standup of the given date.
    Covers the current month up to the previous day, plus the previous month during the first week.
    """
    start_date = date.replace(day=1)
    if date.day <= PREVIOUS_MONTH_GRACE_DAYS:
        start_date = (start_date - datetime.timedelta(days=1)).replace(day=1)
    return start_date, date - datetime.timedelta(days=1)


def calculate_occupancy(hours: float | None, leave: Journal.LeaveType | None) -> float | None:
    if leave == Journal.LeaveType.FULL:
        return 0
    if hours is None:
        return None
    if leave in (Journal.LeaveType.FIRST_HALF, Journal.LeaveType.SECOND_HALF):
        # Only half of the day is expected to be logged
        return round(hours * 2 / WORKING_HOURS_PER_DAY, 2)
    return round(hours / WORKING_HOURS_PER_DAY, 2)


def get_occupancy(date: datetime.date) -> Occupancy:
    start_date, end_date = get_occupancy_date_range(date)
    dates = Event.generate_dates(start_date, end_date)

    users = list(User.get_standup_slide_user_qs().order_by("display_name"))

    hours_qs = (
        TimeEntry.objects.filter(
            user__in=users,
            date__in=dates,
            duration__gt=0,
        )
        .exclude(status=TimeEntry.Status.TODO)
        .order_by()
        .values("user_id", "date")
        .annotate(total_minutes=models.Sum("duration"))
        .values_list("user_id", "date", "total_minutes")
    )
    hours_map = {(user_id, _date): round(total_minutes / 60, 2) for user_id, _date, total_minutes in hours_qs}

    leave_qs = Journal.objects.filter(
        user__in=users,
        date__in=dates,
        leave_type__isnull=False,
    ).values_list("user_id", "date", "leave_type")
    leave_map = {(user_id, _date): Journal.LeaveType(leave_type) for user_id, _date, leave_type in leave_qs}

    users_occupancy = []
    for user in users:
        days = []
        for _date in dates:
            hours = hours_map.get((user.pk, _date))
            leave = leave_map.get((user.pk, _date))
            days.append(
                UserDayOccupancy(
                    date=_date,
                    hours=hours,
                    leave=leave,
                    occupancy=calculate_occupancy(hours, leave),
                ),
            )
        users_occupancy.append(UserOccupancy(user=user, days=days))

    return Occupancy(
        start_date=start_date,
        end_date=end_date,
        dates=dates,
        users=users_occupancy,
    )
