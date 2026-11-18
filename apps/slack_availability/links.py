"""
Links to Slack messages
"""

import logging

from django.core.cache import cache

from main.caches import CacheKey
from utils.slack import TimurSlack

from .models import SlackAvailabilityRun, SlackAvailabilityThread

logger = logging.getLogger(__name__)

WORKSPACE_URL_CACHE_TTL = 60 * 60 * 24
WORKSPACE_URL_FAILURE_CACHE_TTL = 60 * 5


def workspace_url(slack: TimurSlack) -> str | None:
    """
    Workspace URL with a trailing slash, cached. None when Slack can't tell
    """
    url = cache.get(CacheKey.SLACK_WORKSPACE_URL)
    if url is not None:
        return url or None
    try:
        url = slack.fetch_workspace_url() or ""
        ttl = WORKSPACE_URL_CACHE_TTL
    except Exception:
        logger.warning("Failed to get the Slack workspace URL", exc_info=True)
        url = ""
        ttl = WORKSPACE_URL_FAILURE_CACHE_TTL
    if url and not url.endswith("/"):
        url += "/"
    cache.set(CacheKey.SLACK_WORKSPACE_URL, url, ttl)
    return url or None


def message_permalink(base_url: str, channel_id: str, ts: str, thread_ts: str | None = None) -> str:
    """
    https://docs.slack.dev/reference/methods/chat.getPermalink/ (same format, without an API call)
    """
    link = f"{base_url}archives/{channel_id}/p{ts.replace('.', '')}"
    if thread_ts and thread_ts != ts:
        link += f"?thread_ts={thread_ts}&cid={channel_id}"
    return link


def thread_permalink(base_url: str, thread: SlackAvailabilityThread) -> str:
    return message_permalink(base_url, thread.channel_id, thread.thread_ts)


def run_permalink(base_url: str, run: SlackAvailabilityRun) -> str:
    """
    Link to the message that triggered the run
    """
    thread = run.thread
    return message_permalink(base_url, thread.channel_id, run.trigger_ts, thread_ts=thread.thread_ts)
