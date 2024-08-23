from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin, messages
from django.db import models
from django.http import HttpRequest
from django.utils.translation import ngettext

from apps.common.admin import (
    PreventDeleteAdminMixin,
    UserResourceAdmin,
    UserResourceTabularInline,
    VersionAdmin,
)

from .models import Contract, Task, TimeEntry


class ContractTaskInline(UserResourceTabularInline):
    model = Task
    ordering = ("pk",)
    can_delete = False


@admin.register(Contract)
class ContractAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
    search_fields = (
        "project__name",
        "name",
    )
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
class TaskAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
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


# Time Entry ----------------------------------------------------
@admin.action(description="Mark time entries as non-billable")
def flag_as_non_billable(modeladmin, request, queryset):
    updated = queryset.update(is_billable=False)
    modeladmin.message_user(
        request,
        ngettext(
            "%d time entry was successfully marked as non-billable.",
            "%d time entries were successfully marked as non-billable.",
            updated,
        )
        % updated,
        messages.SUCCESS,
    )


@admin.action(description="Mark time entries as billable")
def flag_as_billable(modeladmin, request, queryset):
    updated = queryset.update(is_billable=True)
    modeladmin.message_user(
        request,
        ngettext(
            "%d time entry was successfully marked as billable.",
            "%d time entries were successfully marked as billable.",
            updated,
        )
        % updated,
        messages.SUCCESS,
    )


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_filter = (
        "date",
        "type",
        "status",
        "is_billable",
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
        "type",
        "date",
        "duration",
        "duration_adjustment",
        "is_billable",
        "status",
    )
    actions = [flag_as_non_billable, flag_as_billable]

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
