from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import UserResource
from apps.project.models import Project
from apps.user.models import User


# TODO: Move this to project?
class Contract(UserResource):
    name = models.CharField(max_length=225)
    description = models.TextField(blank=True)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="contracts")
    total_estimated_hours = models.FloatField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)

    project_id: int
    tasks: models.QuerySet["Task"]

    def __str__(self):
        # NOTE: N+1
        return f"{self.project.name} -> {self.name} ({self.total_estimated_hours} hours)"


# TODO: Move this to project?
class Task(UserResource):
    name = models.CharField(max_length=225)
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="tasks")
    estimated_hours = models.FloatField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)

    contract_id: int

    def __str__(self):
        return self.name


class TimeEntry(models.Model):
    class Type(models.IntegerChoices):
        # XXX: Custom integer value is used to support sort by label

        # For MISC, user will leave it empty
        # Generic
        DOCUMENTATION = 6, _("Documentation")
        RESEARCH = 11, _("Research")
        DESIGN = 1, _("Design")
        OPERATION = 9, _("Operation")
        PROJECT_MANAGEMENT = 10, _("Project Management")
        TESTING = 12, _("Testing")

        # Development
        DEVELOPMENT = 3, _("Development")
        DEV_OPS = 2, _("DevOps")

        # Communication
        # - Discussion
        EXTERNAL_DISCUSSION = 4, _("Discussion External")
        INTERNAL_DISCUSSION = 5, _("Discussion Internal")
        # - Meeting
        EXTERNAL_MEETING = 7, _("Meeting External")
        INTERNAL_MEETING = 8, _("Meeting Internal")

    class Status(models.IntegerChoices):
        DOING = 1, _("DOING")
        DONE = 2, _("DONE")
        TODO = 3, _("TODO")

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name="+")
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)  # To track TODO tasks

    type = models.PositiveSmallIntegerField(choices=Type.choices, null=True, blank=True)
    status = models.PositiveSmallIntegerField(choices=Status.choices)
    # NOTE: client_id persisted as ULID, but no validation done on server-side
    #  Uniqueness is required at per-user per-day level
    #  Due to which uniqueness is not something we need to check at DB level
    client_id = models.CharField(max_length=26, null=True, blank=True)

    start_time = models.TimeField(null=True, blank=True)
    description = models.TextField(blank=True)

    duration = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=_("Minutes"),
    )

    # Operational metadata
    duration_adjustment = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text=_(
            "Minutes. Used to keep track of reported minutes. This will be used as duration (+- duration_adjustment)"
        ),
    )
    is_billable = models.BooleanField(default=True)

    user_id: int
    task_id: int

    class Meta:  # type: ignore[reportIncompatibleVariab]
        verbose_name = _("time entry")
        verbose_name_plural = _("time entries")

    def clean(self):
        super().clean()

        # Make sure duration is defined before having duration_adjustment
        if self.duration_adjustment is not None and self.duration is None:
            raise ValidationError(_("Duration needs to be defined before using Duration (Adjustment)"))

        # Make sure duration + duration_adjustment doesn't have negative value
        if self.duration is not None and self.duration_adjustment is not None:
            if self.duration_adjustment + self.duration < 0:
                raise ValidationError(_("Duration adjustment shouldn't generate negative duration"))
