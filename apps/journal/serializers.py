from rest_framework import serializers

from .models import Journal


class JournalSerializer(serializers.ModelSerializer):
    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = Journal
        fields = (
            "leave_type",
            "journal_text",  # TODO: Create custom serializer field to convert null -> empty string for black=True
        )

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        validated_data["date"] = self.context["extra_context"]["journal_date"]
        return super().create(validated_data)
