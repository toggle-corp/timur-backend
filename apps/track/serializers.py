from rest_framework import serializers

from apps.common.serializers import TempClientIdMixin
from utils.strawberry.serializers import (
    CustomCharField,
    IntegerIDField,
    TimeDurationField,
)

from .models import TimeEntry


class TimeEntrySerializer(TempClientIdMixin, serializers.ModelSerializer):
    # Used just for adding description
    duration = TimeDurationField(required=False, allow_null=True)
    description = CustomCharField(required=False, allow_blank=True, trim_whitespace=False)

    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = TimeEntry
        fields = (
            "task",
            "date",
            "type",
            "description",
            "status",
            "duration",
            "start_time",
            "client_id",
        )

    # TODO: Lock changes per project
    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class TimeEntryBulkSerializer(TimeEntrySerializer):
    # Required by mutation
    id = IntegerIDField(required=False)

    class Meta(TimeEntrySerializer.Meta):
        fields = (
            "id",
            *TimeEntrySerializer.Meta.fields,
        )
