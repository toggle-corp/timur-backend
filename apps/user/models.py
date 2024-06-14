# from __future__ import annotations
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from .managers import CustomUserManager


class User(AbstractUser):
    EMAIL_FIELD = USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    username = None
    email = models.EmailField(unique=True)
    invalid_email = models.BooleanField(default=False, help_text=_("Is Bounced email?"))
    display_name = models.CharField(
        verbose_name=_("system generated user display name"),
        blank=True,
        max_length=255,
    )

    objects = CustomUserManager()  # type: ignore[reportAssignmentType]

    pk: int

    def save(self, *args, **kwargs):
        # Make sure email/username are same and lowercase
        self.email = self.email.lower()
        self.display_name = self.get_full_name() or f"User#{self.pk}"
        return super().save(*args, **kwargs)
