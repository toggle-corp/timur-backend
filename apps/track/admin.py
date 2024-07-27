from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin
from django.db import models
from django.http import HttpRequest

from apps.common.admin import UserResourceAdmin, UserResourceTabularInline, VersionAdmin

from .models import Contract, Task, TimeTrack


class ContractTaskInline(UserResourceTabularInline):
    model = Task
    ordering = ("pk",)


@admin.register(Contract)
class ContractAdmin(VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)
    list_filter = (
        AutocompleteFilterFactory("Project", "project"),
        AutocompleteFilterFactory("Created By", "created_by"),
        "is_archived",
    )
    autocomplete_fields = ("project",)
    list_display = ("name", "created_by", "get_project", "is_archived")
    inlines = [ContractTaskInline]

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Contract]:
        return super().get_queryset(request).select_related("created_by", "project")

    @admin.display(ordering="project__name", description="Project")
    def get_project(self, obj):
        return obj.project.name


@admin.register(Task)
class TaskAdmin(VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)
    list_filter = (
        AutocompleteFilterFactory("Project", "contract__project"),
        AutocompleteFilterFactory("Contract", "contract"),
        AutocompleteFilterFactory("Created By", "created_by"),
        "is_archived",
    )
    autocomplete_fields = ("contract",)
    list_display = ("name", "created_by", "get_project", "get_contract", "is_archived")

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Contract]:
        return super().get_queryset(request).select_related("created_by", "contract", "contract__project")

    @admin.display(ordering="project__name", description="Project")
    def get_project(self, obj):
        return obj.contract.project.name

    @admin.display(ordering="contract__name", description="Contract")
    def get_contract(self, obj):
        return obj.contract.name


@admin.register(TimeTrack)
class TimeTrackAdmin(admin.ModelAdmin):
    list_filter = (
        "date",
        "task_type",
        "is_done",
        AutocompleteFilterFactory("Project", "task__contract__project"),
        AutocompleteFilterFactory("Contract", "task__contract"),
        AutocompleteFilterFactory("Task", "task"),
        AutocompleteFilterFactory("User", "user"),
    )
    autocomplete_fields = (
        "user",
        "task",
    )
    list_display = (
        "get_contract",
        "get_project",
        "get_task",
        "get_user",
        "task_type",
        "date",
        "duration",
        "is_done",
    )

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Contract]:
        return super().get_queryset(request).select_related("user", "task", "task__contract", "task__contract__project")

    @admin.display(ordering="project__name", description="Project")
    def get_project(self, obj):
        return obj.task.contract.project.name

    @admin.display(ordering="contract__name", description="Contract")
    def get_contract(self, obj):
        return obj.task.contract.name

    @admin.display(ordering="task__name", description="Task")
    def get_task(self, obj):
        return obj.task.name

    @admin.display(ordering="user__name", description="User")
    def get_user(self, obj):
        return obj.user
