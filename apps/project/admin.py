from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin
from django.db import models
from django.http import HttpRequest

from apps.common.admin import PreventDeleteAdminMixin, UserResourceAdmin, VersionAdmin

from .models import Client, Contractor, Deadline, Project


@admin.register(Client)
class ClientAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)
    list_display = ("name", "created_by", "modified_by")

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Client]:
        return super().get_queryset(request).select_related("created_by", "modified_by")


@admin.register(Contractor)
class ContractorAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)

    list_display = ("name", "created_by", "modified_by")

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Client]:
        return super().get_queryset(request).select_related("created_by", "modified_by")


@admin.register(Deadline)
class DeadlineAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)

    list_display = ("name", "created_by", "modified_by")
    list_filter = (
        AutocompleteFilterFactory("Project", "project"),
        AutocompleteFilterFactory("Contract", "contract"),
    )

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Client]:
        return super().get_queryset(request).select_related("created_by", "modified_by")


@admin.register(Project)
class ProjectAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
    search_fields = ("name",)
    list_filter = (
        AutocompleteFilterFactory("Client", "project_client"),
        AutocompleteFilterFactory("Contractor", "contractor"),
    )

    list_display = ("name", "created_by", "modified_by")

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Client]:
        return super().get_queryset(request).select_related("created_by", "modified_by")
