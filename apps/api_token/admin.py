import typing

from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin, messages
from django.db import models
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from djangoql.admin import DjangoQLSearchMixin

from .models import ApiToken


class StatusFilter(admin.SimpleListFilter):
    title = _("Status")
    parameter_name = "status"

    @typing.override
    def lookups(self, request, model_admin):
        return ApiToken.Status.choices

    @typing.override
    def queryset(self, request, queryset):
        now = timezone.now()
        value = self.value()
        if value == ApiToken.Status.ACTIVE:
            return queryset.filter(revoked_at__isnull=True, expires_at__gt=now)
        if value == ApiToken.Status.EXPIRED:
            return queryset.filter(revoked_at__isnull=True, expires_at__lte=now)
        if value == ApiToken.Status.REVOKED:
            return queryset.filter(revoked_at__isnull=False)
        return queryset


@admin.register(ApiToken)
class ApiTokenAdmin(DjangoQLSearchMixin, admin.ModelAdmin):
    """
    Superuser-only, read-only view of API tokens. The token hash is never shown.
    Tokens are created by users and can only be revoked here.
    """

    list_display = (
        "name",
        "prefix",
        "user",
        "status",
        "scopes",
        "created_at",
        "expires_at",
        "last_used_at",
        "revoked_at",
    )
    list_filter = (
        StatusFilter,
        AutocompleteFilterFactory("User", "user"),
        "created_at",
        "expires_at",
    )
    search_fields = ("name", "prefix", "user__email")
    fields = (
        "user",
        "name",
        "prefix",
        "scopes",
        "created_at",
        "expires_at",
        "last_used_at",
        "revoked_at",
        "expiry_reminder_sent_at",
        "expired_notice_sent_at",
    )
    readonly_fields = fields
    actions = ("revoke_tokens",)
    list_select_related = ("user",)

    @admin.display(description=_("Status"))
    def status(self, obj: ApiToken) -> str:
        return obj.get_status().label

    @admin.action(description=_("Revoke selected tokens"), permissions=["superuser"])
    def revoke_tokens(self, request: HttpRequest, queryset: models.QuerySet[ApiToken]):
        count = queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        self.message_user(request, _("%(count)d token(s) revoked.") % {"count": count}, messages.SUCCESS)

    def has_superuser_permission(self, request: HttpRequest) -> bool:
        return request.user.is_active and request.user.is_superuser  # type: ignore[reportAttributeAccessIssue]

    @typing.override
    def has_module_permission(self, request):
        return self.has_superuser_permission(request)

    @typing.override
    def has_view_permission(self, request, obj=None):
        return self.has_superuser_permission(request)

    @typing.override
    def has_change_permission(self, request, obj=None):
        return self.has_superuser_permission(request)

    @typing.override
    def has_add_permission(self, request, obj=None):
        return False

    @typing.override
    def has_delete_permission(self, request, obj=None):
        return False
