import bisect
import dataclasses
import datetime
import typing

from django.db import models
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.common.models import Event
from apps.journal.models import Journal
from apps.track.models import TimeEntry
from apps.user.models import User

WORKING_HOURS_PER_DAY = 7
# Number of days into a month during which the previous month is also included
PREVIOUS_MONTH_GRACE_DAYS = 7
# Number of days shown after the first week of a month
ROLLING_WINDOW_DAYS = 30
# Longest range accepted by the occupancy query, enough for any two calendar months
MAX_RANGE_DAYS = 62
# Entries of a date are due before this time, in the local time zone, on the person's next working day
LOGGING_DEADLINE = datetime.time(9, 15)
# The standup runs this long from the deadline
STANDUP_DURATION = datetime.timedelta(minutes=15)
# Days ahead of a range searched for the next working day, enough for any holiday or leave
DEADLINE_SEARCH_DAYS = 92
# Days with more hours logged than this are long
LONG_DAY_HOURS = 9
# The catch-all project for standups, meetings and miscellaneous work, which says nothing about focus.
# Matched by name, so renaming the project makes it count like any other.
BLANKET_PROJECT_NAME = "Togglecorp"
# Single entries with at least this many hours are long
LONG_ENTRY_HOURS = 6
# Descriptions of at most this many words are vague
VAGUE_DESCRIPTION_WORDS = 1
# Descriptions of at most this many words are vague on entries with at least VAGUE_SHORT_DESCRIPTION_HOURS
VAGUE_SHORT_DESCRIPTION_WORDS = 2
VAGUE_SHORT_DESCRIPTION_HOURS = 2


@dataclasses.dataclass
class UserDayOccupancy:
    date: datetime.date
    hours: float | None
    leave: Journal.LeaveType | None
    work_from_home: Journal.WorkFromHomeType | None
    # None when there are no time entries and no full day leave
    occupancy: float | None
    entries: int = 0
    # Zero outside the days the user is employed
    expected_hours: float = 0
    is_working_day: bool = True
    # Days from the date to the creation of its first entry, in the local time zone
    logging_lag: int | None = None
    # The first entry was created after the logging deadline
    is_logged_late: bool = False
    # The first entry was created during the standup
    is_logged_during_standup: bool = False
    # Before the logging deadline
    is_pending: bool = False
    last_created_at: datetime.datetime | None = None
    # Projects with hours on the day, other than the blanket project
    projects: int = 0

    @property
    def is_due(self) -> bool:
        return self.expected_hours > 0 and not self.is_pending

    @property
    def is_missing(self) -> bool:
        return self.occupancy is None and self.is_due

    @property
    def late_by_days(self) -> int | None:
        if self.is_due and self.is_logged_late:
            return self.logging_lag
        return None

    @property
    def is_late(self) -> bool:
        """Logged after the deadline. Days without hours are missing, not late."""
        return self.late_by_days is not None

    @property
    def logged_during_standup(self) -> bool:
        return self.is_due and self.is_logged_during_standup


@dataclasses.dataclass
class OccupancySummary:
    hours: float
    expected_hours: float
    occupancy: float | None
    leave_days: float
    work_from_home_days: float
    missing_days: int
    missing_share: float | None
    entries: int
    non_working_day_hours: float
    on_leave_hours: float
    due_days: int
    late_days: int
    late_share: float | None
    standup_days: int
    standup_share: float | None
    # Days of full leave with hours logged
    leave_conflict_days: int
    # Projects per day with hours, other than the blanket project
    projects_per_day: float | None
    long_entries: int
    # Hours of long entries as a share of the hours
    long_entry_share: float | None
    vague_entries: int
    # Vague entries as a share of the entries
    vague_entry_share: float | None


@dataclasses.dataclass
class ProjectHours:
    project_id: int
    hours: float
    last_date: datetime.date
    is_blanket: bool = False


@dataclasses.dataclass
class FlaggedEntry:
    id: int
    date: datetime.date
    hours: float
    description: str
    project_id: int
    task_name: str
    is_long: bool
    is_vague: bool


