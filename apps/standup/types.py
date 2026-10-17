import dataclasses
import datetime
import typing

import strawberry
import strawberry_django
from asgiref.sync import sync_to_async
from django.db import models

from apps.common.models import Event
from apps.common.types import EventType, UserResourceTypeMixin
from apps.journal.enums import JournalLeaveTypeEnum, JournalWorkFromHomeTypeEnum
from apps.project.models import Project
from apps.project.types import ProjectType
from apps.standup.history import PERSON_HISTORY_MONTHS, get_person_history
from apps.standup.models import DailyUserStandup, Quote
from apps.standup.occupancy import (
    BLANKET_PROJECT_NAME,
    LOGGING_DEADLINE,
    LONG_DAY_HOURS,
    LONG_ENTRY_HOURS,
    STANDUP_DURATION,
    VAGUE_DESCRIPTION_WORDS,
    VAGUE_SHORT_DESCRIPTION_HOURS,
    VAGUE_SHORT_DESCRIPTION_WORDS,
    FlaggedEntry,
    Occupancy,
    OccupancySummary,
    UserDayOccupancy,
    UserOccupancy,
    get_range_occupancy,
    get_standup_occupancy,
)
from apps.track.models import TimeEntry
from apps.user.models import User
from apps.user.types import UserType
from main.graphql.context import Info
from utils.common import get_queryset_for_model
from utils.strawberry.types import string_field


@strawberry_django.type(Quote)
class QuoteType(UserResourceTypeMixin):
    id: strawberry.ID

    text = string_field(Quote.text)
    author = string_field(Quote.author)

    @staticmethod
    def get_queryset(_, queryset: models.QuerySet | None, info: Info):
        return get_queryset_for_model(Quote, queryset)


@strawberry.type
class DailyStandUpProjectStatUserType:
    user_obj: strawberry.Private[User]
    date: strawberry.Private[datetime.date]

    id: strawberry.ID  # TODO: Use key for auto computed IDs
    last_active_date: datetime.date

    @strawberry.field(deprecation_reason="Use user.display_picture instead")
    def display_picture(self) -> str | None:
        return self.user_obj.display_picture

    @strawberry.field(deprecation_reason="Use user.display_name instead")
    def display_name(self) -> str:
        return self.user_obj.display_name

    @strawberry.field
    def user(self) -> UserType:
        return self.user_obj  # type: ignore[reportReturnType]

    @strawberry.field
    async def leave(self, info: Info) -> JournalLeaveTypeEnum | None:  # type: ignore[reportInvalidTypeForm]
        return await info.context.dl.journal.load_user_leave.load((self.user_obj.pk, self.date))

    @strawberry.field
    async def work_from_home(self, info: Info) -> JournalWorkFromHomeTypeEnum | None:  # type: ignore[reportInvalidTypeForm]
        return await info.context.dl.journal.load_user_work_from_home.load((self.user_obj.pk, self.date))


@strawberry.type
class DailyStandUpProjectStatType:
    id: strawberry.ID
    project_obj: strawberry.Private[Project]
    date: strawberry.Private[datetime.date]

    async def _check_activity_from_date(self) -> datetime.date:
        return await Event.aget_last_working_date(now_date=self.date, offset_count=1)

    @strawberry.field
    async def last_working_date(self) -> datetime.date:
        return await Event.aget_last_working_date(now_date=self.date)

    # XXX: For debugging only
    @strawberry.field
    async def activity_from_date(self) -> datetime.date:
        return await self._check_activity_from_date()

    @strawberry.field
    def project(self) -> ProjectType:
        return self.project_obj  # type: ignore[reportReturnType]

    @strawberry.field
    async def users(self) -> list[DailyStandUpProjectStatUserType]:
        activity_from_date = await self._check_activity_from_date()
        time_entries_qs = (
            TimeEntry.objects.filter(
                (
                    models.Q(
                        date__gte=activity_from_date,
                        date__lt=self.date,
                        status__in=[TimeEntry.Status.DOING, TimeEntry.Status.DONE],
                    )
                    | models.Q(date=self.date)
                ),
                task__contract__project=self.project_obj,
            )
            .order_by()
            .values("user")
            .annotate(
                active_date=models.Max("date"),
            )
            .values_list("user", "active_date")
        )

        time_entries_user_active_date_map = {user_id: active_date async for user_id, active_date in time_entries_qs}

        users_qs = (
            User.get_standup_slide_user_qs()
            .filter(
                id__in=time_entries_user_active_date_map.keys(),
            )
            .order_by("display_name")
        )

        return [
            DailyStandUpProjectStatUserType(
                user_obj=user,
                date=self.date,
                last_active_date=time_entries_user_active_date_map[user.pk],
                id=strawberry.ID(f"{user.pk}-{self.project_obj.pk}-{self.date.isoformat()}"),
            )
            async for user in users_qs.all()
        ]


