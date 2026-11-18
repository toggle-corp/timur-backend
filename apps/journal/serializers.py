import typing

from rest_framework import serializers

from .models import Journal, JournalAvailabilityHistory


class JournalSerializer(serializers.ModelSerializer):
    class Meta:  # type: ignore[reportIncompatibleVariab]
        model = Journal
        fields = (
            "leave_type",
            "wfh_type",
            "journal_text",  # TODO: Create custom serializer field to convert null -> empty string for black=True
        )

    @typing.override
    def validate(self, attrs):
        super().validate(attrs)
        Journal(**attrs).leave_wfh_check()  # Check leave validation
        return attrs

    def _record_history(self, journal: Journal, leave_type_before: int | None, wfh_type_before: int | None):
        JournalAvailabilityHistory.record(
            journal,
            leave_type_before=leave_type_before,
            wfh_type_before=wfh_type_before,
            source=JournalAvailabilityHistory.Source.MANUAL,
            changed_by=self.context["request"].user,
        )

    @typing.override
    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        validated_data["date"] = self.context["extra_context"]["journal_date"]
        journal = super().create(validated_data)
        self._record_history(journal, None, None)
        return journal

    @typing.override
    def update(self, instance, validated_data):
        leave_type_before, wfh_type_before = instance.leave_type, instance.wfh_type
        journal = super().update(instance, validated_data)
        self._record_history(journal, leave_type_before, wfh_type_before)
        return journal
