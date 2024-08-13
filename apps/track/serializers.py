from rest_framework import serializers

from apps.common.serializers import TempClientIdMixin
from utils.strawberry.serializers import IntegerIDField, TimeDurationField

from .models import TimeEntry


class TimeEntrySerializer(TempClientIdMixin, serializers.ModelSerializer):
    duration = TimeDurationField(required=False, allow_null=True)

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
