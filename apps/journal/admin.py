from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin
from rangefilter.filters import DateRangeQuickSelectListFilterBuilder

from apps.common.admin import PreventDeleteAdminMixin, VersionAdmin

from .models import Journal


@admin.register(Journal)
class JournalAdmin(PreventDeleteAdminMixin, VersionAdmin):
    search_fields = ("user",)
    list_display = ("user", "date", "leave_type", "wfh_type")
    list_filter = (
        ("date", DateRangeQuickSelectListFilterBuilder()),
        AutocompleteFilterFactory("User", "user"),
        "leave_type",
        "wfh_type",
    )
    ordering = (
        "date",
        "user",
    )

    autocomplete_fields = ("user",)
