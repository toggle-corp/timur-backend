import typing

from admin_auto_filters.filters import AutocompleteFilterFactory
from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.http import HttpRequest
from djangoql.admin import DjangoQLSearchMixin
from rangefilter.filters import DateRangeQuickSelectListFilterBuilder

from apps.common.admin import PreventDeleteAdminMixin, VersionAdmin
from apps.slack_availability.admin import SuperuserOnlyAdminMixin

from .models import Journal, JournalAvailabilityHistory

if typing.TYPE_CHECKING:
    from apps.user.models import User

# Request attribute: leave/WFH values of the journal before an admin revert or recover
AVAILABILITY_BEFORE_ATTR = "_journal_availability_before"

HISTORY_FIELDS = (
    "created_at",
    "source",
    "changed_by",
    "slack_availability_run",
    "leave_type_before",
    "wfh_type_before",
    "leave_type_after",
    "wfh_type_after",
)


class JournalAvailabilityHistoryInline(SuperuserOnlyAdminMixin, admin.TabularInline):
    model = JournalAvailabilityHistory
    fields = HISTORY_FIELDS
    readonly_fields = fields
    extra = 0
    verbose_name_plural = "Availability history"


@admin.register(Journal)
class JournalAdmin(DjangoQLSearchMixin, PreventDeleteAdminMixin, VersionAdmin):
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
    inlines = (JournalAvailabilityHistoryInline,)

    @staticmethod
    def _stored_availability(pk) -> tuple[int | None, int | None]:
        return Journal.objects.filter(pk=pk).values_list("leave_type", "wfh_type").first() or (None, None)

    @typing.override
    def save_model(self, request, obj, form, change):
        before = getattr(request, AVAILABILITY_BEFORE_ATTR, None)
        if before is None:
            before = self._stored_availability(obj.pk) if obj.pk else (None, None)
        super().save_model(request, obj, form, change)
        JournalAvailabilityHistory.record(
            obj,
            leave_type_before=before[0],
            wfh_type_before=before[1],
            source=JournalAvailabilityHistory.Source.ADMIN,
            # Admin pages are only open to signed-in staff
            changed_by=typing.cast("User", request.user),
        )

    # Reverting and recovering write the old version before the form is saved, so the values before are read first

    @typing.override
    def revision_view(self, request, object_id, version_id, extra_context=None):
        if request.method == "POST":
            setattr(request, AVAILABILITY_BEFORE_ATTR, self._stored_availability(unquote(object_id)))
        return super().revision_view(request, object_id, version_id, extra_context)

    @typing.override
    def recover_view(self, request, version_id, extra_context=None):
        if request.method == "POST":
            setattr(request, AVAILABILITY_BEFORE_ATTR, (None, None))
        return super().recover_view(request, version_id, extra_context)


@admin.register(JournalAvailabilityHistory)
class JournalAvailabilityHistoryAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("journal", "user", "date", *HISTORY_FIELDS)
    list_filter = (
        ("journal__date", DateRangeQuickSelectListFilterBuilder()),
        AutocompleteFilterFactory("User", "journal__user"),
        "source",
    )
    list_select_related = ("journal__user", "changed_by", "slack_availability_run")
    fields = ("journal", *HISTORY_FIELDS)
    readonly_fields = fields

    @admin.display(description="User", ordering="journal__user")
    def user(self, obj: JournalAvailabilityHistory):
        return obj.journal.user

    @admin.display(description="Date", ordering="journal__date")
    def date(self, obj: JournalAvailabilityHistory):
        return obj.journal.date

    @typing.override
    def get_queryset(self, request: HttpRequest):
        return super().get_queryset(request).select_related("journal__user", "changed_by", "slack_availability_run")
