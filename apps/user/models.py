# from __future__ import annotations
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from .managers import CustomUserManager


class User(AbstractUser):
    class Department(models.IntegerChoices):
        # Using 4 digit for future ordering support
        DATA_ANALYST = 1000, _("Data Analyst")
        DESIGN = 1100, _("Development")
        DEVELOPMENT = 1200, _("Development")
        MANAGEMENT = 2000, _("Management")
        PROJECT_MANAGER = 3000, _("Project Manager")
        QUALITY_ASSURANCE = 5000, _("QA")

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
    department = models.PositiveSmallIntegerField(choices=Department.choices)

    objects = CustomUserManager()  # type: ignore[reportAssignmentType]

    pk: int

    def save(self, *args, **kwargs):
        # Make sure email/username are same and lowercase
        self.email = self.email.lower()
        if self.pk is None:
            super().save(*args, **kwargs)
        self.display_name = self.get_full_name() or f"User#{self.pk}"
        return super().save(*args, **kwargs)
