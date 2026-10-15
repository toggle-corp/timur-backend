import json
import logging

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from slack_sdk.signature import SignatureVerifier

from apps.user.models import User
from main import config
from main.caches import CacheKey
from main.logging import log_extra
from utils.slack import TimurSlack

from .events import classify_event
from .messages import WHY_ACTION_ID
from .models import SlackAvailabilityRun
from .tasks import process_slack_availability_event
from .trace import build_notice_view, build_trace_view, has_viewable_trace

logger = logging.getLogger(__name__)

EVENT_DEDUPE_TTL = 60 * 60 * 24


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


def _why_view(run: SlackAvailabilityRun | None, slack_user_id: str | None, retention_days: int) -> dict:
    if run is None:
        return build_notice_view("I couldn't find the details of this reply.")
    # The trace shows the poster's journal
    if slack_user_id != run.thread.slack_user_id and not _is_timur_admin(slack_user_id):
        return build_notice_view("Only the person who posted (or a Timur admin) can view this.")
    if not has_viewable_trace(run.trace):
        return build_notice_view(f"Details expired after {retention_days} days.")
    return build_trace_view(run.trace)


@csrf_exempt
@require_POST
def slack_interactions(request: HttpRequest) -> HttpResponse:
    """
    Slack interactivity endpoint, for the "How did Timur decide?" button
    https://docs.slack.dev/interactivity/handling-user-interaction/

    Runs inline: the trigger_id of an interaction expires after 3 seconds.
    """
    availability_config = config.SlackAvailability.load_config()
    if not availability_config.signing_secret:
        return HttpResponse()

    verifier = SignatureVerifier(availability_config.signing_secret)
    if not verifier.is_valid_request(request.body, dict(request.headers)):
        return HttpResponse(status=401)

    if availability_config.is_off:
        return HttpResponse()

    try:
        payload = json.loads(request.POST.get("payload") or "")
    except ValueError:
        return HttpResponse(status=400)
    if not isinstance(payload, dict) or payload.get("type") != "block_actions":
        return HttpResponse()

    action = next(
        (action for action in payload.get("actions") or [] if action.get("action_id") == WHY_ACTION_ID),
        None,
    )
    trigger_id = payload.get("trigger_id")
    if action is None or not trigger_id:
        return HttpResponse()

    run_id = action.get("value")
    run = (
        SlackAvailabilityRun.objects.select_related("thread").filter(pk=int(run_id)).first()
        if str(run_id or "").isdigit()
        else None
    )
    view = _why_view(run, (payload.get("user") or {}).get("id"), availability_config.retention_days)
    try:
        TimurSlack().open_view(trigger_id, view)
    except Exception:
        logger.error("Failed to open Slack availability trace view", exc_info=True, extra=log_extra({"run_id": run_id}))
    return HttpResponse()
