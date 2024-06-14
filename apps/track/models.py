from django.db import models

from apps.common.models import UserResource
from apps.project.models import Project
from apps.user.models import User


class Milestone(UserResource):
    name = models.CharField(max_length=225)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="milestones")
    is_archived = models.BooleanField(default=False)

    project_id: int


class Task(UserResource):
    name = models.CharField(max_length=225)
    milestone = models.ForeignKey(Milestone, on_delete=models.PROTECT, related_name="tasks")
    is_archived = models.BooleanField(default=False)

    milestone_id: int


class TimeTrack(models.Model):
    class TaskType(models.IntegerChoices):
        DEVELOPMENT = 1, "Development"
        QUALITY_ASSURANCE = 2, "Quality Assurance"
        DESIGNING = 3, "Designing"
        MEETING = 4, "Meeting"
        INTERNAL_MEETING = 5, "Meeting (Internal)"
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
