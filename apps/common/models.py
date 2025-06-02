import datetime
import typing

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.user.models import User
from main.caches import CacheKey


# -- Abstracts
class UserResource(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        related_name="%(class)s_created",
        on_delete=models.PROTECT,
    )
    modified_by = models.ForeignKey(
        User,
        related_name="%(class)s_modified",
        on_delete=models.PROTECT,
    )

    # Typing
    id: int
    pk: int
    created_by_id: int
    modified_by_id: int

    class Meta:  # type: ignore[reportIncompatibleVariableOverride]
        abstract = True
        ordering = ["-id"]


NotArchivedFilterIndex = models.Index(
    fields=["is_archived"],
    name="%(app_label)s_%(class)s_active_idx",
    condition=models.Q(is_archived=False),
)


# -- Common models
class Event(UserResource):
    class Type(models.IntegerChoices):
        HOLIDAY = 1, "Holiday"
        RETREAT = 2, "Retreat"
        MISC = 3, "Misc"

        __NON_WORKING__ = [
            HOLIDAY[0],
            RETREAT[0],
        ]

    class GoogleCalendarSyncStatus(models.IntegerChoices):
        PENDING = 1, "Pending"
        SUCCESS = 2, "Success"
        FAILURE = 3, "Failure"

    name = models.CharField(max_length=225)
    description = models.TextField(blank=True)
    type = models.PositiveSmallIntegerField(choices=Type.choices, default=Type.HOLIDAY)

    # Google calendar
    google_calendar_sync_status = models.PositiveSmallIntegerField(
        choices=GoogleCalendarSyncStatus.choices,
        default=GoogleCalendarSyncStatus.PENDING,
    )
    google_calendar_event_id = models.CharField(null=True, blank=True)
    google_calendar_html_link = models.URLField(null=True, blank=True)

    start_date = models.DateField()
    end_date = models.DateField()

    # type hints
    get_type_display: typing.Callable[..., str]
    get_google_calendar_sync_status_display: typing.Callable[..., str]

    @typing.override
    def __str__(self):
        return f"{self.name} - {self.get_type_display()}"

    @typing.override
    def save(self, *args, **kwargs):
        self.reload_cache()
        return super().save(*args, **kwargs)

    @typing.override
    def delete(self, *args, **kwargs):
        from apps.common.tasks import delete_event_from_google_calendar

        self.reload_cache()
        # TODO(thenav56): Make this async with celery
        delete_event_from_google_calendar(self)
        return super().delete(*args, **kwargs)

    @classmethod
    def reload_cache(cls):
        # Delete
        cache.delete(CacheKey.TIMUR_EVENT_DATES)
        # Generate cache
        cls.get_relative_event_dates()

    def dates_check(self):
        if self.start_date > self.end_date:
            raise ValidationError(_("Start date can't be greater then End date"))

    @typing.override
    def clean(self):
        super().clean()
        self.dates_check()

    @staticmethod
    def is_weekend(date: datetime.date):
        return date.weekday() > 4  # 5 Sat, 6 Su

    @classmethod
    def generate_dates(
        cls,
        start_date: datetime.date,
        end_date: datetime.date,
        include_holidays=False,
        include_weekends=False,
    ) -> list[datetime.date]:
        if start_date == end_date:
            if not include_weekends and cls.is_weekend(start_date):
                return []
            return [start_date]

        dates = []
        for x in range((end_date - start_date).days + 1):
            date = start_date + datetime.timedelta(days=x)
            if not include_weekends and cls.is_weekend(date):
                continue
            if not include_holidays and date in cls.get_relative_event_dates():
                continue
            dates.append(date)
        return sorted(set(dates))

    def get_dates(self, include_weekends=False, include_holidays=True) -> list[datetime.date]:
        return self.generate_dates(
            self.start_date,
            self.end_date,
            include_weekends=include_weekends,
            include_holidays=include_holidays,
        )

    @classmethod
    def get_last_working_date(
        cls,
        now_date: datetime.date,
        skip_dates: list[datetime.date] | None = None,
        offset_count: int | None = None,
    ) -> datetime.date:  # type: ignore[reportReturnType]
        # TODO: Add test
        dates_to_skip = set(cls.get_relative_event_dates())
        if skip_dates:
            dates_to_skip.update(skip_dates)
        found_count = 0
        for x in range(30):  # Create a 1 month window, Should be enough
            date = now_date - datetime.timedelta(days=x)
            if cls.is_weekend(date) or date in dates_to_skip:
                continue
            if offset_count is not None and found_count < offset_count:
                found_count += 1
                continue
            return date
        return timezone.now()  # XXX: Fallback to now

    @classmethod
    @sync_to_async
    def aget_last_working_date(
        cls,
        now_date: datetime.date,
        skip_dates: list[datetime.date] | None = None,
        offset_count: int | None = None,
    ) -> datetime.date:  # type: ignore[reportReturnType]
        return cls.get_last_working_date(now_date, skip_dates=skip_dates, offset_count=offset_count)

    @classmethod
    def get_next_working_date(
        cls,
        now_date: datetime.date,
        skip_dates: list[datetime.date] | None = None,
        offset_count: int | None = None,
    ) -> datetime.date:  # type: ignore[reportReturnType]
        # TODO: Add test
        dates_to_skip = set(cls.get_relative_event_dates())
        if skip_dates:
            dates_to_skip.update(skip_dates)
        found_count = 0
        for x in range(30):  # Create a 1 month window, Should be enough
            date = now_date + datetime.timedelta(days=x)
            if cls.is_weekend(date) or date in dates_to_skip:
                continue
            if offset_count is not None and found_count < offset_count:
                found_count += 1
                continue
            return date
        return timezone.now()  # XXX: Fallback to now

    @classmethod
    def get_relative_non_working_events(cls) -> models.QuerySet["Event"]:
        """
        Return list of dates with holiday relative to current date
        """
        # TODO: Add test
        now = timezone.now().date()
        start_threshold = now - datetime.timedelta(days=200)
        end_threshold = now + datetime.timedelta(days=200)
        return cls.objects.filter(
            type__in=cls.Type.__NON_WORKING__,
            start_date__gte=start_threshold,
            end_date__lte=end_threshold,
        )

    @classmethod
    def get_relative_event_dates(cls) -> list[datetime.date]:
        """
        Return list of dates with holiday relative to current date
        """
        if cached_value := cache.get(CacheKey.TIMUR_EVENT_DATES):
            return cached_value

        dates = []
        qs = cls.get_relative_non_working_events()
        for start_date, end_date in qs.values_list("start_date", "end_date"):
            if start_date == end_date:
                dates.append(start_date)
                continue

            for x in range((end_date - start_date).days + 1):
                dates.append(start_date + datetime.timedelta(days=x))

        sorted_dates = sorted(set(dates))
        cache.set(CacheKey.TIMUR_EVENT_DATES, sorted_dates, 3600)  # Cache for 1hr
        return sorted_dates

    @classmethod
    @sync_to_async
    def aget_relative_event_dates(cls) -> list[datetime.date]:
        """
        Return list of dates with holiday relative to current date
        """
        return cls.get_relative_event_dates()

    @classmethod
    def get_working_days_count(
        cls,
        start_date: datetime.date,
        end_date: datetime.date,
        include_weekends: bool = False,
        include_holidays: bool = False,
    ) -> int:
        """
        Return number of working days excluding weekends and holidays
        """
        return len(
            cls.generate_dates(
                start_date,
                end_date,
                include_weekends=include_weekends,
                include_holidays=include_holidays,
            ),
        )

    @classmethod
    @sync_to_async
    def aget_working_days_count(
        cls,
        start_date: datetime.date,
        end_date: datetime.date,
        include_weekends: bool = False,
        include_holidays: bool = False,
    ) -> int:
        """
        Return number of working days excluding weekends and holidays
        """
        return cls.get_working_days_count(
            start_date,
            end_date,
            include_weekends=include_weekends,
            include_holidays=include_holidays,
        )
