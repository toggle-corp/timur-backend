from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin, messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.admin import UserResourceAdmin, VersionAdmin

from .models import Client, Contractor, Deadline, Project
from .tasks import sync_deadline_with_google_calendar


@admin.register(Client)
class ClientAdmin(VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)
    list_display = ("name",)


@admin.register(Contractor)
class ContractorAdmin(VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)
    list_display = ("name",)


@admin.register(Deadline)
class DeadlineAdmin(VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)

    list_display = ("name", "start_date", "end_date")
    list_filter = (
        "is_archived",
        AutocompleteFilterFactory("Project", "project"),
        AutocompleteFilterFactory("Contract", "contract"),
    )

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
        obj.google_calendar_sync_status = Deadline.GoogleCalendarSyncStatus.PENDING
        super().save_model(request, obj, form, change)

        # TODO(thenav56): Make this async with celery
        sync_deadline_with_google_calendar(obj)

        if obj.start_date > timezone.now().date():
            messages.warning(
                request,
                _(
                    "It appears that the start date is in the future. "
                    "This deadline will remain hidden until the start date is reached.",
                ),
            )


@admin.register(Project)
class ProjectAdmin(VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)
    list_filter = (
        "is_archived",
        AutocompleteFilterFactory("Client", "project_client"),
        AutocompleteFilterFactory("Contractor", "contractor"),
    )

    list_display = ("name", "slide_order")
