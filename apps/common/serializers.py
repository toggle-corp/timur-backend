from rest_framework import serializers

from main.caches import CacheKey, local_cache
from utils.strawberry.serializers import StringIDField


class UserResourceSerializer(serializers.ModelSerializer):
    modified_at = serializers.DateTimeField(read_only=True)
    modified_by = serializers.PrimaryKeyRelatedField(read_only=True)

    client_id = StringIDField(required=False)
    version_id = serializers.SerializerMethodField()

    def create(self, validated_data):
        if "created_by" in self.Meta.model._meta._forward_fields_map:  # type: ignore[reportAttributeAccessIssue]
            validated_data["created_by"] = self.context["request"].user
        if "modified_by" in self.Meta.model._meta._forward_fields_map:  # type: ignore[reportAttributeAccessIssue]
            validated_data["modified_by"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "modified_by" in self.Meta.model._meta._forward_fields_map:  # type: ignore[reportAttributeAccessIssue]
            validated_data["modified_by"] = self.context["request"].user
        return super().update(instance, validated_data)


class TempClientIdMixin(serializers.ModelSerializer):
    """
    ClientId for serializer level only, storing to database is optional (if field exists).
    """

    client_id = StringIDField(required=False)

    @staticmethod
    def get_cache_key(instance, request):
        return CacheKey.TEMP_CLIENT_ID_KEY_FORMAT.format(
            request_hash=hash(request),
            instance_type=type(instance).__name__,
            instance_id=instance.pk,
        )

    def create(self, validated_data):
        temp_client_id = validated_data.pop("client_id", None)
        instance = super().create(validated_data)
        if temp_client_id:
            instance.client_id = temp_client_id
            local_cache.set(self.get_cache_key(instance, self.context["request"]), temp_client_id, 60)
        return instance

    def update(self, instance, validated_data):
        temp_client_id = validated_data.pop("client_id", None)
        instance = super().update(instance, validated_data)
        if temp_client_id:
            instance.client_id = temp_client_id
            local_cache.set(self.get_cache_key(instance, self.context["request"]), temp_client_id, 60)
        return instance
