import datetime

import strawberry
import strawberry_django
from django.db.models import Sum
from strawberry_django.filters import apply as apply_filters

from main.graphql.context import Info
from utils.strawberry.paginations import CountList, pagination_field

# from .models import TimeEntry
# from .enums import TimeEntryDateFilterEnum
from .filters import ContractFilter, TaskFilter, TimeEntryFilter
from .orders import ContractOrder, TaskOrder, TimeEntryOrder
from .types import ContractType, DailySummaryType, TaskType, TimeEntryType

# from django.db import models


# TODO: Remove
# async def custom_time_entries_filters_apply(
#     queryset: models.QuerySet[TimeEntry],
#     date_gte: TimeEntryDateFilterEnum | None,
#     date_lte: TimeEntryDateFilterEnum | None,
# ) -> models.QuerySet:
#     if date_gte:
#         date_gte_value = await TimeEntryDateFilterEnum.resolve_value(date_gte)
#         queryset = queryset.filter(date__gte=date_gte_value)
#     if date_lte:
#         date_lte_value = await TimeEntryDateFilterEnum.resolve_value(date_lte)
#         queryset = queryset.filter(date__lte=date_lte_value)
#     return queryset


@strawberry.type
class PrivateQuery:
    # Paginated ----------------------------
    contracts: CountList[ContractType] = pagination_field(
        pagination=True,
        filters=ContractFilter,
        order=ContractOrder,
    )

    tasks: CountList[TaskType] = pagination_field(
        pagination=True,
        filters=TaskFilter,
        order=TaskOrder,
    )

    time_entries: CountList[TimeEntryType] = pagination_field(
        pagination=True,
        filters=TimeEntryFilter,
        order=TimeEntryOrder,
    )

    # Unbounded ----------------------------
    @strawberry_django.field(description="Return all UnArchived contracts")
    async def all_active_contracts(self, info: Info) -> list[ContractType]:
        qs = ContractType.get_queryset(None, None, info).filter(is_archived=False).order_by("-id")
        return [contract async for contract in qs]

    @strawberry_django.field(description="Return all UnArchived tasks")
    async def all_active_tasks(self, info: Info) -> list[TaskType]:
        qs = TaskType.get_queryset(None, None, info).filter(is_archived=False, contract__is_archived=False).order_by("-id")
        return [task async for task in qs]

    @strawberry_django.field
    async def my_time_entries(self, info: Info, date: datetime.date) -> list[TimeEntryType]:
        qs = (
            TimeEntryType.get_queryset(None, None, info)
            .filter(
                date=date,
                user=info.context.request.user,
            )
            .order_by("-id")
        )
        return [time_entry async for time_entry in qs]

    @strawberry_django.field
    async def all_time_entries(
        self,
        info: Info,
        filters: TimeEntryFilter,
        # date_gte: TimeEntryDateFilterEnum | None = None,  # type: ignore[reportInvalidTypeForm]
        # date_lte: TimeEntryDateFilterEnum | None = None,  # type: ignore[reportInvalidTypeForm]
    ) -> list[TimeEntryType]:
        queryset = TimeEntryType.get_queryset(None, None, info)
        queryset = apply_filters(filters, queryset, info, None)
        # queryset = await custom_time_entries_filters_apply(queryset, date_gte, date_lte)
        count = await queryset.acount()
        if count > 3000:  # TODO: Is this fine?
            raise Exception(f"Try using filters. To much data to return (Row count: {count})")
        return [time_entry async for time_entry in queryset]

    @strawberry_django.field(
        description="Return total minutes and target minutes per day for the user within the given date range.",
    )
    async def daily_summary(
        self,
        info: Info,
        date_gte: datetime.date,
        date_lte: datetime.date,
    ) -> list[DailySummaryType]:
        from apps.common.models import Event
        from apps.journal.models import Journal

        from .models import TimeEntry

        # Recorded minutes per date
        qs = (
            TimeEntry.objects.filter(
                user=info.context.request.user,
                date__gte=date_gte,
                date__lte=date_lte,
            )
            .values("date")
            .annotate(total_minutes=Sum("duration"))
            .order_by("date")
        )
        recorded: dict[datetime.date, int] = {}
        async for row in qs:
            recorded[row["date"]] = row["total_minutes"] or 0

        # Holiday / non-working event dates (cached)
        from asgiref.sync import sync_to_async

        holiday_dates = set(await sync_to_async(Event.get_relative_event_dates)())

        # User journal entries (leave + wfh) in range
        journal_qs = Journal.objects.filter(
            user=info.context.request.user,
            date__gte=date_gte,
            date__lte=date_lte,
        ).values("date", "leave_type", "wfh_type")
        journal_map: dict[datetime.date, dict] = {}
        async for row in journal_qs:
            journal_map[row["date"]] = row

        # Build one entry per day in the range
        result = []
        total_days = (date_lte - date_gte).days + 1
        for offset in range(total_days):
            date = date_gte + datetime.timedelta(days=offset)
            journal = journal_map.get(date, {})
            leave_type = journal.get("leave_type")
            wfh_type = journal.get("wfh_type")
            is_holiday = not Event.is_weekend(date) and date in holiday_dates

            if Event.is_weekend(date) or date in holiday_dates or leave_type == Journal.LeaveType.FULL:
                target = 0
            elif leave_type in (Journal.LeaveType.FIRST_HALF, Journal.LeaveType.SECOND_HALF):
                target = 240
            else:
                target = 480
            result.append(
                DailySummaryType(
                    date=date,
                    total_minutes=recorded.get(date, 0),
                    target_minutes=target,
                    is_holiday=is_holiday,
                    leave_type=leave_type,
                    wfh_type=wfh_type,
                ),
            )
        return result

    # Single ----------------------------
    @strawberry_django.field
    async def contract(self, info: Info, pk: strawberry.ID) -> ContractType | None:
        return await ContractType.get_queryset(None, None, info).filter(pk=pk).afirst()

    @strawberry_django.field
    async def task(self, info: Info, pk: strawberry.ID) -> TaskType | None:
        return await TaskType.get_queryset(None, None, info).filter(pk=pk).afirst()
