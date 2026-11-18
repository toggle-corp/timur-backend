import datetime
import json
import logging

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from slack_sdk.signature import SignatureVerifier

from apps.user.models import User
from main import config
from main.caches import CacheKey
from main.logging import log_extra
from utils.slack import TimurSlack

from .dates import local_datetime_from_ts
from .events import classify_event
from .history import history_lines
from .messages import WHY_ACTION_ID, WHY_SHORTCUT_CALLBACK_ID
from .models import SlackAvailabilityRun, SlackAvailabilityThread
from .reactions import OUTCOME_EMOJI, OUTCOME_LABEL, run_outcome
from .tasks import process_slack_availability_event
from .trace import build_notice_view, build_trace_view, has_viewable_trace

logger = logging.getLogger(__name__)

EVENT_DEDUPE_TTL = 60 * 60 * 24

AvailabilityConfig = config.SlackAvailability.SlackAvailabilityConfig


@csrf_exempt
@require_POST
def slack_events(request: HttpRequest) -> HttpResponse:
    """
    Slack Events API endpoint
    https://docs.slack.dev/apis/events-api/
    """
    availability_config = config.SlackAvailability.load_config()
    if not availability_config.signing_secret:
        return HttpResponse()

    verifier = SignatureVerifier(availability_config.signing_secret)
    if not verifier.is_valid_request(request.body, dict(request.headers)):
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)

    # Answered in every mode, so the request URL can be set in Slack before the feature is turned on
    if payload.get("type") == "url_verification":
        return JsonResponse({"challenge": payload.get("challenge")})

    if availability_config.is_off or payload.get("type") != "event_callback" or not availability_config.channel_id:
        return HttpResponse()

    message_event = classify_event(payload.get("event") or {}, availability_config.channel_id)
    if message_event is None:
        return HttpResponse()

    # Slack retries events it considers undelivered
    event_id = payload.get("event_id")
    dedupe_key = event_id and CacheKey.SLACK_EVENT_ID_FORMAT.format(event_id)
    if dedupe_key and not cache.add(dedupe_key, 1, EVENT_DEDUPE_TTL):
        return HttpResponse()

    try:
        process_slack_availability_event.delay(message_event.as_dict())
    except Exception:
        # Let Slack's retry of this event through
        if dedupe_key:
            cache.delete(dedupe_key)
        raise
    return HttpResponse()


def _is_timur_admin(slack_user_id: str | None) -> bool:
    """
    The Slack user is linked to an active Timur superuser
    """
    if not slack_user_id:
        return False
    return User.get_active_user_qs().filter(slack_user_id=slack_user_id, is_superuser=True).exists()


def _outcome_text(run: SlackAvailabilityRun) -> str:
    outcome = run_outcome(run)
    if outcome is None:
        return run.get_status_display()
    return f":{OUTCOME_EMOJI[outcome].native}: {OUTCOME_LABEL[outcome]}"


def _why_view(
    run: SlackAvailabilityRun | None,
    slack_user_id: str | None,
    retention_days: int,
    slack: TimurSlack,
) -> dict:
    if run is None:
        return build_notice_view("I couldn't find the details of this reply.")
    # The trace shows the poster's journal
    if slack_user_id != run.thread.slack_user_id and not _is_timur_admin(slack_user_id):
        return build_notice_view("Only the person who posted (or a Timur admin) can view this.")
    if not has_viewable_trace(run.trace):
        return build_notice_view(f"Details expired after {retention_days} days.")
    return build_trace_view(run.trace, outcome=_outcome_text(run), history=history_lines(run, slack))


def _is_bot_message(message: dict) -> bool:
    return bool(message.get("bot_id")) or message.get("subtype") == "bot_message" or not message.get("user")


def _no_run_reason(message: dict, thread: SlackAvailabilityThread | None, retention_days: int) -> str:
    if thread is not None and thread.is_deleted:
        return "The first message of this thread was deleted, so Timur stopped reading it."
    if thread is not None and message.get("user") != thread.slack_user_id:
        return "Timur only reads messages from the person who started the thread."
    try:
        posted_at = local_datetime_from_ts(message.get("ts") or "")
    except ValueError:
        posted_at = None
    if posted_at is not None and posted_at < timezone.now() - datetime.timedelta(days=retention_days):
        return f"Timur keeps the details of a message for {retention_days} days, and this message is older."
    return (
        "Timur has no record of reading this message. It reads new messages and replies from the person who started"
        " the thread."
    )


