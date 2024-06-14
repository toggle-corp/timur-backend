from rest_framework import serializers

from apps.common.serializers import TempClientIdMixin

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
            "client_id",
        )

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)
