import typing

from django.contrib import admin
from django.db import models
from django.http import HttpRequest
from reversion.admin import VersionAdmin as OgVersionAdmin

from .models import Event, UserResource
from .tasks import sync_event_with_google_calendar

DjangoModel = typing.TypeVar("DjangoModel", bound=models.Model)


# -- Abstracts
class VersionAdmin(OgVersionAdmin):
    history_latest_first = True


class PreventDeleteAdminMixin:
    def has_delete_permission(self, request, obj=None):
        return False


class UserResourceAdmin(admin.ModelAdmin):
    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        for field in ["created_by", "modified_by"]:
            if field not in list_display:
                list_display = [
                    *list_display,
                    field,
                ]
        return list_display

    def get_readonly_fields(self, *args, **kwargs):
        readonly_fields = super().get_readonly_fields(*args, **kwargs)  # type: ignore[reportAttributeAccessIssue]
        return [
            # To maintain order
            *dict.fromkeys(
                [
                    *readonly_fields,
                    "created_at",
                    "created_by",
                    "modified_at",
                    "modified_by",
                ],
            ),
        ]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)  # type: ignore[reportAttributeAccessIssue]

    def save_formset(self, request, form, formset, change) -> None:
        if not issubclass(formset.model, UserResource):
            return super().save_formset(request, form, formset, change)
        # https://docs.djangoproject.com/en/4.2/ref/contrib/admin/#django.contrib.admin.ModelAdmin.save_formset
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            # UserResource changes
            if instance.pk is None:
                instance.created_by = request.user
            instance.modified_by = request.user
            instance.save()
        return None

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[DjangoModel]:
        return super().get_queryset(request).select_related("created_by", "modified_by")


class UserResourceTabularInline(admin.TabularInline):
    def get_readonly_fields(self, *args, **kwargs):
        readonly_fields = super().get_readonly_fields(*args, **kwargs)  # type: ignore[reportAttributeAccessIssue]
        return [
            # To maintain order
            *dict.fromkeys(
                [
                    *readonly_fields,
                    "created_at",
                    "created_by",
                    "modified_at",
                    "modified_by",
                ],
            ),
        ]


# -- Common Models
@admin.register(Event)
class EventAdmin(VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)
    list_display = ("name", "type", "start_date", "end_date")
    list_filter = ("type",)
    ordering = ("start_date",)

    def get_readonly_fields(self, *args, **kwargs):
        readonly_fields = super().get_readonly_fields(*args, **kwargs)  # type: ignore[reportAttributeAccessIssue]
        return [
            # To maintain order
            *dict.fromkeys(
                [
                    *readonly_fields,
                    "google_calendar_sync_status",
                    "google_calendar_event_id",
                    "google_calendar_html_link",
                ],
            ),
        ]

    def save_model(self, request, obj, form, change):
        obj.google_calendar_sync_status = Event.GoogleCalendarSyncStatus.PENDING
        super().save_model(request, obj, form, change)
        # TODO(thenav56): Make this async with celery
        sync_event_with_google_calendar(obj)
