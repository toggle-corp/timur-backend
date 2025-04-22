import typing

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import NotArchivedFilterIndex, UserResource


class Client(UserResource):
    name = models.CharField(max_length=225)

    def __str__(self):
        return self.name


class Contractor(UserResource):
    name = models.CharField(max_length=225)

    def __str__(self):
        return self.name


class Project(UserResource):
    name = models.CharField(max_length=225)
    short_name = models.CharField(max_length=10)
    description = models.TextField(blank=True)
    # TODO: Validate image size for optimal performance
    logo = models.ImageField(
        upload_to="project/logo/",
        help_text="Low quality logo.",
        max_length=255,
        blank=True,
        null=True,
    )
    logo_hd = models.ImageField(
        upload_to="project/logo-hd/",
        help_text="Hight quality logo",
        max_length=255,
        blank=True,
        null=True,
    )

    # NOTE: We use `client_id` for storing client context information temporary.
    # This may collide in future. So, using `project_client` instead of just `client`
    project_client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="projects")
    contractor = models.ForeignKey(Contractor, on_delete=models.PROTECT, related_name="projects")
    is_archived = models.BooleanField(default=False)
    slide_order = models.PositiveSmallIntegerField(
        default=0,
        help_text=_("Used to order projects in daily stand-up slides"),
    )

    project_client_id: int
    contractor_id: int

    class Meta:  # type: ignore [reportIncompatibleVariableOverride]
        indexes = [NotArchivedFilterIndex]

    def __str__(self):
        return self.name


class Deadline(UserResource):
    class GoogleCalendarSyncStatus(models.IntegerChoices):
        PENDING = 1, "Pending"
        SUCCESS = 2, "Success"
        FAILURE = 3, "Failure"

    name = models.CharField(max_length=225)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="deadlines")
    contract = models.ForeignKey(
        "track.Contract",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )

    is_archived = models.BooleanField(default=False)
    is_external = models.BooleanField(default=True, help_text=_("This is the deadline for clients"))
    start_date = models.DateField(help_text=_("This will be the date from which we need to start working."))
    end_date = models.DateField(help_text=_("This will be the date on which we need to deliver the work."))

    # Google calendar
    google_calendar_sync_status = models.PositiveSmallIntegerField(
        choices=GoogleCalendarSyncStatus.choices,
        default=GoogleCalendarSyncStatus.PENDING,
    )
    google_calendar_event_id = models.CharField(null=True, blank=True)
    google_calendar_html_link = models.URLField(null=True, blank=True)

    # Type hints
    project_id: int
    get_google_calendar_sync_status_display: typing.Callable[..., str]

    class Meta:  # type: ignore [reportIncompatibleVariableOverride]
        indexes = [NotArchivedFilterIndex]

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        from apps.project.tasks import delete_deadline_from_google_calendar

        # TODO(thenav56): Make this async with celery
        delete_deadline_from_google_calendar(self)
        return super().delete(*args, **kwargs)

    @property
    def display_name(self):
        # NOTE: Also defined in ./dataloaders.py (load_deadline_display_name)
        return f"{self.project.short_name}: {self.name}"

    def dates_check(self):
        if self.start_date > self.end_date:
            raise ValidationError(_("Start date can't be greater then End date"))

    def clean(self):
        super().clean()
        self.dates_check()
