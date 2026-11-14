import datetime
import typing

from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers

from .models import ApiToken
from .scopes import with_implied_scopes


class ApiTokenCreateSerializer(serializers.ModelSerializer):
    MAX_ACTIVE_TOKENS_PER_USER = 10
    MIN_EXPIRY = datetime.timedelta(hours=1)
    # One year plus two days: the end of the local day one year ahead fits in every timezone,
    # with room for a client clock that runs ahead
    MAX_EXPIRY = datetime.timedelta(days=367)

    # A value without an offset is read as UTC
    expires_at = serializers.DateTimeField(default_timezone=datetime.UTC)

    class Meta:  # type: ignore[reportIncompatibleVariableOverride]
        model = ApiToken
        fields = (
            "name",
            "scopes",
            "expires_at",
        )
        extra_kwargs = {
            "scopes": {"required": True},
        }

    def _active_tokens_qs(self):
        return ApiToken.objects.active().filter(user=self.context["request"].user)

    def validate_name(self, name: str) -> str:
        name = name.strip()
        if not name:
            raise serializers.ValidationError(gettext("Name is required."))
        if not name.isprintable():
            raise serializers.ValidationError(gettext("Name can't contain line breaks or control characters."))
        if self._active_tokens_qs().filter(name__iexact=name).exists():
            raise serializers.ValidationError(gettext("An active token with this name already exists."))
        return name

    def validate_scopes(self, scopes: list[str]) -> list[str]:
        if not scopes:
            raise serializers.ValidationError(gettext("Select at least one scope."))
        # Stored explicitly so the token list shows the read scope that comes with a write scope
        return sorted(with_implied_scopes(scopes))

    def validate_expires_at(self, expires_at: datetime.datetime) -> datetime.datetime:
        now = timezone.now()
        if expires_at <= now + self.MIN_EXPIRY:
            raise serializers.ValidationError(gettext("Expiry must be more than 1 hour from now."))
        if expires_at > now + self.MAX_EXPIRY:
            raise serializers.ValidationError(gettext("Expiry can be at most 1 year from now."))
        return expires_at.astimezone(datetime.UTC)

    @typing.override
    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self._active_tokens_qs().count() >= self.MAX_ACTIVE_TOKENS_PER_USER:
            raise serializers.ValidationError(
                gettext("You can have at most %(count)d active tokens. Revoke one first.")
                % {"count": self.MAX_ACTIVE_TOKENS_PER_USER},
            )
        return attrs

    @typing.override
    def create(self, validated_data):
        secret = ApiToken.generate_secret()
        token = ApiToken(user=self.context["request"].user, **validated_data)
        token.set_secret(secret)
        token.save()
        # Transient: only returned in the create mutation response
        token.secret = secret  # type: ignore[reportAttributeAccessIssue]
        return token