@dataclasses.dataclass
class UserOccupancy:
    user: User
    days: list[UserDayOccupancy]
    # Logged on weekends, holidays and retreats, which have no day of their own
    non_working_day_hours: float = 0
    non_working_day_entries: int = 0
    # Most hours first, then the latest activity
    projects: list[ProjectHours] = dataclasses.field(default_factory=list)
    # By date
    flagged_entries: list[FlaggedEntry] = dataclasses.field(default_factory=list)

    @property
    def top_project(self) -> tuple[ProjectHours, float | None] | None:
        """The project with the most hours other than the blanket project, and its share of the hours outside it."""
        projects = [item for item in self.projects if not item.is_blanket]
        hours = sum(item.hours for item in projects)
        if not hours:
            return None
        return projects[0], get_ratio(projects[0].hours, hours)

    @property
    def long_dates(self) -> list[datetime.date]:
        return [day.date for day in self.days if (day.hours or 0) > LONG_DAY_HOURS]

    @property
    def summary(self) -> OccupancySummary:
        return summarize_occupancy(
            self.days,
            self.non_working_day_hours,
            self.non_working_day_entries,
            self.flagged_entries,
        )


@dataclasses.dataclass
class Occupancy:
    start_date: datetime.date
    end_date: datetime.date
    dates: list[datetime.date]
    users: list[UserOccupancy]
    non_working_dates: set[datetime.date] = dataclasses.field(default_factory=set)
    # Names of the holidays and retreats by date
    event_names: dict[datetime.date, str] = dataclasses.field(default_factory=dict)
    # The same days of the previous month
    previous: "Occupancy | None" = None

    @property
    def summary(self) -> OccupancySummary:
        return summarize_occupancy(
            [day for user in self.users for day in user.days],
            sum(user.non_working_day_hours for user in self.users),
            sum(user.non_working_day_entries for user in self.users),
            [entry for user in self.users for entry in user.flagged_entries],
        )

    def get_period(self, start_date: datetime.date, end_date: datetime.date) -> "Occupancy":
        indexes = [index for index, date in enumerate(self.dates) if start_date <= date <= end_date]

        def in_range(dates: typing.Iterable[datetime.date]) -> set[datetime.date]:
            return {date for date in dates if start_date <= date <= end_date}

        return Occupancy(
            start_date=start_date,
            end_date=end_date,
            dates=[self.dates[index] for index in indexes],
            users=[
                dataclasses.replace(
                    user_occupancy,
                    days=[user_occupancy.days[index] for index in indexes],
                    flagged_entries=[
                        entry for entry in user_occupancy.flagged_entries if start_date <= entry.date <= end_date
                    ],
                )
                for user_occupancy in self.users
            ],
            non_working_dates=in_range(self.non_working_dates),
        )

    @property
    def missing_people(self) -> int:
        return sum(user.summary.missing_days > 0 for user in self.users)

    @property
    def data_as_of(self) -> datetime.datetime | None:
        return max(
            (day.last_created_at for user in self.users for day in user.days if day.last_created_at),
            default=None,
        )

    @property
    def day_summaries(self) -> list[OccupancySummary]:
        return [summarize_occupancy([user.days[index] for user in self.users]) for index in range(len(self.dates))]


def get_occupancy_date_range(date: datetime.date) -> tuple[datetime.date, datetime.date]:
    """
    Return (start_date, end_date) for the occupancy shown on the standup of the given date.
    Covers the whole previous month and the current month up to the previous day during the first week,
    and the last ROLLING_WINDOW_DAYS days otherwise.
    """
    end_date = date - datetime.timedelta(days=1)
    if date.day <= PREVIOUS_MONTH_GRACE_DAYS:
        return (date.replace(day=1) - datetime.timedelta(days=1)).replace(day=1), end_date
    return date - datetime.timedelta(days=ROLLING_WINDOW_DAYS), end_date


def validate_occupancy_range(start_date: datetime.date, end_date: datetime.date):
    if start_date > end_date:
        raise ValueError("Start date can't be greater than end date")
    if (end_date - start_date).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"Date range can't be longer than {MAX_RANGE_DAYS} days")


def get_previous_range(start_date: datetime.date, end_date: datetime.date) -> tuple[datetime.date, datetime.date]:
    """The same days of the previous month. A range up to the end of a month compares with the whole previous month."""

    def get_previous_month_date(date: datetime.date) -> datetime.date:
        previous_month_end = date.replace(day=1) - datetime.timedelta(days=1)
        return previous_month_end.replace(day=min(date.day, previous_month_end.day))

    if (end_date + datetime.timedelta(days=1)).day == 1:
        return get_previous_month_date(start_date), end_date.replace(day=1) - datetime.timedelta(days=1)
    return get_previous_month_date(start_date), get_previous_month_date(end_date)


