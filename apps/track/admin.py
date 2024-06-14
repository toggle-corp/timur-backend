from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin
from django.db import models
from django.http import HttpRequest

from .models import Milestone, Task, TimeTrack


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_filter = (
        AutocompleteFilterFactory("Project", "project"),
        AutocompleteFilterFactory("Created By", "created_by"),
        "is_archived",
    )
    autocomplete_fields = ("project",)
    list_display = ("name", "get_project", "is_archived")

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Milestone]:
        return super().get_queryset(request).select_related("project")

    @admin.display(ordering="project__title", description="Project")
    def get_project(self, obj):
        return obj.project.title


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_filter = (
        AutocompleteFilterFactory("Project", "milestone__project"),
        AutocompleteFilterFactory("Milestone", "milestone"),
        AutocompleteFilterFactory("Created By", "created_by"),
        "is_archived",
    )
    autocomplete_fields = ("project",)
    list_display = ("name", "get_milestone", "get_project", "is_archived")

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Milestone]:
        return super().get_queryset(request).select_related("milestone", "milestone__project")

    @admin.display(ordering="project__title", description="Project")
    def get_project(self, obj):
        return obj.milestone.project.title

    @admin.display(ordering="milestone__title", description="Milestone")
    def get_milestone(self, obj):
        return obj.milestone.title


@admin.register(TimeTrack)
class TimeTrackAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_filter = (
        "date",
        "task_type",
        "is_done",
        AutocompleteFilterFactory("Project", "task__milestone__project"),
        AutocompleteFilterFactory("Milestone", "task__milestone"),
        AutocompleteFilterFactory("Task", "task"),
        AutocompleteFilterFactory("Created By", "created_by"),
    )
    autocomplete_fields = ("task",)
    list_display = (
        "get_milestone",
        "get_project",
        "get_task",
        "task_type",
        "date",
        "duration",
        "is_done",
    )

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Milestone]:
        return super().get_queryset(request).select_related("task", "task__milestone", "task__milestone__project")

    @admin.display(ordering="project__title", description="Project")
    def get_project(self, obj):
        return obj.task.milestone.project.title

    @admin.display(ordering="milestone__title", description="Milestone")
    def get_milestone(self, obj):
        return obj.task.milestone.title

    @admin.display(ordering="task__title", description="Task")
    def get_task(self, obj):
        return obj.task.title
