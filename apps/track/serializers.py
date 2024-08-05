from rest_framework import serializers

from apps.common.serializers import TempClientIdMixin
from utils.strawberry.serializers import IntegerIDField

from .models import TimeEntry


class TimeEntrySerializer(TempClientIdMixin, serializers.ModelSerializer):
    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = TimeEntry
        fields = (
            "task",
            "date",
            "task_type",
            "description",
            "is_done",
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
