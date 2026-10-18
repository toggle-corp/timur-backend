import datetime
import logging
import typing

from django.db import models, transaction
from django.utils import timezone
from slack_sdk.errors import SlackApiError

from apps.standup.models import DailyUserStandup
from apps.user.models import User
from main import config
from main.logging import log_extra
from utils.slack import TimurSlack

from .dates import ExpandedAvailability, expand_ranges, local_datetime_from_ts
from .events import SlackMessageEvent
from .guards import GuardResult, apply_guards
from .messages import StandupNote, StandupRole, build_reply, build_reply_blocks
from .models import SlackAvailabilityRun, SlackAvailabilityThread
from .parsers import AvailabilityParser, get_parser
from .reconcile import (
    JOURNAL_CHANGING_ACTIONS,
    MANUAL_VALUE_ACTIONS,
    ChangeAction,
    PlannedChange,
    apply_changes,
    load_journal_state,
    load_other_requests,
    plan_changes,
    serialize_desired,
)
from .structs import AvailabilityRange, MissingDetail, ThreadMessage, UnclearPart
from .trace import build_trace, has_viewable_trace

logger = logging.getLogger(__name__)


def with_end_date_questions(unclear: list[UnclearPart], ranges: list[AvailabilityRange]) -> list[UnclearPart]:
    """
    The unclear parts, plus an end-date question for an open-ended range the parser did not ask about
    """
    if any(part.missing == MissingDetail.END_DATE for part in unclear):
        return unclear
    open_ranges = [availability_range for availability_range in ranges if availability_range.open_end]
    if not open_ranges:
        return unclear
    return [*unclear, UnclearPart(open_ranges[0].source_phrase, MissingDetail.END_DATE)]


Status = SlackAvailabilityRun.Status

# Runs below this parser confidence change nothing
MIN_CONFIDENCE = 0.5


class Reaction:
    SEEN = "eyes"
    DONE = "white_check_mark"
    FAILED = "warning"


def _is_thread_message(message: dict, slack_user_id: str) -> bool:
    return message.get("user") == slack_user_id and not message.get("bot_id") and message.get("subtype") != "tombstone"


