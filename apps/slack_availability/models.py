import typing

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.journal.models import Journal
from apps.user.models import User


class SlackAvailabilityThread(models.Model):
    """
    A top-level message in the availability channel, together with its replies
    """

    channel_id = models.CharField(max_length=32)
    thread_ts = models.CharField(max_length=32)
    slack_user_id = models.CharField(max_length=32, help_text=_("Slack user who posted the top-level message"))
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    is_deleted = models.BooleanField(default=False, help_text=_("Top-level message is deleted in Slack"))
    snapshot_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the Slack thread was read for the latest run that reached the journal step"),
    )
    desired_state = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Leave/WFH the thread asks for, by ISO date, as of the latest applied run"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    # Typing
    id: int
    pk: int
    user_id: int | None
    runs: models.QuerySet["SlackAvailabilityRun"]
    journal_entries: models.QuerySet["SlackAvailabilityJournalEntry"]

    class Meta:  # type: ignore[reportIncompatibleVariableOverride]
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["channel_id", "thread_ts"], name="slack_availability_unique_thread"),
        ]

    @typing.override
    def __str__(self):
        return f"{self.channel_id}#{self.thread_ts}"


class SlackAvailabilityRun(models.Model):
    """
    One processing of a thread, triggered by a Slack event
    """

    class Status(models.IntegerChoices):
        APPLIED = 1, _("Applied")
        PLANNED = 2, _("Planned (shadow)")
        NO_CHANGE = 3, _("No change")
        UNMAPPED_USER = 4, _("Unmapped user")
        FAILED = 5, _("Failed")
        LOW_CONFIDENCE = 6, _("Low confidence")
        STALE = 7, _("Stale (thread changed since it was read)")
        NOT_ABOUT_AVAILABILITY = 8, _("Not about the poster's availability")

    class Trigger(models.TextChoices):
        MESSAGE = "message", _("New message")
        REPLY = "reply", _("Thread reply")
        EDIT = "edit", _("Edit")
        DELETE = "delete", _("Delete")

    thread = models.ForeignKey(SlackAvailabilityThread, on_delete=models.CASCADE, related_name="runs")
    mode = models.CharField(max_length=10)
    trigger = models.CharField(max_length=10, choices=Trigger.choices)
    trigger_ts = models.CharField(max_length=32)
    status = models.PositiveSmallIntegerField(choices=Status.choices)
    today = models.DateField(help_text=_("Date of the Slack event, in the app timezone"))

    llm_input = models.TextField(
        blank=True,
        help_text=_("Thread text sent to the parser. Purged after the retention period"),
    )
    purged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When message-derived text (input, unclear and quoted phrases, trace, reply, error) was blanked"),
    )
    llm_model = models.CharField(max_length=255, blank=True)
    llm_output = models.JSONField(null=True, blank=True)
    planned_changes = models.JSONField(default=dict, blank=True)
    trace = models.JSONField(
        null=True,
        blank=True,
        help_text=_("Steps of the run shown to the poster in Slack (see trace.py). Message text is purged"),
    )
    reply_text = models.TextField(blank=True)
    reply_ts = models.CharField(max_length=32, blank=True)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # Typing
    id: int
    pk: int
    thread_id: int
    get_status_display: typing.Callable[..., str]

    class Meta:  # type: ignore[reportIncompatibleVariableOverride]
        ordering = ["-id"]

    @typing.override
    def __str__(self):
        return f"{self.thread_id}#{self.pk} ({self.get_status_display()})"


class SlackAvailabilityJournalEntry(models.Model):
    """
    Journal values written by Timur from a thread

    Timur owns a journal's leave/wfh values while they still equal the values recorded here
    """

    journal = models.OneToOneField(Journal, on_delete=models.CASCADE, related_name="+")
    thread = models.ForeignKey(SlackAvailabilityThread, on_delete=models.CASCADE, related_name="journal_entries")
    leave_type = models.PositiveSmallIntegerField(null=True, blank=True, choices=Journal.LeaveType.choices)
    wfh_type = models.PositiveSmallIntegerField(null=True, blank=True, choices=Journal.WorkFromHomeType.choices)

    modified_at = models.DateTimeField(auto_now=True)

    # Typing
    id: int
    pk: int
    journal_id: int
    thread_id: int

    @typing.override
    def __str__(self):
        return f"{self.thread_id}#{self.journal_id}"
