from django.contrib import admin

from apps.common.admin import UserResourceAdmin, VersionAdmin

from .models import Quote


@admin.register(Quote)
class QuoteAdmin(VersionAdmin, UserResourceAdmin):
    search_fields = ("author",)
    list_display = ("author", "last_viewed")
