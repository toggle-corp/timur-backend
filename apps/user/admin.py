import typing

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from djangoql.admin import DjangoQLSearchMixin

from .models import User


class HasSlackUserIdFilter(admin.SimpleListFilter):
    title = _("Slack User ID")
    parameter_name = "has_slack_user_id"

    @typing.override
    def lookups(self, request, model_admin):
        return (
            ("yes", gettext("Has value")),
            ("no", gettext("Is empty")),
        )

    @typing.override
    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(slack_user_id__isnull=True).exclude(slack_user_id__exact="")
        if self.value() == "no":
            return queryset.filter(slack_user_id__isnull=True) | queryset.filter(slack_user_id__exact="")
        return queryset


@admin.register(User)
class UserAdmin(DjangoQLSearchMixin, DjangoUserAdmin):
    list_display = (
        "email",
        "is_active",
        "first_name",
        "last_name",
        "department",
        "is_staff",
        "assign_for_standup",
        "exclude_from_slides",
    )
    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
        "groups",
        "assign_for_standup",
        "exclude_from_slides",
        HasSlackUserIdFilter,
    )
    search_fields = ("first_name", "last_name", "email")
    ordering = ("email",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "email",
                    "password",
                ),
            },
        ),
        (
            _("Personal info"),
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "department",
                    "display_picture",
                    "slack_user_id",
                ),
            },
        ),
        (
            _("Standup"),
            {
                "fields": (
                    "assign_for_standup",
                    "exclude_from_slides",
                ),
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