@strawberry.type
class DailyStandUpOccupancyUserDayType:
    date: datetime.date
    hours: float | None
    leave: JournalLeaveTypeEnum | None  # type: ignore[reportInvalidTypeForm]
    work_from_home: JournalWorkFromHomeTypeEnum | None  # type: ignore[reportInvalidTypeForm]
    occupancy: float | None
    entries: int
    expected_hours: float = strawberry.field(description="Zero before the user joined and after an inactive user left")
    late_by_days: int | None = strawberry.field(
        default=None,
        description="Days from a working day to the creation of its first entry, when that is after "
        f"{LOGGING_DEADLINE:%H:%M} on the person's next working day",
    )
    logged_during_standup: bool = strawberry.field(
        default=False,
        description=f"The first entry of a working day was created during the {STANDUP_DURATION.seconds // 60} minutes "
        "of the standup, from the deadline",
    )
    is_pending: bool = strawberry.field(
        default=False,
        description="Before the deadline, so a day without entries is pending rather than missing",
    )

    @strawberry.field
    def leave_display(self) -> str | None:
        return self.leave.label if self.leave else None


@strawberry.type
class DailyStandUpOccupancyUserType:
    user_obj: strawberry.Private[User]

    id: strawberry.ID
    days: list[DailyStandUpOccupancyUserDayType]

    @strawberry.field
    def user(self) -> UserType:
        return self.user_obj  # type: ignore[reportReturnType]


@strawberry.type
class DailyStandUpOccupancyType:
    id: strawberry.ID
    start_date: datetime.date
    end_date: datetime.date
    dates: list[datetime.date]
    users: list[DailyStandUpOccupancyUserType]


@strawberry.type
class OccupancySummaryType:
    hours: float
    expected_hours: float
    occupancy: float | None
    leave_days: float = strawberry.field(description="Days of leave, with a half day of leave counted as half")
    work_from_home_days: float
    missing_days: int
    missing_share: float | None = strawberry.field(description="Missing days as a share of the due days")
    entries: int
    non_working_day_hours: float = strawberry.field(description="Hours logged on weekends, holidays and retreats")
    on_leave_hours: float = strawberry.field(description="Hours logged on days of full leave")
    due_days: int = strawberry.field(
        description=f"Days with hours expected, past their deadline of {LOGGING_DEADLINE:%H:%M} on the person's "
        "next working day",
    )
    late_days: int = strawberry.field(
        description="Due days whose first entry was created after the deadline. Days without hours are missing, not late.",
    )
    late_share: float | None = strawberry.field(description="Late days as a share of the due days")
    standup_days: int = strawberry.field(description="Due days whose first entry was created during the standup")
    standup_share: float | None = strawberry.field(description="Standup days as a share of the due days")
    leave_conflict_days: int = strawberry.field(description="Days of full leave with hours logged")
    projects_per_day: float | None = strawberry.field(
        description=f"Projects per day with hours, other than {BLANKET_PROJECT_NAME}",
    )
    long_entries: int = strawberry.field(description=f"Entries with {LONG_ENTRY_HOURS} hours or more")
    long_entry_share: float | None = strawberry.field(description="Hours of long entries as a share of the hours")
    vague_entries: int = strawberry.field(description="Logged entries with a vague description")
    vague_entry_share: float | None = strawberry.field(description="Vague entries as a share of the entries")


@strawberry.type
class OccupancyDaySummaryType:
    date: datetime.date
    is_working_day: bool
    event_name: str | None = strawberry.field(description="Names of the holidays and retreats on the day")
    summary: OccupancySummaryType


@strawberry.type
class OccupancyProjectHoursType:
    project: ProjectType
    hours: float
    share: float | None = strawberry.field(description="Share of the hours the person logged within the range")


@strawberry.type
class OccupancyEntryType:
    id: strawberry.ID
    date: datetime.date
    hours: float
    description: str
    project: ProjectType
    task_name: str
    is_long: bool = strawberry.field(description=f"Logged with {LONG_ENTRY_HOURS} hours or more")
    is_vague: bool = strawberry.field(
        description=f"Logged with a description of at most {VAGUE_DESCRIPTION_WORDS} word, or of at most "
        f"{VAGUE_SHORT_DESCRIPTION_WORDS} words with {VAGUE_SHORT_DESCRIPTION_HOURS} hours or more",
    )


@strawberry.type
class OccupancyUserType(DailyStandUpOccupancyUserType):
    summary: OccupancySummaryType
    long_dates: list[datetime.date] = strawberry.field(
        description=f"Dates with more than {LONG_DAY_HOURS} hours logged",
    )
    projects: list[OccupancyProjectHoursType] = strawberry.field(
        description="Hours per project, most hours first, then the latest activity",
    )
    top_project: OccupancyProjectHoursType | None = strawberry.field(
        description=f"The project with the most hours other than {BLANKET_PROJECT_NAME}, "
        f"with its share of the hours outside {BLANKET_PROJECT_NAME}",
    )
    flagged_entries: list[OccupancyEntryType] = strawberry.field(
        description="Long and vague entries, by date",
    )


