from django.db import models

from apps.common.models import UserResource


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
    logo = models.ImageField(
        upload_to="project/logo/",
        max_length=255,
        blank=True,
        null=True,
    )

    # NOTE: We use `client_id` for storing client context information temporary.
    # This may collide in future. So, using `project_client` instead of just `client`
    project_client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="projects")
    contractor = models.ForeignKey(Contractor, on_delete=models.PROTECT, related_name="projects")
    is_archived = models.BooleanField(default=False)

    project_client_id: int
    contractor_id: int

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

    is_archived = models.BooleanField(default=False)
    start_date = models.DateField()
    end_date = models.DateField()

    project_id: int
