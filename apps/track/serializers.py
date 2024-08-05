from rest_framework import serializers

from apps.common.serializers import TempClientIdMixin
from utils.strawberry.serializers import IntegerIDField

from .models import TimeTrack


class TimeTrackSerializer(TempClientIdMixin, serializers.ModelSerializer):
    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = TimeTrack
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


class TimeTrackBulkSerializer(TimeTrackSerializer):
    # Required by mutation
    id = IntegerIDField(required=False)

    class Meta(TimeTrackSerializer.Meta):
        fields = (
            "id",
            *TimeTrackSerializer.Meta.fields,
        )
