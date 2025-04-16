from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin, messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.admin import UserResourceAdmin, VersionAdmin

from .models import Client, Contractor, Deadline, Project


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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
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
