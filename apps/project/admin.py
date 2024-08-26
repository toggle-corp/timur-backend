from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin

from apps.common.admin import PreventDeleteAdminMixin, UserResourceAdmin, VersionAdmin

from .models import Client, Contractor, Deadline, Project


@admin.register(Client)
class ClientAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)
    list_display = ("name",)


@admin.register(Contractor)
class ContractorAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)

    list_display = ("name",)


@admin.register(Deadline)
class DeadlineAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)

    list_display = ("name",)
    list_filter = (
        AutocompleteFilterFactory("Project", "project"),
        AutocompleteFilterFactory("Contract", "contract"),
    )


@admin.register(Project)
class ProjectAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)
    list_filter = (
        AutocompleteFilterFactory("Client", "project_client"),
        AutocompleteFilterFactory("Contractor", "contractor"),
    )

    list_display = ("name", "slide_order")
