from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import UserResource
from apps.project.models import Project
from apps.user.models import User


class Milestone(UserResource):
    name = models.CharField(max_length=225)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="milestones")
    is_archived = models.BooleanField(default=False)

    project_id: int

    def __str__(self):
        return self.name


class Task(UserResource):
    name = models.CharField(max_length=225)
    milestone = models.ForeignKey(Milestone, on_delete=models.PROTECT, related_name="tasks")
    is_archived = models.BooleanField(default=False)

    milestone_id: int

    def __str__(self):
        return self.name


class TimeTrack(models.Model):
    class TaskType(models.IntegerChoices):
        DEVELOPMENT = 1, _("Development")
        QUALITY_ASSURANCE = 2, _("Quality Assurance")
        DESIGNING = 3, _("Designing")
        MEETING = 4, _("Meeting")
        INTERNAL_MEETING = 5, _("Meeting (Internal)")
        # TODO: Add/Remove

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name="+")
    date = models.DateField()

    task_type = models.PositiveSmallIntegerField(choices=TaskType.choices)
    description = models.TextField(blank=True)
    is_done = models.BooleanField(default=False)

    duration = models.DurationField(null=True, blank=True)

    user_id: int
    task_id: int
