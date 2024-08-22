from django.contrib import admin

from apps.common.admin import PreventDeleteAdminMixin, VersionAdmin

from .models import Journal


@admin.register(Journal)
class JournalAdmin(PreventDeleteAdminMixin, VersionAdmin):
    search_fields = ("user",)
    list_display = ("user", "date")

    autocomplete_fields = ("user",)
