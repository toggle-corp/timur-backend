from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin

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

    list_display = ("name",)
    list_filter = (
        "is_archived",
        AutocompleteFilterFactory("Project", "project"),
        AutocompleteFilterFactory("Contract", "contract"),
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
