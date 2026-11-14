import dataclasses
import datetime
import enum
import logging
import typing

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.template.loader import render_to_string
from django.utils import dateformat, timezone

from apps.user.models import User
from main import config
from main.logging import log_extra

from .models import ApiToken

logger = logging.getLogger(__name__)

EXPIRY_REMINDER_WINDOW = datetime.timedelta(days=7)
EXPIRED_NOTICE_WINDOW = datetime.timedelta(days=7)
API_TOKENS_FRONTEND_PATH = "/settings/api-tokens"


class Notice(typing.NamedTuple):
    template: str
    sent_at_field: str
    subject: str


EXPIRY_REMINDER = Notice(
    template="api_token/emails/expiry_reminder",
    sent_at_field="expiry_reminder_sent_at",
    subject='Your Timur API token "{name}" expires {expires_in}',
)
EXPIRED_NOTICE = Notice(
    template="api_token/emails/expired_notice",
    sent_at_field="expired_notice_sent_at",
    subject='Your Timur API token "{name}" has expired',
)


def _notifiable_qs() -> models.QuerySet[ApiToken]:
    return ApiToken.objects.filter(
        revoked_at__isnull=True,
        user__is_active=True,
        user__invalid_email=False,
    ).select_related("user")


def get_expiry_reminder_qs(now: datetime.datetime) -> models.QuerySet[ApiToken]:
    return _notifiable_qs().filter(
        expires_at__gt=now,
        expires_at__lte=now + EXPIRY_REMINDER_WINDOW,
        expiry_reminder_sent_at__isnull=True,
    )


def get_expired_notice_qs(now: datetime.datetime) -> models.QuerySet[ApiToken]:
    return _notifiable_qs().filter(
        expires_at__lte=now,
        expires_at__gte=now - EXPIRED_NOTICE_WINDOW,
        expired_notice_sent_at__isnull=True,
    )


# Emails don't know the reader's timezone, so dates are shown in UTC
def _format_date(value: datetime.datetime) -> str:
    return dateformat.format(value.astimezone(datetime.UTC), "M j, Y") + " UTC"


def _format_datetime(value: datetime.datetime) -> str:
    return dateformat.format(value.astimezone(datetime.UTC), "M j, Y, H:i") + " UTC"


def _format_expires_in(expires_at: datetime.datetime, now: datetime.datetime) -> str:
    days = (expires_at.astimezone(datetime.UTC).date() - now.astimezone(datetime.UTC).date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def get_api_tokens_url() -> str:
    return config.APP_FRONTEND_HOST.geturl().rstrip("/") + API_TOKENS_FRONTEND_PATH


class SendStatus(enum.Enum):
    SENT = "sent"
    SKIPPED = "skipped"
    FAILED = "failed"


def _build_email(token: ApiToken, notice: Notice, now: datetime.datetime) -> EmailMultiAlternatives:
    user = token.user
    api_tokens_url = get_api_tokens_url()
    subject = notice.subject.format(name=token.name, expires_in=_format_expires_in(token.expires_at, now))
    context = {
        "subject": subject,
        "user_name": User.get_display_name(user.pk, user.get_full_name() or user.email),
        "token_name": token.name,
        "token_prefix": f"{ApiToken.SECRET_PREFIX}{token.prefix}",
        "expires_on": _format_date(token.expires_at),
        "expires_at": _format_datetime(token.expires_at),
        "expires_in": _format_expires_in(token.expires_at, now),
        "last_used": token.last_used_at and _format_date(token.last_used_at),
        "api_tokens_url": api_tokens_url,
        "api_tokens_url_display": api_tokens_url.split("://", 1)[-1],
    }
    email = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string(f"{notice.template}.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[token.user.email],
    )
    email.attach_alternative(render_to_string(f"{notice.template}.html", context), "text/html")
    return email


def send_notice(token: ApiToken, notice: Notice, now: datetime.datetime | None = None) -> SendStatus:
    """
    Claim the token by setting the notice's sent marker, then send.
    The conditional update is the claim: when two runs overlap, only one of them sets the marker
    (Postgres re-checks the `IS NULL` condition after the other run's update commits).
    On a send failure the marker is cleared so the next run retries.
    """
    claimed_at = timezone.now()
    claimed = ApiToken.objects.filter(pk=token.pk, **{f"{notice.sent_at_field}__isnull": True}).update(
        **{notice.sent_at_field: claimed_at},
    )
    if not claimed:
        return SendStatus.SKIPPED
    try:
        _build_email(token, notice, now or timezone.now()).send()
    except Exception:
        logger.error(
            "Failed to send API token notice",
            exc_info=True,
            extra=log_extra({"token_id": token.pk, "notice": notice.sent_at_field}),
        )
        ApiToken.objects.filter(pk=token.pk, **{notice.sent_at_field: claimed_at}).update(
            **{notice.sent_at_field: None},
        )
        return SendStatus.FAILED
    return SendStatus.SENT


@dataclasses.dataclass
class SendResult:
    expiry_reminders: int = 0
    expired_notices: int = 0
    failed: int = 0


def send_expiry_notices(now: datetime.datetime | None = None) -> SendResult:
    """
    Send the 7-day reminder and the expired notice, each at most once per token.
    A failed send is counted in `failed` and retried on the next run.
    """
    now = now or timezone.now()
    result = SendResult()
    for notice, qs in (
        (EXPIRED_NOTICE, get_expired_notice_qs(now)),
        (EXPIRY_REMINDER, get_expiry_reminder_qs(now)),
    ):
        for token in qs.order_by("id"):
            status = send_notice(token, notice, now)
            if status == SendStatus.FAILED:
                result.failed += 1
            elif status == SendStatus.SENT and notice is EXPIRY_REMINDER:
                result.expiry_reminders += 1
            elif status == SendStatus.SENT:
                result.expired_notices += 1
    return result
