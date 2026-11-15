import datetime
import hashlib
import secrets
import string
import typing

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.user.models import User

from .scopes import ApiTokenScope


class ApiTokenManager(models.Manager["ApiToken"]):
    def active(self, now: datetime.datetime | None = None) -> models.QuerySet["ApiToken"]:
        now = now or timezone.now()
        return self.filter(revoked_at__isnull=True, expires_at__gt=now)


class ApiToken(models.Model):
    SECRET_PREFIX = "tc_timur_"
    SECRET_RANDOM_LENGTH = 40
    SECRET_ALPHABET = string.ascii_letters + string.digits
    PREFIX_LENGTH = 8

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        EXPIRED = "expired", _("Expired")
        REVOKED = "revoked", _("Revoked")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=100)
    prefix = models.CharField(
        max_length=PREFIX_LENGTH,
        help_text=_("First characters of the random part of the token, used to identify it"),
    )
    hash = models.CharField(max_length=64, unique=True, help_text=_("SHA-256 of the token"))
    scopes = ArrayField(
        models.CharField(max_length=32, choices=ApiTokenScope.choices),
        default=list,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    expiry_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    expired_notice_sent_at = models.DateTimeField(null=True, blank=True)

    objects: ApiTokenManager = ApiTokenManager()  # type: ignore[reportAssignmentType]

    user_id: int
    pk: int

    class Meta:  # type: ignore[reportIncompatibleVariableOverride]
        ordering = ("-created_at", "-id")

    @typing.override
    def __str__(self):
        return f"{self.name} ({self.prefix})"

    # Secret helpers
    @staticmethod
    def hash_secret(secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    @classmethod
    def generate_secret(cls) -> str:
        random_part = "".join(secrets.choice(cls.SECRET_ALPHABET) for _ in range(cls.SECRET_RANDOM_LENGTH))
        return f"{cls.SECRET_PREFIX}{random_part}"

    def set_secret(self, secret: str):
        self.prefix = secret[len(self.SECRET_PREFIX) :][: self.PREFIX_LENGTH]
        self.hash = self.hash_secret(secret)

    # State
    def get_status(self, now: datetime.datetime | None = None) -> "ApiToken.Status":
        now = now or timezone.now()
        if self.revoked_at is not None:
            return self.Status.REVOKED
        if self.expires_at <= now:
            return self.Status.EXPIRED
        return self.Status.ACTIVE
