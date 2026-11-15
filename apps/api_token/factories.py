# pyright: reportPrivateImportUsage=false
# pyright: reportIncompatibleVariableOverride=false
import datetime
import typing

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.user.factories import UserFactory

from .models import ApiToken
from .scopes import ApiTokenScope


class ApiTokenFactory(DjangoModelFactory):
    """
    The plain-text token is available as `token.secret` on the created instance.
    """

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Token-{n}")
    scopes = factory.LazyFunction(lambda: [ApiTokenScope.TIME_ENTRY_READ.value])
    expires_at = factory.LazyFunction(lambda: timezone.now() + datetime.timedelta(days=30))

    class Meta:
        model = ApiToken

    @classmethod
    @typing.override
    def _create(cls, model_class, *args, **kwargs):
        secret = kwargs.pop("secret", None) or ApiToken.generate_secret()
        token = model_class(*args, **kwargs)
        token.set_secret(secret)
        token.save()
        token.secret = secret
        return token
