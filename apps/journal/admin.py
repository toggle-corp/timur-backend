from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin

from apps.common.admin import PreventDeleteAdminMixin, VersionAdmin

from .models import Journal


@admin.register(Journal)
class JournalAdmin(PreventDeleteAdminMixin, VersionAdmin):
    search_fields = ("user",)
    list_display = ("user", "date", "leave_type", "wfh_type")
    list_filter = (AutocompleteFilterFactory("User", "user"),)
    ordering = (
        "date",
        "user",
    )

    autocomplete_fields = ("user",)
