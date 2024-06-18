from django.contrib import admin
from reversion.admin import VersionAdmin as OgVersionAdmin

from .models import UserResource


class VersionAdmin(OgVersionAdmin):
    history_latest_first = True


class UserResourceAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, *args, **kwargs):
        readonly_fields = super().get_readonly_fields(*args, **kwargs)  # type: ignore[reportAttributeAccessIssue]
        return [
            # To maintain order
            *dict.fromkeys(
                [
                    *readonly_fields,
                    "created_at",
                    "created_by",
                    "modified_at",
                    "modified_by",
                ]
            )
        ]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.modified_by = request.user
        return super().save_model(request, obj, form, change)  # type: ignore[reportAttributeAccessIssue]

    def save_formset(self, request, form, formset, change):
        if not issubclass(formset.model, UserResource):
            return super().save_formset(request, form, formset, change)
        # https://docs.djangoproject.com/en/4.2/ref/contrib/admin/#django.contrib.admin.ModelAdmin.save_formset
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            # UserResource changes
            if instance.pk is None:
                instance.created_by = request.user
            instance.modified_by = request.user
            instance.save()


class UserResourceTabularInline(admin.TabularInline):
    def get_readonly_fields(self, *args, **kwargs):
        readonly_fields = super().get_readonly_fields(*args, **kwargs)  # type: ignore[reportAttributeAccessIssue]
        return [
            # To maintain order
            *dict.fromkeys(
                [
                    *readonly_fields,
                    "created_at",
                    "created_by",
                    "modified_at",
                    "modified_by",
                ]
            )
        ]