def get_working_dates(start_date: datetime.date, end_date: datetime.date) -> list[datetime.date]:
    non_working_dates = Event.get_non_working_dates(start_date, end_date)
    return [
        date for date in Event.generate_dates(start_date, end_date, include_holidays=True) if date not in non_working_dates
    ]


def get_ratio(value: float, total: float) -> float | None:
    return round(value / total, 4) if total else None


def get_leave_days(leave: Journal.LeaveType | None) -> float:
    if leave is None:
        return 0
    return 1 if leave == Journal.LeaveType.FULL else 0.5


def get_work_from_home_days(work_from_home: Journal.WorkFromHomeType | None) -> float:
    if work_from_home is None:
        return 0
    return 1 if work_from_home == Journal.WorkFromHomeType.FULL else 0.5


def get_expected_hours(leave: Journal.LeaveType | None) -> float:
    if leave == Journal.LeaveType.FULL:
        return 0
    if leave in (Journal.LeaveType.FIRST_HALF, Journal.LeaveType.SECOND_HALF):
        return WORKING_HOURS_PER_DAY / 2
    return WORKING_HOURS_PER_DAY


def summarize_occupancy(
    days: list[UserDayOccupancy],
    non_working_day_hours: float = 0,
    non_working_day_entries: int = 0,
    flagged_entries: list[FlaggedEntry] | None = None,
) -> OccupancySummary:
    flagged_entries = flagged_entries or []
    logged_days = [day for day in days if day.hours is not None]
    hours = round(sum(day.hours or 0 for day in days) + non_working_day_hours, 2)
    expected_hours = sum(day.expected_hours for day in days)
    due_days = sum(day.is_due for day in days)
    late_days = sum(day.is_late for day in days)
    missing_days = sum(day.is_missing for day in days)
    standup_days = sum(day.logged_during_standup for day in days)
    entries = sum(day.entries for day in days) + non_working_day_entries
    long_entry_hours = sum(entry.hours or 0 for entry in flagged_entries if entry.is_long)
    vague_entries = sum(entry.is_vague for entry in flagged_entries)
    return OccupancySummary(
        hours=hours,
        expected_hours=expected_hours,
        occupancy=round(hours / expected_hours, 2) if expected_hours else None,
        leave_days=sum(get_leave_days(day.leave) for day in days),
        work_from_home_days=sum(get_work_from_home_days(day.work_from_home) for day in days),
        missing_days=missing_days,
        missing_share=get_ratio(missing_days, due_days),
        entries=entries,
        non_working_day_hours=round(
            sum(day.hours or 0 for day in days if not day.is_working_day) + non_working_day_hours,
            2,
        ),
        on_leave_hours=round(sum(day.hours or 0 for day in days if day.leave == Journal.LeaveType.FULL), 2),
        due_days=due_days,
        late_days=late_days,
        late_share=get_ratio(late_days, due_days),
        standup_days=standup_days,
        standup_share=get_ratio(standup_days, due_days),
        leave_conflict_days=sum(day.leave == Journal.LeaveType.FULL and day.hours is not None for day in days),
        projects_per_day=(round(sum(day.projects for day in logged_days) / len(logged_days), 2) if logged_days else None),
        long_entries=sum(entry.is_long for entry in flagged_entries),
        long_entry_share=get_ratio(long_entry_hours, hours),
        vague_entries=vague_entries,
        vague_entry_share=get_ratio(vague_entries, entries),
    )


def calculate_occupancy(hours: float | None, leave: Journal.LeaveType | None) -> float | None:
    if leave == Journal.LeaveType.FULL:
        return 0
    if hours is None:
        return None
    if leave in (Journal.LeaveType.FIRST_HALF, Journal.LeaveType.SECOND_HALF):
        # Only half of the day is expected to be logged
        return round(hours * 2 / WORKING_HOURS_PER_DAY, 2)
    return round(hours / WORKING_HOURS_PER_DAY, 2)


