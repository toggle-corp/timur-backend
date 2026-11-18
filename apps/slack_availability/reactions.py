"""
Reactions Timur adds to the messages it reads

While a message is processed it has the seen reaction. When the run is done, the seen reaction is replaced by
the outcome of the run. Each reaction is a custom Timur emoji, or a native emoji when the workspace doesn't have
the custom one. Reaction errors are logged and never fail a run.
"""

import dataclasses
import enum
import logging

from django.core.cache import cache

from main.caches import CacheKey
from main.logging import log_extra
from utils.slack import TimurSlack

from .models import SlackAvailabilityRun
from .reconcile import ChangeAction

logger = logging.getLogger(__name__)

Status = SlackAvailabilityRun.Status
Trigger = SlackAvailabilityRun.Trigger

CUSTOM_EMOJI_CACHE_TTL = 60 * 60
# Retried sooner when emoji.list fails, e.g. while the emoji:read scope is missing
CUSTOM_EMOJI_FAILURE_CACHE_TTL = 60 * 5


@dataclasses.dataclass(frozen=True)
class Emoji:
    custom: str
    """Custom emoji uploaded to the workspace"""
    native: str
    """Built-in Slack emoji, used when the custom one is missing"""

    @property
    def names(self) -> tuple[str, str]:
        return (self.custom, self.native)


class Outcome(enum.StrEnum):
    APPLIED = "applied"
    NO_CHANGE = "no_change"
    NOT_ABOUT_AVAILABILITY = "not_about_availability"
    LOW_CONFIDENCE = "low_confidence"
    MANUAL_VALUE_KEPT = "manual_value_kept"
    STALE = "stale"
    FAILED = "failed"


SEEN_EMOJI = Emoji("timur-seen", "eyes")

OUTCOME_EMOJI: dict[Outcome, Emoji] = {
    Outcome.APPLIED: Emoji("timur-applied", "white_check_mark"),
    Outcome.NO_CHANGE: Emoji("timur-no-change", "heavy_minus_sign"),
    Outcome.NOT_ABOUT_AVAILABILITY: Emoji("timur-not-about", "see_no_evil"),
    Outcome.LOW_CONFIDENCE: Emoji("timur-unsure", "question"),
    Outcome.MANUAL_VALUE_KEPT: Emoji("timur-manual", "raised_hand"),
    Outcome.STALE: Emoji("timur-stale", "hourglass"),
    Outcome.FAILED: Emoji("timur-failed", "warning"),
}

OUTCOME_LABEL: dict[Outcome, str] = {
    Outcome.APPLIED: "Journal updated",
    Outcome.NO_CHANGE: "Read, nothing to change",
    Outcome.NOT_ABOUT_AVAILABILITY: "Not about leave or WFH",
    Outcome.LOW_CONFIDENCE: "Not sure enough, nothing changed",
    Outcome.MANUAL_VALUE_KEPT: "Kept a value set outside this thread",
    Outcome.STALE: "Skipped, the thread changed while I read it",
    Outcome.FAILED: "Failed",
}

# Planned changes where Timur leaves a value it does not own
KEPT_VALUE_ACTIONS = {ChangeAction.DROP.value, ChangeAction.SKIP.value}


def has_kept_values(planned_changes: dict) -> bool:
    """
    Timur left a value set outside the thread: a date the thread asks for, or one it wrote and that was changed since
    """
    return bool(planned_changes.get("kept")) or any(
        change.get("action") in KEPT_VALUE_ACTIONS for change in planned_changes.get("changes") or []
    )


def run_outcome(run: SlackAvailabilityRun) -> Outcome | None:
    """
    Outcome of a run, None for runs that only plan (shadow mode)

    A run whose Slack reply failed after its journal step has the error set and is a failure.
    """
    if run.error:
        return Outcome.FAILED
    return _status_outcome(run)


