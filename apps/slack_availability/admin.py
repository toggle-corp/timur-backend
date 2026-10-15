import json
import typing

from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html

from .models import SlackAvailabilityJournalEntry, SlackAvailabilityRun, SlackAvailabilityThread


def _is_active_superuser(request: HttpRequest) -> bool:
    return request.user.is_active and getattr(request.user, "is_superuser", False)


class SuperuserOnlyAdminMixin:
    """
    Threads hold message text, which can include personal details
    """

    def has_module_permission(self, request: HttpRequest):
        return _is_active_superuser(request)

    def has_view_permission(self, request: HttpRequest, obj=None):
        return _is_active_superuser(request)

    def has_add_permission(self, *_, **__):
        return False

    def has_change_permission(self, *_, **__):
        return False

    def has_delete_permission(self, *_, **__):
        return False


def _pretty_json(value) -> str:
    return format_html("<pre>{}</pre>", json.dumps(value, indent=2, ensure_ascii=False))


class SlackAvailabilityRunInline(SuperuserOnlyAdminMixin, admin.TabularInline):
    model = SlackAvailabilityRun
    fields = ("created_at", "mode", "trigger", "status", "today", "reply_text")
    readonly_fields = fields
    extra = 0
    show_change_link = True


class SlackAvailabilityJournalEntryInline(SuperuserOnlyAdminMixin, admin.TabularInline):
    model = SlackAvailabilityJournalEntry
    fields = ("journal", "leave_type", "wfh_type", "modified_at")
    readonly_fields = fields
    extra = 0


@admin.register(SlackAvailabilityThread)
class SlackAvailabilityThreadAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("thread_ts", "user", "slack_user_id", "is_deleted", "snapshot_at", "created_at", "modified_at")
    list_filter = ("is_deleted",)
    search_fields = ("thread_ts", "slack_user_id", "user__email")
    list_select_related = ("user",)
    inlines = (SlackAvailabilityRunInline, SlackAvailabilityJournalEntryInline)
    fields = ("channel_id", "thread_ts", "slack_user_id", "user", "is_deleted", "snapshot_at", "desired_state_display")
    readonly_fields = fields

    @admin.display(description="Desired state")
    def desired_state_display(self, obj: SlackAvailabilityThread):
        return _pretty_json(obj.desired_state)


@admin.register(SlackAvailabilityRun)
class SlackAvailabilityRunAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("id", "thread", "user", "mode", "trigger", "status", "today", "created_at")
    list_filter = ("mode", "trigger", "status")
    search_fields = ("thread__thread_ts", "thread__slack_user_id", "thread__user__email")
    list_select_related = ("thread__user",)
    fields = (
        "thread",
        "mode",
        "trigger",
        "trigger_ts",
        "status",
        "today",
        "llm_input",
        "purged_at",
        "llm_model",
        "llm_output_display",
        "planned_changes_display",
        "trace_display",
        "reply_text",
        "reply_ts",
        "error",
        "created_at",
    )
    readonly_fields = fields

    @admin.display(description="User")
    def user(self, obj: SlackAvailabilityRun):
        return obj.thread.user

    @admin.display(description="LLM output")
    def llm_output_display(self, obj: SlackAvailabilityRun):
        return _pretty_json(obj.llm_output)

    @admin.display(description="Planned changes")
    def planned_changes_display(self, obj: SlackAvailabilityRun):
        return _pretty_json(obj.planned_changes)

    @admin.display(description="Trace")
    def trace_display(self, obj: SlackAvailabilityRun):
        return _pretty_json(obj.trace)

    @typing.override
    def get_queryset(self, request: HttpRequest):
        return super().get_queryset(request).select_related("thread__user")
