import datetime
import typing

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.user.models import User


class Journal(models.Model):
    class LeaveType(models.IntegerChoices):
        FULL = 1, _("Full")
        FIRST_HALF = 2, _("First Half")
        SECOND_HALF = 3, _("Second Half")

    class WorkFromHomeType(models.IntegerChoices):
        FULL = 1, _("Full")
        FIRST_HALF = 2, _("First Half")
        SECOND_HALF = 3, _("Second Half")

    VALID_LEAVE_WFH_COMBINATION = set(
        [
            # -- FULL
            (LeaveType.FULL, None),
            (None, WorkFromHomeType.FULL),
            # -- FH
            (LeaveType.FIRST_HALF, None),
            (LeaveType.FIRST_HALF, WorkFromHomeType.SECOND_HALF),
            (None, WorkFromHomeType.FIRST_HALF),
            # -- SH
            (LeaveType.SECOND_HALF, None),
            (LeaveType.SECOND_HALF, WorkFromHomeType.FIRST_HALF),
            (None, WorkFromHomeType.SECOND_HALF),
        ],
    )

    user = models.ForeignKey(User, related_name="+", on_delete=models.PROTECT)
    date = models.DateField()

    leave_type = models.PositiveSmallIntegerField(null=True, blank=True, choices=LeaveType.choices)
    wfh_type = models.PositiveSmallIntegerField(null=True, blank=True, choices=WorkFromHomeType.choices)

    journal_text = models.TextField(blank=True)

    user_id: int

    class Meta:  # type: ignore[reportIncompatibleVariableOverride]
        unique_together = ("user", "date")
        indexes = [
            models.Index(fields=["date"]),
        ]

    @typing.override
    def __str__(self):
        return f"{self.user_id}#{self.date}"

    @classmethod
    def as_leave_qs(cls, recent_only=False) -> models.QuerySet["Journal"]:
        """
        Return a Journal queryset with pre-applied leave filters
        """
        qs = Journal.objects.filter(
            leave_type__in=[
                Journal.LeaveType.FULL,
                Journal.LeaveType.FIRST_HALF,
            ],
        )
        if recent_only:
            return qs.filter(date__gte=timezone.now() - datetime.timedelta(days=30))
        return qs

    def leave_wfh_check(self):
        # Make sure leave_type and wfh_type don't conflict with each other
        if (
            self.leave_type is not None
            and self.wfh_type is not None
            and (self.leave_type, self.wfh_type) not in self.VALID_LEAVE_WFH_COMBINATION
        ):
            raise ValidationError(_("Provided Leave and Work from home combination is invalid"))

    @typing.override
    def clean(self):
        super().clean()
        self.leave_wfh_check()


class JournalAvailabilityHistory(models.Model):
    """
    A change of a journal's leave/WFH values

    Only changes of leave_type or wfh_type are recorded.
    """

    class Source(models.IntegerChoices):
        MANUAL = 1, _("Manual")
        SLACK_TIMUR = 2, _("Timur from Slack")
        ADMIN = 3, _("Django admin")

    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name="+")
    leave_type_before = models.PositiveSmallIntegerField(null=True, blank=True, choices=Journal.LeaveType.choices)
    wfh_type_before = models.PositiveSmallIntegerField(null=True, blank=True, choices=Journal.WorkFromHomeType.choices)
    leave_type_after = models.PositiveSmallIntegerField(null=True, blank=True, choices=Journal.LeaveType.choices)
    wfh_type_after = models.PositiveSmallIntegerField(null=True, blank=True, choices=Journal.WorkFromHomeType.choices)
    source = models.PositiveSmallIntegerField(choices=Source.choices)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=_("User who made a manual or admin change. Empty for Timur"),
    )
    slack_availability_run = models.ForeignKey(
        "slack_availability.SlackAvailabilityRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=_("Slack availability run that made the change. Empty once the run is deleted"),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    # Typing
    id: int
    pk: int
    journal_id: int
    changed_by_id: int | None
    slack_availability_run_id: int | None
    get_source_display: typing.Callable[..., str]

    class Meta:  # type: ignore[reportIncompatibleVariableOverride]
        ordering = ["-id"]
        verbose_name_plural = _("Journal availability history")
        indexes = [
            models.Index(fields=["journal", "-created_at"]),
        ]

    @typing.override
    def __str__(self):
        return f"{self.journal_id}#{self.pk} ({self.get_source_display()})"

    @classmethod
    def record(
        cls,
        journal: Journal,
        *,
        leave_type_before: int | None,
        wfh_type_before: int | None,
        source: "JournalAvailabilityHistory.Source",
        changed_by: User | None = None,
        slack_availability_run_id: int | None = None,
    ) -> typing.Optional["JournalAvailabilityHistory"]:
        """
        Record the journal's current leave/WFH values, when they differ from the given values
        """
        if (leave_type_before, wfh_type_before) == (journal.leave_type, journal.wfh_type):
            return None
        return cls.objects.create(
            journal=journal,
            leave_type_before=leave_type_before,
            wfh_type_before=wfh_type_before,
            leave_type_after=journal.leave_type,
            wfh_type_after=journal.wfh_type,
            source=source,
            changed_by=changed_by,
            slack_availability_run_id=slack_availability_run_id,
        )
