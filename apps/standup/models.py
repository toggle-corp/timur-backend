import textwrap
import typing

from django.db import models
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from apps.common.models import UserResource
from apps.user.models import User


class Quote(UserResource):
    text = models.TextField()
    author = models.CharField(max_length=225)
    last_viewed = models.DateTimeField(null=True, blank=True)
    auto_select = models.BooleanField(
        default=True,
        help_text=_("Exclude from automatic selection. If false, it must be manually assigned to the DailyUserStandup."),
    )

    @classmethod
    def get_random(cls, track_last_viewed=False) -> typing.Self | None:
        obj = (
            cls.objects.filter(auto_select=True)
            .order_by(
                models.F("last_viewed").asc(nulls_first=True),
            )
            .first()
        )
        if obj and track_last_viewed:
            cls.objects.filter(pk=obj.pk).update(last_viewed=Now())
        return obj

    @typing.override
    def __str__(self):
        _text = textwrap.shorten(self.text, width=20, placeholder="...")
        return f"Quote: {self.author} - {_text}"


class StandupGatherAroundMedia(UserResource):
    """
    Used by ./tasks.py before_standup_reminder
    """

    url = models.URLField(help_text=_("Gif/Image to show during standup reminder"))
    caption = models.CharField(help_text=_("A short piece of text that describes the media"))
    last_viewed = models.DateTimeField(null=True, blank=True)
    auto_select = models.BooleanField(
        default=True,
        help_text=_("Exclude from automatic selection. If false, it must be manually assigned to the DailyUserStandup."),
    )

    class Meta(UserResource.Meta):
        verbose_name_plural = _("standup gather around media")

    @typing.override
    def __str__(self):
        return self.caption

    @classmethod
    def get_random(cls, track_last_viewed=False) -> typing.Self | None:
        obj = (
            cls.objects.filter(auto_select=True)
            .order_by(
                models.F("last_viewed").asc(nulls_first=True),
            )
            .first()
        )
        if obj and track_last_viewed:
            cls.objects.filter(pk=obj.pk).update(last_viewed=Now())
        return obj


# TODO: Add created_at, created_by, modified_by, modified_at
class DailyUserStandup(models.Model):
    date = models.DateField(unique=True)

    quote = models.ForeignKey(Quote, on_delete=models.SET_NULL, null=True, blank=True)
    gather_around_media = models.ForeignKey(StandupGatherAroundMedia, on_delete=models.SET_NULL, null=True, blank=True)

    conductor = models.ForeignKey(
        User,
        help_text=_("User responsible for conducting the stand-up"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    fallback_conductor = models.ForeignKey(
        User,
        help_text=_("Fallback user when conductor is not available"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    slack_thread_ts = models.CharField(max_length=20, null=True, blank=True)

    # typing hints
    quote_id: int | None
    gather_around_media_id: int | None
    conductor_id: int | None
    fallback_conductor_id: int | None

    @typing.override
    def __str__(self):
        return str(self.date)