class AvailabilityProcessor:
    """
    Turn a Slack thread into journal changes for its author
    """

    def __init__(
        self,
        slack: TimurSlack,
        parser_factory: typing.Callable[[], AvailabilityParser] = get_parser,
    ):
        self.slack = slack
        self.parser_factory = parser_factory
        self.config = config.SlackAvailability.load_config()

    @property
    def is_live(self) -> bool:
        return self.config.is_live

    def react(self, event: SlackMessageEvent, name: str):
        if self.is_live and event.trigger_ts:
            self.slack.add_reaction(event.channel_id, event.trigger_ts, name)

    def resolve_user(self, slack_user_id: str) -> User | None:
        """
        Return the active user linked to the Slack user, linking by email when no user holds the Slack id

        An existing link is never changed: None when the id belongs to an inactive user or
        the email matches a user linked to another Slack id.
        """
        linked_users = list(User.objects.filter(slack_user_id=slack_user_id)[:2])
        if linked_users:
            if len(linked_users) == 1 and linked_users[0].is_active:
                return linked_users[0]
            return None

        email = self.slack.fetch_user_email(slack_user_id)
        if not email:
            return None
        user = User.get_active_user_qs().filter(email__iexact=email).first()
        if user is None:
            return None
        if user.slack_user_id:
            return None
        user.slack_user_id = slack_user_id
        user.save(update_fields=("slack_user_id",))
        return user

    def fetch_thread_messages(self, event: SlackMessageEvent) -> list[dict]:
        return self.slack.fetch_thread_messages(event.channel_id, event.thread_ts)

    def process(self, event: SlackMessageEvent) -> SlackAvailabilityRun | None:
        """
        Plan and apply journal changes for the event

        Slack and parser calls run outside database transactions. The thread's journal step runs in a short
        transaction that skips the run when a newer read of the thread was already applied.
        The DONE reaction and the thread reply are sent separately by notify(), after the journal is committed.
        """
        if event.is_parent_deleted:
            return self.process_parent_deleted(event)

        snapshot_at = timezone.now()
        messages = self.fetch_thread_messages(event)
        if not messages or messages[0].get("ts") != event.thread_ts:
            return None
        parent = messages[0]
        if not _is_thread_message(parent, parent.get("user") or ""):
            return None
        # Only the author of the top-level message changes the thread
        if event.slack_user_id != parent["user"]:
            return None

        try:
            self.react(event, Reaction.SEEN)
        except SlackApiError:
            logger.warning(
                "Failed to add seen reaction",
                exc_info=True,
                extra=log_extra({"thread_ts": event.thread_ts, "trigger_ts": event.trigger_ts}),
            )

        user = self.resolve_user(event.slack_user_id)
        if user is None:
            return self.process_unmapped_user(event)

        return self.process_thread(event, user, messages, snapshot_at)

    def _get_thread(self, event: SlackMessageEvent, user: User | None) -> SlackAvailabilityThread:
        thread, _ = SlackAvailabilityThread.objects.get_or_create(
            channel_id=event.channel_id,
            thread_ts=event.thread_ts,
            defaults={"slack_user_id": event.slack_user_id, "user": user},
        )
        return thread

    def _today(self, event: SlackMessageEvent) -> datetime.date:
        return local_datetime_from_ts(event.event_ts).date()

    def process_unmapped_user(self, event: SlackMessageEvent) -> SlackAvailabilityRun:
        self.react(event, Reaction.FAILED)
        logger.error(
            "Slack user is not linked to an active Timur user",
            extra=log_extra({"slack_user_id": event.slack_user_id, "thread_ts": event.thread_ts}),
        )
        return SlackAvailabilityRun.objects.create(
            thread=self._get_thread(event, None),
            mode=self.config.mode,
            trigger=event.trigger,
            trigger_ts=event.trigger_ts or event.event_ts,
            status=Status.UNMAPPED_USER,
            today=self._today(event),
        )

    def process_parent_deleted(self, event: SlackMessageEvent) -> SlackAvailabilityRun | None:
        with transaction.atomic():
            thread = (
                SlackAvailabilityThread.objects.select_for_update()
                .filter(channel_id=event.channel_id, thread_ts=event.thread_ts)
                .first()
            )
            if thread is None:
                return None
            thread.is_deleted = True
            thread.desired_state = {}
            thread.save(update_fields=("is_deleted", "desired_state", "modified_at"))
            if thread.user is None:
                return None

            today = self._today(event)
            current, owned = load_journal_state(thread.user, thread, dates=set())
            changes = plan_changes(
                thread_id=thread.pk,
                today=today,
                desired={},
                current=current,
                owned=owned,
                other_requests=load_other_requests(thread.user, thread, today),
            )
            if self.is_live:
                apply_changes(thread.user, thread, changes)
            return SlackAvailabilityRun.objects.create(
                thread=thread,
                mode=self.config.mode,
                trigger=event.trigger,
                trigger_ts=event.deleted_ts or event.event_ts,
                status=self._status(changes),
                today=today,
                planned_changes={"changes": [change.as_dict() for change in changes]},
            )

    def _status(self, changes: list[PlannedChange]) -> int:
        if not self.is_live:
            return Status.PLANNED
        if any(change.action in JOURNAL_CHANGING_ACTIONS for change in changes):
            return Status.APPLIED
        return Status.NO_CHANGE

    def _standup_notes(self, user: User, changes: list[PlannedChange]) -> list[StandupNote]:
        dates = [
            change.date
            for change in changes
            if change.action in (ChangeAction.ADD, ChangeAction.UPDATE) and change.after.blocks_first_half
        ]
        if not dates:
            return []
        notes = []
        for standup in (
            DailyUserStandup.objects.filter(date__in=dates)
            .filter(models.Q(conductor=user) | models.Q(fallback_conductor=user))
            .select_related("conductor", "fallback_conductor")
            .order_by("date")
        ):
            if standup.conductor_id == user.pk:
                fallback_conductor = standup.fallback_conductor
                notes.append(
                    StandupNote(
                        date=standup.date,
                        role=StandupRole.CONDUCTOR,
                        other_slack_user_id=fallback_conductor and fallback_conductor.slack_user_id,
                    ),
                )
            else:
                conductor = standup.conductor
                notes.append(
                    StandupNote(
                        date=standup.date,
                        role=StandupRole.FALLBACK_CONDUCTOR,
                        other_slack_user_id=conductor and conductor.slack_user_id,
                    ),
                )
        return notes

    @staticmethod
    def _notice_key(planned_changes: dict) -> tuple:
        """
        What the user was already told about dates they set themselves and unclear dates
        """
        return (
            sorted(
                change["date"] for change in planned_changes.get("changes", []) if change["action"] in MANUAL_VALUE_ACTIONS
            ),
            sorted(planned_changes.get("unknown_half_dates", [])),
            sorted(planned_changes.get("unclear", [])),
        )

    def _should_reply(
        self,
        thread: SlackAvailabilityThread,
        changes: list[PlannedChange],
        planned_changes: dict,
    ) -> bool:
        if any(change.action in JOURNAL_CHANGING_ACTIONS for change in changes):
            return True
        notice_key = self._notice_key(planned_changes)
        if not any(notice_key):
            return False
        # Only replies that reached Slack count as told
        previous_run = thread.runs.exclude(reply_ts="").order_by("-id").first()
        return previous_run is None or self._notice_key(previous_run.planned_changes) != notice_key

    def process_thread(
        self,
        event: SlackMessageEvent,
        user: User,
        raw_messages: list[dict],
        snapshot_at: datetime.datetime,
    ) -> SlackAvailabilityRun:
        today = self._today(event)
        thread = self._get_thread(event, user)
        messages = [
            ThreadMessage(
                ts=message["ts"],
                posted_at=local_datetime_from_ts(message["ts"]),
                text=message.get("text") or "",
            )
            for message in raw_messages
            if _is_thread_message(message, event.slack_user_id)
        ]
        parse_result = self.parser_factory().parse(messages, today)

        run = SlackAvailabilityRun(
            thread=thread,
            mode=self.config.mode,
            trigger=event.trigger,
            trigger_ts=event.trigger_ts or event.deleted_ts or event.event_ts,
            today=today,
            llm_input=parse_result.prompt,
            llm_model=parse_result.model,
            llm_output=parse_result.raw,
        )

        if parse_result.is_about_availability:
            # Low confidence changes nothing, and keeps what earlier runs wrote
            if parse_result.confidence < MIN_CONFIDENCE:
                run.status = Status.LOW_CONFIDENCE
                run.trace = build_trace(
                    messages=messages,
                    parse_result=parse_result,
                    today=today,
                    changes=None,
                    unknown_half_dates=[],
                    unclear=[],
                    low_confidence=True,
                )
                run.save()
                return run
            guard_result = apply_guards(parse_result.ranges, messages)
            expanded = expand_ranges(guard_result.ranges, today)
            unclear = with_end_date_questions(parse_result.unclear, guard_result.ranges)
        else:
            # The thread asks for nothing: what earlier runs wrote is reverted
            guard_result = GuardResult(ranges=[], ignored=[], corrections=[])
            expanded = ExpandedAvailability(desired={}, unknown_half_dates=[], invalid_ranges=[])
            unclear = []

        with transaction.atomic():
            thread = SlackAvailabilityThread.objects.select_for_update().get(pk=thread.pk)
            run.thread = thread
            # The thread was deleted, or a run that read the thread later already reached this step
            if thread.is_deleted or (thread.snapshot_at is not None and snapshot_at < thread.snapshot_at):
                run.status = Status.STALE
                run.save()
                return run

            changes = self._plan(thread, user, today, expanded)
            standup_notes = self._standup_notes(user, changes)
            planned_changes = self._planned_changes(changes, expanded, unclear, standup_notes, guard_result)

            reply_text = None
            if self._should_reply(thread, changes, planned_changes):
                reply_text = build_reply(
                    slack_user_id=event.slack_user_id,
                    changes=changes,
                    unknown_half_dates=expanded.unknown_half_dates,
                    unclear=unclear,
                    standup_notes=standup_notes,
                    llm_model=parse_result.model,
                    needs_care=parse_result.needs_care and parse_result.is_about_availability,
                )

            run.status = self._status(changes)
            if not parse_result.is_about_availability and run.status == Status.NO_CHANGE:
                run.status = Status.NOT_ABOUT_AVAILABILITY
            run.planned_changes = planned_changes
            run.reply_text = reply_text or ""
            run.trace = build_trace(
                messages=messages,
                parse_result=parse_result,
                today=today,
                changes=changes,
                unknown_half_dates=expanded.unknown_half_dates,
                unclear=unclear,
                guard_result=guard_result,
            )

            thread.user = user
            thread.slack_user_id = event.slack_user_id
            thread.snapshot_at = snapshot_at
            if self.is_live:
                apply_changes(user, thread, changes)
                thread.desired_state = {
                    # Held-back dates keep what the thread asked for before
                    **{
                        date.isoformat(): thread.desired_state[date.isoformat()]
                        for date in expanded.unknown_half_dates
                        if date.isoformat() in thread.desired_state
                    },
                    **serialize_desired(expanded.desired),
                }
            thread.save(update_fields=("user", "slack_user_id", "snapshot_at", "desired_state", "modified_at"))
            run.save()
            return run

    def notify(self, run: SlackAvailabilityRun):
        """
        Send the DONE reaction and the thread reply of a committed run

        Safe to call again: reactions are idempotent and the reply is sent once per run.
        """
        thread = run.thread
        # The thread is gone once its top-level message is deleted
        if run.mode != "live" or thread.is_deleted:
            return
        # A deleted reply has no message to react on
        if run.status == Status.APPLIED and run.trigger != SlackAvailabilityRun.Trigger.DELETE:
            self.slack.add_reaction(thread.channel_id, run.trigger_ts, Reaction.DONE)
        if run.reply_text and not run.reply_ts:
            response = self.slack.send_slack_message(
                # Shown in notifications, and by clients that can't render blocks
                text=run.reply_text,
                blocks=build_reply_blocks(run.reply_text, run.pk) if has_viewable_trace(run.trace) else None,
                thread_ts=thread.thread_ts,
                channel=thread.channel_id,
            )
            run.reply_ts = response.get("ts") or ""
            run.save(update_fields=("reply_ts",))

    def _plan(
        self,
        thread: SlackAvailabilityThread,
        user: User,
        today: datetime.date,
        expanded: ExpandedAvailability,
    ) -> list[PlannedChange]:
        current, owned = load_journal_state(user, thread, dates=set(expanded.desired.keys()))
        return plan_changes(
            thread_id=thread.pk,
            today=today,
            desired=expanded.desired,
            current=current,
            owned=owned,
            other_requests=load_other_requests(user, thread, today),
            held_dates=set(expanded.unknown_half_dates),
        )

    @staticmethod
    def _planned_changes(
        changes: list[PlannedChange],
        expanded: ExpandedAvailability,
        unclear: list[UnclearPart],
        standup_notes: list[StandupNote],
        guard_result: GuardResult,
    ) -> dict:
        return {
            "changes": [change.as_dict() for change in changes],
            "unknown_half_dates": [date.isoformat() for date in expanded.unknown_half_dates],
            "unclear": [part.phrase for part in unclear],
            "invalid_ranges": [
                {
                    "start_date": availability_range.start_date.isoformat(),
                    "end_date": availability_range.end_date.isoformat(),
                    "leave": availability_range.leave,
                    "wfh": availability_range.wfh,
                }
                for availability_range in expanded.invalid_ranges
            ],
            "standup": [
                {"date": note.date.isoformat(), "role": note.role.value, "other_slack_user_id": note.other_slack_user_id}
                for note in standup_notes
            ],
            # Dates and types only: phrases are in the trace, which the retention purge blanks
            "guards": {
                "ignored": [
                    {
                        "start_date": ignored.availability_range.start_date.isoformat(),
                        "end_date": ignored.availability_range.end_date.isoformat(),
                        "reason": ignored.kind.value,
                    }
                    for ignored in guard_result.ignored
                ],
                "corrected": [
                    {
                        "kind": correction.kind.value,
                        "before": [correction.before.start_date.isoformat(), correction.before.end_date.isoformat()],
                        "after": [
                            guard_result.ranges[correction.index].start_date.isoformat(),
                            guard_result.ranges[correction.index].end_date.isoformat(),
                        ],
                    }
                    for correction in guard_result.corrections
                ],
            },
        }