@strawberry.type
class OccupancyPeriodType:
    start_date: datetime.date
    end_date: datetime.date
    summary: OccupancySummaryType
    missing_people: int


@strawberry.type
class OccupancyType:
    id: strawberry.ID
    start_date: datetime.date
    end_date: datetime.date
    dates: list[datetime.date]
    users: list[OccupancyUserType]
    summary: OccupancySummaryType
    missing_people: int = strawberry.field(description="People with at least one missing day")
    previous: OccupancyPeriodType = strawberry.field(
        description="The same days of the previous month, or all of it for a range up to the end of a month, "
        "for the same people",
    )
    day_summaries: list[OccupancyDaySummaryType]
    misc_events: list[EventType]
    data_as_of: datetime.datetime | None = strawberry.field(
        description="When the latest entry within the range was created",
    )


@strawberry.type
class OccupancyMonthType:
    start_date: datetime.date
    hours: float
    expected_hours: float
    occupancy: float | None
    late_share: float | None = strawberry.field(description="Late days as a share of the due days")
    leave_days: float = strawberry.field(description="Leave on working days, with a half day counted as half")
    work_from_home_days: float = strawberry.field(description="WFH on working days, with a half day counted as half")


@strawberry.type
class OccupancyPersonType:
    id: strawberry.ID
    months: list[OccupancyMonthType] = strawberry.field(
        description=f"The {PERSON_HISTORY_MONTHS} months up to the end date, oldest first",
    )
    leave_days_this_year: float = strawberry.field(
        description="Leave on working days from the start of the year up to the end date, with a half day counted as half",
    )


def get_occupancy_user_days(days: list[UserDayOccupancy]) -> list[DailyStandUpOccupancyUserDayType]:
    return [
        DailyStandUpOccupancyUserDayType(
            date=day.date,
            hours=day.hours,
            leave=day.leave,
            work_from_home=day.work_from_home,
            occupancy=day.occupancy,
            entries=day.entries,
            expected_hours=day.expected_hours,
            late_by_days=day.late_by_days,
            logged_during_standup=day.logged_during_standup,
            is_pending=day.is_pending,
        )
        for day in days
    ]


def get_occupancy_summary(summary: OccupancySummary) -> OccupancySummaryType:
    return OccupancySummaryType(**dataclasses.asdict(summary))


def get_occupancy_user(
    user_occupancy: UserOccupancy,
    summary: OccupancySummary,
    key: str,
    projects_by_id: dict[int, Project],
) -> OccupancyUserType:
    return OccupancyUserType(
        id=strawberry.ID(f"{user_occupancy.user.pk}-{key}"),
        user_obj=user_occupancy.user,
        days=get_occupancy_user_days(user_occupancy.days),
        summary=get_occupancy_summary(summary),
        long_dates=user_occupancy.long_dates,
        projects=[
            OccupancyProjectHoursType(
                project=projects_by_id[item.project_id],  # type: ignore[reportArgumentType]
                hours=item.hours,
                share=round(item.hours / summary.hours, 4) if summary.hours else None,
            )
            for item in user_occupancy.projects
        ],
        flagged_entries=[get_occupancy_entry(entry, projects_by_id) for entry in user_occupancy.flagged_entries],
        top_project=get_top_project(user_occupancy, projects_by_id),
    )


def get_top_project(user_occupancy: UserOccupancy, projects_by_id: dict[int, Project]) -> OccupancyProjectHoursType | None:
    if user_occupancy.top_project is None:
        return None
    item, share = user_occupancy.top_project
    return OccupancyProjectHoursType(
        project=projects_by_id[item.project_id],  # type: ignore[reportArgumentType]
        hours=item.hours,
        share=share,
    )


def get_occupancy_entry(entry: FlaggedEntry, projects_by_id: dict[int, Project]) -> OccupancyEntryType:
    return OccupancyEntryType(
        id=strawberry.ID(str(entry.id)),
        date=entry.date,
        hours=entry.hours,
        description=entry.description,
        project=projects_by_id[entry.project_id],  # type: ignore[reportArgumentType]
        task_name=entry.task_name,
        is_long=entry.is_long,
        is_vague=entry.is_vague,
    )


