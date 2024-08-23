import datetime
import functools

from django.db import models
from django.utils import timezone

from apps.user.models import User


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


# -- Common models
class Event(UserResource):
    class Type(models.IntegerChoices):
        HOLIDAY = 1, "Holiday"
        RETREAT = 2, "Retreat"
        MISC = 3, "Misc"

    name = models.CharField(max_length=225)
    type = models.PositiveSmallIntegerField(choices=Type.choices, default=Type.HOLIDAY)

    start_date = models.DateField()
    end_date = models.DateField()

    @staticmethod
    def is_weekend(date: datetime.date):
        return date.weekday() > 4  # 5 Sat, 6 Su

    def get_dates(self, include_weekends=False) -> list[datetime.date]:
        if self.start_date == self.end_date:
            if not include_weekends and self.is_weekend(self.start_date):
                return []
            return [self.start_date]

        dates = []
        for x in range((self.end_date - self.start_date).days):
            date = self.start_date + datetime.timedelta(days=x)
            if not include_weekends and self.is_weekend(date):
                continue
            dates.append(date)
        return sorted(set(dates))

    @classmethod
    def get_last_working_date(
        cls,
        now_date: datetime.date,
        offset_count: int | None = None,
    ) -> datetime.date:  # type: ignore[reportReturnType]
        # TODO: Add test
        event_dates = set(cls.get_relative_event_dates())
        found_count = 0
        for x in range(30):  # Create a 1 month window, Should be enough
            date = now_date - datetime.timedelta(days=x)
            if cls.is_weekend(date) or date in event_dates:
                continue
            if offset_count is not None and found_count < offset_count:
                found_count += 1
                continue
            return date

    @classmethod
    def get_relative_events(cls) -> models.QuerySet["Event"]:
        """
        Return list of dates with holiday relative to current date
        """
        # TODO: Add test
        now = timezone.now().date()
        start_threshold = now - datetime.timedelta(days=200)
        end_threshold = now + datetime.timedelta(days=200)
        return cls.objects.filter(start_date__gte=start_threshold, end_date__lte=end_threshold)

    @classmethod
    @functools.cache
    def get_relative_event_dates(cls) -> list[datetime.date]:
        """
        Return list of dates with holiday relative to current date
        """
        dates = []

        qs = cls.get_relative_events()
        for start_date, end_date in qs.values_list("start_date", "end_date"):
            if start_date == end_date:
                dates.append(start_date)
                continue

            for x in range((end_date - start_date).days):
                dates.append(start_date + datetime.timedelta(days=x))

        return sorted(set(dates))