def get_logging_deadline(
    date: datetime.date,
    working_dates: list[datetime.date],
    full_leave_dates: set[datetime.date],
) -> datetime.datetime:
    """LOGGING_DEADLINE on the first of the sorted working dates after the date that is not a day of full leave."""
    next_dates = working_dates[bisect.bisect_right(working_dates, date) :]
    next_date = next((_date for _date in next_dates if _date not in full_leave_dates), next_dates[-1])
    return timezone.make_aware(datetime.datetime.combine(next_date, LOGGING_DEADLINE))


def get_standup_occupancy(date: datetime.date) -> Occupancy:
    start_date, end_date = get_occupancy_date_range(date)
    return get_occupancy(
        start_date,
        end_date,
        Event.generate_dates(start_date, end_date),
        User.get_standup_slide_user_qs(),
    )


def get_range_occupancy_user_qs(start_date: datetime.date, end_date: datetime.date) -> models.QuerySet[User]:
    """Users who joined by the end of the range, and are active or logged anything within the range."""
    in_range = models.Q(date__gte=start_date, date__lte=end_date)
    return User.objects.filter(
        models.Q(is_active=True)
        | models.Q(pk__in=TimeEntry.get_logged_qs().filter(in_range).values("user"))
        | models.Q(pk__in=Journal.objects.filter(in_range).values("user")),
        date_joined__date__lte=end_date,
    )


def get_user_project_hours(
    users: list[User],
    start_date: datetime.date,
    end_date: datetime.date,
) -> dict[int, list[ProjectHours]]:
    """Hours per project of each user, most hours first, then the latest activity."""
    rows = (
        TimeEntry.get_logged_qs()
        .filter(user__in=users, date__gte=start_date, date__lte=end_date)
        .order_by()
        .values_list("user_id", "task__contract__project_id", "task__contract__project__name")
        .annotate(minutes=models.Sum("duration"), last_date=models.Max("date"))
    )
    project_hours_map: dict[int, list[ProjectHours]] = {}
    for user_id, project_id, project_name, minutes, last_date in rows:
        project_hours_map.setdefault(user_id, []).append(
            ProjectHours(
                project_id=project_id,
                hours=round(minutes / 60, 2),
                last_date=last_date,
                is_blanket=project_name == BLANKET_PROJECT_NAME,
            ),
        )
    for projects in project_hours_map.values():
        projects.sort(key=lambda item: (-item.hours, -item.last_date.toordinal(), item.project_id))
    return project_hours_map


def get_user_day_project_counts(
    users: list[User],
    start_date: datetime.date,
    end_date: datetime.date,
) -> dict[tuple[int, datetime.date], int]:
    """Projects with hours of each user and day, other than the blanket project."""
    rows = (
        TimeEntry.get_logged_qs()
        .filter(user__in=users, date__gte=start_date, date__lte=end_date)
        .exclude(task__contract__project__name=BLANKET_PROJECT_NAME)
        .order_by()
        .values_list("user_id", "date")
        .annotate(projects=models.Count("task__contract__project", distinct=True))
    )
    return {(user_id, _date): projects for user_id, _date, projects in rows}


def is_vague_description(description: str, hours: float) -> bool:
    words = len(description.split())
    return words <= VAGUE_DESCRIPTION_WORDS or (
        words <= VAGUE_SHORT_DESCRIPTION_WORDS and hours >= VAGUE_SHORT_DESCRIPTION_HOURS
    )


def get_user_flagged_entries(occupancy: Occupancy) -> dict[int, list[FlaggedEntry]]:
    """Long and vague logged entries of each user, by date."""
    rows = (
        TimeEntry.get_logged_qs()
        .filter(
            user__in=[user_occupancy.user for user_occupancy in occupancy.users],
            date__gte=occupancy.start_date,
            date__lte=occupancy.end_date,
        )
        .order_by("date", "id")
        .values_list(
            "id",
            "user_id",
            "date",
            "duration",
            "description",
            "task__contract__project_id",
            "task__name",
        )
    )
    flagged_entries_map: dict[int, list[FlaggedEntry]] = {}
    for pk, user_id, _date, duration, description, project_id, task_name in rows:
        hours = round(duration / 60, 2)
        entry = FlaggedEntry(
            id=pk,
            date=_date,
            hours=hours,
            description=description,
            project_id=project_id,
            task_name=task_name,
            is_long=hours >= LONG_ENTRY_HOURS,
            is_vague=is_vague_description(description, hours),
        )
        if entry.is_long or entry.is_vague:
            flagged_entries_map.setdefault(user_id, []).append(entry)
    return flagged_entries_map


