from django.db import models

from apps.user.models import User


class UserResource(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        related_name="%(class)s_created",
        on_delete=models.PROTECT,
    )
    modified_by = models.ForeignKey(
        User,
        related_name="%(class)s_modified",
        on_delete=models.PROTECT,
    )

    # Typing
    id: int
    pk: int
    created_by_id: int
    modified_by_id: int

    class Meta:  # type: ignore[reportIncompatibleVariableOverride]
        abstract = True
        ordering = ["-id"]


class Event(models.Model):
    class Type(models.IntegerChoices):
        HOLIDAY = 1, "Holiday"
        RETREAT = 2, "Retreat"
        MISC = 3, "Misc"

    name = models.CharField(max_length=225)
    date = models.DateField()
    type = models.PositiveSmallIntegerField(choices=Type.choices, default=Type.HOLIDAY)
