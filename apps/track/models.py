from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import UserResource
from apps.project.models import Project
from apps.user.models import User


class Contract(UserResource):
    name = models.CharField(max_length=225)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="contracts")
    total_estimated_hours = models.FloatField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)

    project_id: int
    tasks: models.QuerySet["Task"]

    def __str__(self):
        return f"{self.name} ({self.total_estimated_hours} hours)"


class Task(UserResource):
    name = models.CharField(max_length=225)
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="tasks")
    estimated_hours = models.FloatField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)

    contract_id: int

    def __str__(self):
        return self.name


class TimeTrack(models.Model):
    class TaskType(models.IntegerChoices):
        # Using 4 digit for future ordering support
        DESIGN = 1000, _("Design")
        DEVELOPMENT = 1100, _("Development")
        DEV_OPS = 1200, _("DevOps")
        DOCUMENTATION = 2000, _("Documentation")
        INTERNAL_DISCUSSION = 3000, _("Documentation")
        MEETING = 4000, _("Meeting")
        QUALITY_ASSURANCE = 5000, _("QA")

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name="+")
    date = models.DateField()

    task_type = models.PositiveSmallIntegerField(choices=TaskType.choices)
    description = models.TextField(blank=True)
    is_done = models.BooleanField(default=False)

    duration = models.DurationField(null=True, blank=True)

    user_id: int
    task_id: int
