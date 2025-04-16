import datetime

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

    def clean(self):
        super().clean()
        self.leave_wfh_check()