def _shortcut_view(payload: dict, availability_config: AvailabilityConfig, slack: TimurSlack) -> dict:
    """
    View for the "Why did Timur do this?" message shortcut: the latest run triggered by the message, or why there
    is none

    A run is triggered by the message, or for a top-level message, by any message of its thread.
    """
    if availability_config.is_off:
        return build_notice_view("Timur isn't reading availability messages right now.")
    channel_id = (payload.get("channel") or {}).get("id")
    if not availability_config.channel_id or channel_id != availability_config.channel_id:
        return build_notice_view(f"Timur only reads messages in <#{availability_config.channel_id}>.")
    message = payload.get("message") or {}
    if _is_bot_message(message):
        return build_notice_view("Timur doesn't read messages from bots or apps.")
    slack_user_id = (payload.get("user") or {}).get("id")
    if slack_user_id != message["user"] and not _is_timur_admin(slack_user_id):
        return build_notice_view("Only the author of the message or a Timur admin can view this.")

    ts = message.get("ts") or payload.get("message_ts") or ""
    thread_ts = message.get("thread_ts") or ts
    thread = SlackAvailabilityThread.objects.filter(channel_id=channel_id, thread_ts=thread_ts).first()
    run = None
    if thread is not None:
        runs = thread.runs.exclude(trigger=SlackAvailabilityRun.Trigger.DELETE)
        if ts != thread_ts:
            runs = runs.filter(trigger_ts=ts)
        run = runs.select_related("thread").order_by("-id").first()
    if run is None:
        return build_notice_view(_no_run_reason(message, thread, availability_config.retention_days))
    return _why_view(run, slack_user_id, availability_config.retention_days, slack)


def _button_view(payload: dict, availability_config: AvailabilityConfig, slack: TimurSlack) -> dict | None:
    """
    View for the "How did Timur decide?" button of a reply, None for other actions
    """
    action = next(
        (action for action in payload.get("actions") or [] if action.get("action_id") == WHY_ACTION_ID),
        None,
    )
    if action is None:
        return None
    run_id = action.get("value")
    run = (
        SlackAvailabilityRun.objects.select_related("thread").filter(pk=int(run_id)).first()
        if str(run_id or "").isdigit()
        else None
    )
    return _why_view(run, (payload.get("user") or {}).get("id"), availability_config.retention_days, slack)


@csrf_exempt
@require_POST
def slack_interactions(request: HttpRequest) -> HttpResponse:
    """
    Slack interactivity endpoint, for the "How did Timur decide?" button and the "Why did Timur do this?" message
    shortcut
    https://docs.slack.dev/interactivity/handling-user-interaction/

    Runs inline: the trigger_id of an interaction expires after 3 seconds.
    """
    availability_config = config.SlackAvailability.load_config()
    if not availability_config.signing_secret:
        return HttpResponse()

    verifier = SignatureVerifier(availability_config.signing_secret)
    if not verifier.is_valid_request(request.body, dict(request.headers)):
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.POST.get("payload") or "")
    except ValueError:
        return HttpResponse(status=400)
    if not isinstance(payload, dict):
        return HttpResponse()
    trigger_id = payload.get("trigger_id")
    if not trigger_id:
        return HttpResponse()

    try:
        slack = TimurSlack()
    except Exception:
        logger.error("Failed to set up the Slack client", exc_info=True)
        return HttpResponse()
    if payload.get("type") == "message_action" and payload.get("callback_id") == WHY_SHORTCUT_CALLBACK_ID:
        # Answered in off mode too, with a notice
        view = _shortcut_view(payload, availability_config, slack)
    elif payload.get("type") == "block_actions" and not availability_config.is_off:
        view = _button_view(payload, availability_config, slack)
    else:
        view = None
    if view is None:
        return HttpResponse()

    try:
        slack.open_view(trigger_id, view)
    except Exception:
        logger.error(
            "Failed to open Slack availability view",
            exc_info=True,
            extra=log_extra({"type": payload.get("type")}),
        )
    return HttpResponse()
