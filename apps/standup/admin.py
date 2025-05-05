from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.common.admin import UserResourceAdmin, VersionAdmin

from .models import DailyUserStandup, Quote, StandupGatherAroundMedia


@admin.register(Quote)
class QuoteAdmin(VersionAdmin, UserResourceAdmin):
    search_fields = ("author", "text")
    list_filter = ("auto_select",)
    list_display = ("author", "last_viewed")


@admin.register(StandupGatherAroundMedia)
class StandupGatherAroundMediaAdmin(VersionAdmin, UserResourceAdmin):
    search_fields = ("url", "caption")
    list_filter = ("auto_select",)
    list_display = ("caption", "url_preview", "last_viewed")

    @admin.display(description=_("url display"))
    def url_preview(self, obj):
        return format_html(
            (
                '<a href="{0}" target="_blank">'
                '<img src="{0}" style="max-width: 300px; max-height: 300px; border-radius: 4px; object-fit: contain;" />'
                "</a>"
            ),
            obj.url,
        )


@admin.register(DailyUserStandup)
class DailyUserStandupAdmin(VersionAdmin):
    list_filter = ("date",)
    list_display = ("date", "conductor", "fallback_conductor")
    autocomplete_fields = (
        "quote",
        "gather_around_media",
        "conductor",
        "fallback_conductor",
    )
