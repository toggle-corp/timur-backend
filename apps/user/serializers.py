from django.contrib.auth import authenticate
from rest_framework import serializers

from .validators import CustomMaximumLengthValidator


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate_password(self, password):
        # this will now only handle max-length in the login
        CustomMaximumLengthValidator().validate(password=password)
        return password

    def validate(self, attrs):
        # NOTE: authenticate only works for active users
        authenticate_user = authenticate(
            email=attrs["email"].lower(),
            password=attrs["password"],
        )
        # User doesn't exists in the system.
        if authenticate_user is None:
            raise serializers.ValidationError("No active account found with the given credentials")
        return {"user": authenticate_user}