async def aget_occupancy_person_type(user_id: int, end_date: datetime.date) -> OccupancyPersonType | None:
    history = await sync_to_async(get_person_history)(user_id, end_date)
    if history is None:
        return None
    return OccupancyPersonType(
        id=strawberry.ID(f"{user_id}-{end_date.isoformat()}"),
        months=[
            OccupancyMonthType(
                start_date=month.start_date,
                hours=month.hours,
                expected_hours=month.capacity_hours,
                occupancy=month.occupancy,
                late_share=month.late_share,
                leave_days=month.leave_days,
                work_from_home_days=month.work_from_home_days,
            )
            for month in history.months
        ],
        leave_days_this_year=history.leave_days_this_year,
    )


async def aget_occupancy_type(
    start_date: datetime.date,
    end_date: datetime.date,
) -> OccupancyType:
    occupancy = await sync_to_async(get_range_occupancy)(start_date, end_date)
    previous = typing.cast("Occupancy", occupancy.previous)
    projects_by_id = {
        project.pk: project
        async for project in Project.objects.filter(
            pk__in={
                *(item.project_id for user_occupancy in occupancy.users for item in user_occupancy.projects),
                *(entry.project_id for user_occupancy in occupancy.users for entry in user_occupancy.flagged_entries),
            },
        )
    }
    misc_events_qs = Event.objects.filter(
        type=Event.Type.MISC,
        start_date__lte=end_date,
        end_date__gte=start_date,
    ).order_by("start_date")
    key = f"{occupancy.start_date.isoformat()}-{occupancy.end_date.isoformat()}"
    return OccupancyType(
        id=strawberry.ID(key),
        start_date=occupancy.start_date,
        end_date=occupancy.end_date,
        dates=occupancy.dates,
        users=[
            get_occupancy_user(user_occupancy, user_occupancy.summary, key, projects_by_id)
            for user_occupancy in occupancy.users
        ],
        summary=get_occupancy_summary(occupancy.summary),
        missing_people=occupancy.missing_people,
        previous=OccupancyPeriodType(
            start_date=previous.start_date,
            end_date=previous.end_date,
            summary=get_occupancy_summary(previous.summary),
            missing_people=previous.missing_people,
        ),
        day_summaries=[
            OccupancyDaySummaryType(
                date=date,
                is_working_day=date not in occupancy.non_working_dates,
                event_name=occupancy.event_names.get(date),
                summary=get_occupancy_summary(summary),
            )
            for date, summary in zip(occupancy.dates, occupancy.day_summaries, strict=True)
        ],
        misc_events=[event async for event in misc_events_qs],  # type: ignore[reportArgumentType]
        data_as_of=occupancy.data_as_of,
    )


@strawberry_django.type(DailyUserStandup)
class DailyStandUpType:
    id: strawberry.ID
    date: strawberry.auto

    @strawberry_django.field
    async def conductor(self, standup: strawberry.Parent[DailyUserStandup], info: Info) -> UserType | None:
        if standup.conductor_id:
            return await info.context.dl.user.load_user.load(standup.conductor_id)
        return None

    @strawberry_django.field
    async def fallback_conductor(self, standup: strawberry.Parent[DailyUserStandup], info: Info) -> UserType | None:
        if standup.fallback_conductor_id:
            return await info.context.dl.user.load_user.load(standup.fallback_conductor_id)
        return None

    @strawberry.field
    async def quote(
        self,
        standup: strawberry.Parent[DailyUserStandup],
    ) -> QuoteType | None:
        @sync_to_async
        def _get_quote(standup):
            return standup.quote

        if standup.quote_id:
            return await _get_quote(standup)

        # As fallback return a random quote
        return typing.cast(
            "QuoteType",
            await sync_to_async(Quote.get_random)(track_last_viewed=True),
        )

    @strawberry.field
    async def project_stat(
        self,
        info: Info,
        standup: strawberry.Parent[DailyUserStandup],
        pk: strawberry.ID,
    ) -> DailyStandUpProjectStatType | None:
        project = await ProjectType.get_queryset(None, None, info).filter(pk=pk).afirst()
        if project:
            return DailyStandUpProjectStatType(
                id=strawberry.ID(f"{project.pk}-{standup.date.isoformat()}"),
                project_obj=project,
                date=standup.date,
            )
        return None

    @strawberry.field
    async def occupancy(
        self,
        standup: strawberry.Parent[DailyUserStandup],
    ) -> DailyStandUpOccupancyType:
        occupancy = await sync_to_async(get_standup_occupancy)(standup.date)
        return DailyStandUpOccupancyType(
            id=strawberry.ID(standup.date.isoformat()),
            start_date=occupancy.start_date,
            end_date=occupancy.end_date,
            dates=occupancy.dates,
            users=[
                DailyStandUpOccupancyUserType(
                    id=strawberry.ID(f"{user_occupancy.user.pk}-{standup.date.isoformat()}"),
                    user_obj=user_occupancy.user,
                    days=get_occupancy_user_days(user_occupancy.days),
                )
                for user_occupancy in occupancy.users
            ],
        )
