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

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="projects")
    contractor = models.ForeignKey(Contractor, on_delete=models.PROTECT, related_name="projects")

    client_id: int
    contractor_id: int

    def __str__(self):
        return self.name