def mark_notify_failed(slack: TimurSlack | None, run: SlackAvailabilityRun, error: BaseException):
    """
    Record a run whose Slack reaction or reply failed after all retries

    The journal changes of the run stay applied.
    """
    logger.error(
        "Failed to notify Slack about availability run",
        exc_info=error,
        extra=log_extra({"run_id": run.pk, "thread_id": run.thread_id}),
    )
    if slack is not None:
        try:
            slack.add_reaction(run.thread.channel_id, run.trigger_ts, Reaction.FAILED)
        except Exception:
            logger.error("Failed to add failure reaction", exc_info=True)
    run.error = repr(error)
    run.save(update_fields=("error",))


def mark_event_failed(slack: TimurSlack | None, event: SlackMessageEvent, error: BaseException):
    """
    Record a run that failed after all retries
    """
    logger.error(
        "Failed to process Slack availability event",
        exc_info=error,
        extra=log_extra({"thread_ts": event.thread_ts, "trigger_ts": event.trigger_ts}),
    )
    availability_config = config.SlackAvailability.load_config()
    if slack is not None and availability_config.is_live and event.trigger_ts:
        try:
            slack.add_reaction(event.channel_id, event.trigger_ts, Reaction.FAILED)
        except Exception:
            logger.error("Failed to add failure reaction", exc_info=True)

    thread, _ = SlackAvailabilityThread.objects.get_or_create(
        channel_id=event.channel_id,
        thread_ts=event.thread_ts,
        defaults={"slack_user_id": event.slack_user_id},
    )
    SlackAvailabilityRun.objects.create(
        thread=thread,
        mode=availability_config.mode,
        trigger=event.trigger,
        trigger_ts=event.trigger_ts or event.event_ts,
        status=Status.FAILED,
        today=local_datetime_from_ts(event.event_ts).date(),
        error=repr(error),
    )
