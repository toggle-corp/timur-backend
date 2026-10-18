import datetime
import logging

from celery import shared_task
from django.utils import timezone

from main import config
from utils.slack import TimurSlack

from .events import SlackMessageEvent
from .models import SlackAvailabilityRun
from .parsers import ABOUT_AVAILABILITY_KEY
from .processor import AvailabilityProcessor, mark_event_failed, mark_notify_failed
from .trace import purge_trace

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def retry_countdown(retries: int) -> int:
    return 30 * 2**retries


@shared_task(bind=True, max_retries=MAX_RETRIES)
def process_slack_availability_event(self, event: dict):
    """
    Process an event classified by the events endpoint (SlackMessageEvent.as_dict)
    """
    # The mode can change while the event is queued
    if config.SlackAvailability.load_config().is_off:
        return

    message_event = SlackMessageEvent.from_dict(event)

    slack = TimurSlack()
    processor = AvailabilityProcessor(slack)
    try:
        run = processor.process(message_event)
    except Exception as exc:
        if self.request.retries < MAX_RETRIES:
            raise self.retry(exc=exc, countdown=retry_countdown(self.request.retries)) from exc
        mark_event_failed(slack, message_event, exc)
        return

    if run is None:
        return
    try:
        processor.notify(run)
    except Exception:
        logger.warning("Failed to notify Slack, retrying separately", exc_info=True)
        notify_slack_availability_run.apply_async(args=(run.pk,), countdown=retry_countdown(0))


@shared_task(bind=True, max_retries=MAX_RETRIES)
def notify_slack_availability_run(self, run_id: int):
    """
    Retry the Slack reaction and reply of a run whose journal changes are committed
    """
    run = SlackAvailabilityRun.objects.select_related("thread").filter(pk=run_id).first()
    if run is None:
        return

    slack = TimurSlack()
    try:
        AvailabilityProcessor(slack).notify(run)
    except Exception as exc:
        if self.request.retries < MAX_RETRIES:
            raise self.retry(exc=exc, countdown=retry_countdown(self.request.retries + 1)) from exc
        mark_notify_failed(slack, run, exc)


# Keys of the parser output that hold dates and types only
LLM_OUTPUT_KEPT_KEYS = (ABOUT_AVAILABILITY_KEY, "availability", "confidence")
# Keys of a parser output availability item that quote the messages
LLM_OUTPUT_QUOTED_ITEM_KEYS = ("source_phrase",)


def _purge_llm_output(llm_output: dict) -> dict:
    kept = {key: llm_output[key] for key in LLM_OUTPUT_KEPT_KEYS if key in llm_output}
    if isinstance(kept.get("availability"), list):
        kept["availability"] = [
            {key: value for key, value in item.items() if key not in LLM_OUTPUT_QUOTED_ITEM_KEYS}
            if isinstance(item, dict)
            else item
            for item in kept["availability"]
        ]
    return {**kept, "unclear": []}


def purge_slack_availability_runs() -> int:
    """
    Blank message-derived text of runs older than the retention period

    Dates and leave/WFH types are kept.
    """
    retention_days = config.SlackAvailability.load_config().retention_days
    now = timezone.now()
    runs = list(
        SlackAvailabilityRun.objects.filter(
            created_at__lt=now - datetime.timedelta(days=retention_days),
            purged_at__isnull=True,
        ).only("id", "llm_output", "planned_changes", "trace"),
    )
    for run in runs:
        run.llm_input = ""
        run.reply_text = ""
        run.error = ""
        if isinstance(run.llm_output, dict):
            run.llm_output = _purge_llm_output(run.llm_output)
        run.trace = purge_trace(run.trace)
        if run.planned_changes.get("unclear"):
            run.planned_changes = {**run.planned_changes, "unclear": []}
        run.purged_at = now
    SlackAvailabilityRun.objects.bulk_update(
        runs,
        fields=("llm_input", "reply_text", "error", "llm_output", "planned_changes", "trace", "purged_at"),
        batch_size=500,
    )
    logger.info("Purged message text of %s Slack availability runs", len(runs))
    return len(runs)
