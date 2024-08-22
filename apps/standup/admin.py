from django.contrib import admin
from django.db import models
from django.http import HttpRequest

from apps.common.admin import PreventDeleteAdminMixin, UserResourceAdmin, VersionAdmin

from .models import Quote


@admin.register(Quote)
class QuoteAdmin(PreventDeleteAdminMixin, VersionAdmin, UserResourceAdmin):
    search_fields = ("author",)
    list_display = ("author", "created_by", "modified_by")

    def get_queryset(self, request: HttpRequest) -> models.QuerySet[Quote]:
        return super().get_queryset(request).select_related("created_by", "modified_by")
