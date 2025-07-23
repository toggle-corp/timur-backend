# from __future__ import annotations
import typing

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from .managers import CustomUserManager


class User(AbstractUser):
    class Department(models.IntegerChoices):
        # Using 4 digit for future ordering support
        DATA_ANALYST = 1000, _("Data Analyst")
        DESIGN = 1100, _("Design")
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
        blank=True,
        max_length=255,
    )
    display_picture = models.URLField(null=True, blank=True)
    department = models.PositiveSmallIntegerField(choices=Department.choices, null=True, blank=True)

    # TODO: This is a hacky way to exclude useres from standup slides, for better integration implement
    # support for custom teams with members & projects
    exclude_from_slides = models.BooleanField(default=False)

    slack_user_id = models.CharField(max_length=20, null=True, blank=True)
    assign_for_standup = models.BooleanField(default=True)

    objects: CustomUserManager = CustomUserManager()  # type: ignore[reportAssignmentType]

    pk: int

    @typing.override
    def __str__(self):
        return self.email or str(self.pk)

    @typing.override
    def save(self, *args, **kwargs):
        # Make sure email/username are same and lowercase
        self.email = self.email.lower()
        if self.pk is None:
            super().save(*args, **kwargs)
            # Remove force_insert since we have already inserted
            kwargs.pop("force_insert", None)
        self.display_name = self.get_full_name() or f"User#{self.pk}"
        return super().save(*args, **kwargs)

    @classmethod
    def get_active_user_qs(cls) -> models.QuerySet[typing.Self]:
        return cls.objects.filter(is_active=True)

    @classmethod
    def get_standup_slide_user_qs(cls) -> models.QuerySet[typing.Self]:
        return cls.get_active_user_qs().filter(exclude_from_slides=False)

    @classmethod
    def get_users_with_slack_user_id(cls) -> models.QuerySet[typing.Self]:
        return cls.get_active_user_qs().exclude(
            models.Q(slack_user_id__isnull=True) | models.Q(slack_user_id=""),
        )

    @classmethod
    def get_users_without_slack_user_id(cls) -> models.QuerySet[typing.Self]:
        return cls.get_active_user_qs().filter(
            models.Q(slack_user_id__isnull=True) | models.Q(slack_user_id=""),
        )