def get_non_working_event_names(start_date: datetime.date, end_date: datetime.date) -> dict[datetime.date, str]:
    names: dict[datetime.date, list[str]] = {}
    events_qs = Event.objects.filter(
        type__in=Event.Type.__NON_WORKING__,
        start_date__lte=end_date,
        end_date__gte=start_date,
    ).order_by("start_date", "name")
    for event in events_qs:
        for date in event.get_dates(include_weekends=True):
            if start_date <= date <= end_date:
                names.setdefault(date, []).append(event.name)
    return {date: ", ".join(date_names) for date, date_names in names.items()}


def get_range_occupancy(start_date: datetime.date, end_date: datetime.date) -> Occupancy:
    """
    Every day of the range, with no hours expected on weekends, holidays and retreats.
    The previous month is fetched together with the range, for the same people.
    """
    previous_start_date, previous_end_date = get_previous_range(start_date, end_date)
    dates = Event.generate_dates(previous_start_date, end_date, include_holidays=True, include_weekends=True)
    occupancy = get_occupancy(
        previous_start_date,
        end_date,
        dates,
        get_range_occupancy_user_qs(start_date, end_date).filter(
            # People who left are excluded from the slides, but stay in the months they worked
            models.Q(exclude_from_slides=False) | models.Q(is_active=False),
        ),
        non_working_dates=set(dates) - set(get_working_dates(previous_start_date, end_date)),
        with_pending=True,
    )
    flagged_entries_map = get_user_flagged_entries(occupancy)
    day_project_counts = get_user_day_project_counts(
        [user_occupancy.user for user_occupancy in occupancy.users],
        occupancy.start_date,
        occupancy.end_date,
    )
    for user_occupancy in occupancy.users:
        for day in user_occupancy.days:
            day.projects = day_project_counts.get((user_occupancy.user.pk, day.date), 0)
    for user_occupancy in occupancy.users:
        user_occupancy.flagged_entries = flagged_entries_map.get(user_occupancy.user.pk, [])
    range_occupancy = occupancy.get_period(start_date, end_date)
    range_occupancy.event_names = get_non_working_event_names(start_date, end_date)
    range_occupancy.previous = occupancy.get_period(previous_start_date, previous_end_date)
    project_hours_map = get_user_project_hours(
        [user_occupancy.user for user_occupancy in range_occupancy.users],
        start_date,
        end_date,
    )
    for user_occupancy in range_occupancy.users:
        user_occupancy.projects = project_hours_map.get(user_occupancy.user.pk, [])
    return range_occupancy


