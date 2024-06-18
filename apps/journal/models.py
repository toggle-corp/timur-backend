from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.user.models import User


class Journal(models.Model):

    class LeaveType(models.IntegerChoices):
        FULL = 1, _("Full")
        FIRST_HALF = 2, _("First Half")
        SECOND_HALF = 3, _("Second Half")

    user = models.ForeignKey(User, related_name="+", on_delete=models.CASCADE)
    date = models.DateField()

    leave_type = models.PositiveSmallIntegerField(null=True, blank=True, choices=LeaveType.choices)

    journal_text = models.TextField(blank=True)

    user_id: int

    class Meta:  # type: ignore[reportIncompatibleVariableOverride]
        unique_together = ("user", "date")
        indexes = [
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return f"{self.user_id}#{self.date}"
