from django.contrib import admin

from apps.common.admin import UserResourceAdmin, VersionAdmin

from .models import DailyUserStandup, Quote


@admin.register(Quote)
class QuoteAdmin(VersionAdmin, UserResourceAdmin):
    search_fields = ("author", "text")
    list_display = ("author", "last_viewed")


@admin.register(DailyUserStandup)
class DailyUserStandupAdmin(VersionAdmin):
    list_filter = ("date",)
    list_display = ("date", "conductor", "fallback_conductor")
    autocomplete_fields = (
        "quote",
        "conductor",
        "fallback_conductor",
    )