def get_occupancy(
    start_date: datetime.date,
    end_date: datetime.date,
    dates: list[datetime.date],
    user_qs: models.QuerySet[User],
    non_working_dates: set[datetime.date] | None = None,
    with_pending: bool = False,
) -> Occupancy:
    """
    Occupancy on the given dates; hours on other dates count as non-working day hours.
    With pending, days without entries before their logging deadline are pending rather than missing.
    """
    non_working_dates = non_working_dates or set()
    users = list(user_qs.order_by("display_name"))
    now = timezone.now()

    hours_qs = (
        TimeEntry.get_logged_qs()
        .filter(
            user__in=users,
            date__gte=start_date,
            date__lte=end_date,
        )
        .order_by()
        .annotate(created_date=TruncDate("created_at"))
        .values("user_id", "date")
        .annotate(
            total_minutes=models.Sum("duration"),
            entries=models.Count("id"),
            first_created_date=models.Min("created_date"),
            first_created_at=models.Min("created_at"),
            last_created_at=models.Max("created_at"),
        )
        .values_list(
            "user_id",
            "date",
            "total_minutes",
            "entries",
            "first_created_date",
            "first_created_at",
            "last_created_at",
        )
    )
    hours_map: dict[tuple[int, datetime.date], float] = {}
    entries_map = {}
    logging_lag_map = {}
    first_created_at_map = {}
    last_created_at_map = {}
    for (
        user_id,
        _date,
        total_minutes,
        entries,
        first_created_date,
        first_created_at,
        last_created_at,
    ) in hours_qs:
        hours_map[(user_id, _date)] = round(total_minutes / 60, 2)
        entries_map[(user_id, _date)] = entries
        logging_lag_map[(user_id, _date)] = (first_created_date - _date).days
        first_created_at_map[(user_id, _date)] = first_created_at
        last_created_at_map[(user_id, _date)] = last_created_at

    journal_qs = Journal.objects.filter(
        user__in=users,
        date__gte=start_date,
        date__lte=end_date,
    ).values_list("user_id", "date", "leave_type", "wfh_type")
    leave_map = {}
    work_from_home_map = {}
    # Inactive users are employed up to the last date with entries or a journal
    last_active_date_map: dict[int, datetime.date] = {}
    for user_id, _date in hours_map:
        last_active_date_map[user_id] = max(_date, last_active_date_map.get(user_id, _date))
    for user_id, _date, leave_type, wfh_type in journal_qs:
        last_active_date_map[user_id] = max(_date, last_active_date_map.get(user_id, _date))
        if leave_type is not None:
            leave_map[(user_id, _date)] = Journal.LeaveType(leave_type)
        if wfh_type is not None:
            work_from_home_map[(user_id, _date)] = Journal.WorkFromHomeType(wfh_type)

    deadline_search_end_date = end_date + datetime.timedelta(days=DEADLINE_SEARCH_DAYS)
    deadline_working_dates = get_working_dates(start_date + datetime.timedelta(days=1), deadline_search_end_date)
    full_leave_dates_map: dict[int, set[datetime.date]] = {}
    for user_id, _date in Journal.objects.filter(
        user__in=users,
        date__gt=start_date,
        date__lte=deadline_search_end_date,
        leave_type=Journal.LeaveType.FULL,
    ).values_list("user_id", "date"):
        full_leave_dates_map.setdefault(user_id, set()).add(_date)

    working_dates = set(dates)
    non_working_day_hours_map: dict[int, float] = {}
    non_working_day_entries_map: dict[int, int] = {}
    for (user_id, _date), hours in hours_map.items():
        if _date not in working_dates:
            non_working_day_hours_map[user_id] = non_working_day_hours_map.get(user_id, 0) + hours
            non_working_day_entries_map[user_id] = (
                non_working_day_entries_map.get(user_id, 0) + entries_map[(user_id, _date)]
            )

    users_occupancy = []
    for user in users:
        employed_from = timezone.localdate(user.date_joined)
        employed_until = end_date if user.is_active else last_active_date_map.get(user.pk)
        days = []
        for _date in dates:
            hours = hours_map.get((user.pk, _date))
            is_working_day = _date not in non_working_dates
            # Leave on a day off is not leave
            leave = leave_map.get((user.pk, _date)) if is_working_day else None
            is_employed = employed_until is not None and employed_from <= _date <= employed_until
            deadline = get_logging_deadline(_date, deadline_working_dates, full_leave_dates_map.get(user.pk, set()))
            first_created_at = first_created_at_map.get((user.pk, _date))
            days.append(
                UserDayOccupancy(
                    date=_date,
                    hours=hours,
                    leave=leave,
                    work_from_home=work_from_home_map.get((user.pk, _date)),
                    occupancy=calculate_occupancy(hours, leave),
                    entries=entries_map.get((user.pk, _date), 0),
                    expected_hours=get_expected_hours(leave) if is_employed and is_working_day else 0,
                    is_working_day=is_working_day,
                    logging_lag=logging_lag_map.get((user.pk, _date)),
                    is_logged_late=first_created_at is not None and first_created_at >= deadline,
                    is_logged_during_standup=(
                        first_created_at is not None and deadline <= first_created_at < deadline + STANDUP_DURATION
                    ),
                    is_pending=with_pending and now < deadline,
                    last_created_at=last_created_at_map.get((user.pk, _date)),
                ),
            )
        users_occupancy.append(
            UserOccupancy(
                user=user,
                days=days,
                non_working_day_hours=non_working_day_hours_map.get(user.pk, 0),
                non_working_day_entries=non_working_day_entries_map.get(user.pk, 0),
            ),
        )

    return Occupancy(
        start_date=start_date,
        end_date=end_date,
        dates=dates,
        users=users_occupancy,
        non_working_dates=non_working_dates,
    )