def _status_outcome(run: SlackAvailabilityRun) -> Outcome | None:
    if run.status in (Status.FAILED, Status.UNMAPPED_USER):
        return Outcome.FAILED
    if run.status == Status.STALE:
        return Outcome.STALE
    if run.status == Status.LOW_CONFIDENCE:
        return Outcome.LOW_CONFIDENCE
    if run.status == Status.APPLIED:
        return Outcome.APPLIED
    if run.status in (Status.NO_CHANGE, Status.NOT_ABOUT_AVAILABILITY) and has_kept_values(run.planned_changes or {}):
        return Outcome.MANUAL_VALUE_KEPT
    if run.status == Status.NOT_ABOUT_AVAILABILITY:
        return Outcome.NOT_ABOUT_AVAILABILITY
    if run.status == Status.NO_CHANGE:
        return Outcome.NO_CHANGE
    return None


def custom_emoji_names(slack: TimurSlack) -> set[str]:
    """
    Custom emoji names of the workspace, cached. Empty when Slack can't list them
    """
    names = cache.get(CacheKey.SLACK_CUSTOM_EMOJI_NAMES)
    if names is not None:
        return set(names)
    try:
        names = slack.fetch_custom_emoji_names()
        ttl = CUSTOM_EMOJI_CACHE_TTL
    except Exception:
        logger.warning("Failed to list Slack custom emojis, using native emojis", exc_info=True)
        names = set()
        ttl = CUSTOM_EMOJI_FAILURE_CACHE_TTL
    cache.set(CacheKey.SLACK_CUSTOM_EMOJI_NAMES, sorted(names), ttl)
    return names


def emoji_name(slack: TimurSlack, emoji: Emoji) -> str:
    return emoji.custom if emoji.custom in custom_emoji_names(slack) else emoji.native


def add_seen_reaction(slack: TimurSlack, channel_id: str, ts: str):
    slack.add_reaction(channel_id, ts, emoji_name(slack, SEEN_EMOJI))


def _remove_reactions(slack: TimurSlack, channel_id: str, ts: str, names: list[str], run: SlackAvailabilityRun):
    for name in names:
        try:
            slack.remove_reaction(channel_id, ts, name)
        except Exception:
            logger.warning(
                "Failed to remove Slack reaction",
                exc_info=True,
                extra=log_extra({"run_id": run.pk, "reaction": name}),
            )


def set_outcome_reaction(slack: TimurSlack, run: SlackAvailabilityRun):
    """
    Replace the seen reaction, and the outcome of earlier runs on the same message, with the outcome of the run

    Only live runs on a message that still exists get a reaction. A newer run on the same message sets its own.
    """
    if run.mode != "live" or run.trigger == Trigger.DELETE:
        return
    outcome = run_outcome(run)
    if outcome is None:
        return

    other_runs = list(
        SlackAvailabilityRun.objects.filter(thread_id=run.thread_id, trigger_ts=run.trigger_ts, mode=run.mode)
        .exclude(trigger=Trigger.DELETE)
        .exclude(pk=run.pk)
        .only("id", "status", "error", "planned_changes"),
    )
    if any(other_run.pk > run.pk for other_run in other_runs):
        return

    channel_id = run.thread.channel_id
    emoji = OUTCOME_EMOJI[outcome]
    # Includes the outcome of the run before its reply failed
    earlier_outcomes = {_status_outcome(run), *(run_outcome(other_run) for other_run in other_runs)}
    # Both names: the custom emoji can be added or removed in the workspace between two runs
    stale_names = [
        name
        for earlier_outcome in earlier_outcomes
        if earlier_outcome is not None and earlier_outcome != outcome
        for name in OUTCOME_EMOJI[earlier_outcome].names
    ]
    _remove_reactions(slack, channel_id, run.trigger_ts, [*SEEN_EMOJI.names, *stale_names], run)
    try:
        slack.add_reaction(channel_id, run.trigger_ts, emoji_name(slack, emoji))
    except Exception:
        logger.warning(
            "Failed to add Slack outcome reaction",
            exc_info=True,
            extra=log_extra({"run_id": run.pk, "outcome": outcome.value}),
        )
