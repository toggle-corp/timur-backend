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

    @admin.display(ordering="project__name", description="Project")
    def get_project(self, obj):
        return obj.project.name


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_filter = (
        AutocompleteFilterFactory("Project", "milestone__project"),
        AutocompleteFilterFactory("Milestone", "milestone"),
        AutocompleteFilterFactory("Created By", "created_by"),
        "is_archived",
    )
    autocomplete_fields = ("milestone",)
    list_display = ("name", "get_project", "get_milestone", "is_archived")

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Milestone]:
        return super().get_queryset(request).select_related("milestone", "milestone__project")

    @admin.display(ordering="project__name", description="Project")
    def get_project(self, obj):
        return obj.milestone.project.name

    @admin.display(ordering="milestone__name", description="Milestone")
    def get_milestone(self, obj):
        return obj.milestone.name


@admin.register(TimeTrack)
class TimeTrackAdmin(admin.ModelAdmin):
    list_filter = (
        "date",
        "task_type",
        "is_done",
        AutocompleteFilterFactory("Project", "task__milestone__project"),
        AutocompleteFilterFactory("Milestone", "task__milestone"),
        AutocompleteFilterFactory("Task", "task"),
        AutocompleteFilterFactory("User", "user"),
    )
    autocomplete_fields = ("task",)
    list_display = (
        "get_milestone",
        "get_project",
        "get_task",
        "get_user",
        "task_type",
        "date",
        "duration",
        "is_done",
    )

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Milestone]:
        return super().get_queryset(request).select_related("user", "task", "task__milestone", "task__milestone__project")

    @admin.display(ordering="project__name", description="Project")
    def get_project(self, obj):
        return obj.task.milestone.project.name

    @admin.display(ordering="milestone__name", description="Milestone")
    def get_milestone(self, obj):
        return obj.task.milestone.name

    @admin.display(ordering="task__name", description="Task")
    def get_task(self, obj):
        return obj.task.name

    @admin.display(ordering="user__name", description="User")
    def get_user(self, obj):
        return obj.user
