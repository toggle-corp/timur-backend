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
    name = models.CharField(max_length=225)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="deadlines")
    contract = models.ForeignKey(
        "track.Contract",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )

    is_archived = models.BooleanField(default=False)  # XXX: Is this useful?
    start_date = models.DateField()
    end_date = models.DateField()

    project_id: int
