from django.contrib import admin

from apps.common.admin import PreventDeleteAdminMixin, UserResourceAdmin, VersionAdmin

from .models import Quote


@admin.register(Quote)
class QuoteAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
    search_fields = ("author",)
    list_display = ("author",)
