from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin

from .models import Client, Contractor, Project


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Contractor)
class ContractorAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_filter = (
        AutocompleteFilterFactory("Client", "client"),
        AutocompleteFilterFactory("Contractor", "contractor"),
    )
