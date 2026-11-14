import datetime
import io
import typing

import pytest
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.locmem import EmailBackend as LocmemEmailBackend
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone

from apps.api_token.factories import ApiTokenFactory
from apps.api_token.models import ApiToken
from apps.api_token.notifications import EXPIRY_REMINDER, SendStatus, send_expiry_notices, send_notice
from apps.user.factories import UserFactory
from main.tests import TestCase

UTC = datetime.UTC


def html_body(email) -> str:
    (content,) = [content for content, mimetype in email.alternatives if mimetype == "text/html"]
    return content


class FailingEmailBackend(BaseEmailBackend):
    @typing.override
    def send_messages(self, email_messages):
        raise ConnectionRefusedError("SMTP is down")


class MarkerCheckingEmailBackend(LocmemEmailBackend):
    """
    Records on each message the reminder markers stored in the database at send time.
    """

    @typing.override
    def send_messages(self, email_messages):
        for message in email_messages:
            markers = list(ApiToken.objects.values_list("expiry_reminder_sent_at", flat=True))
            message.markers_at_send = markers  # type: ignore[reportAttributeAccessIssue]
        return super().send_messages(email_messages)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="Timur <timur@example.com>",
)
class TestApiTokenExpiryNotify(TestCase):
    def notify(self):
        mail.outbox.clear()
        call_command("api_token_expiry_notify", stdout=io.StringIO())
        return list(mail.outbox)

    def in_days(self, days: float) -> datetime.datetime:
        return timezone.now() + datetime.timedelta(days=days)

    def test_reminder_within_seven_days_sent_once(self):
        soon = ApiTokenFactory.create(name="deploy bot", expires_at=self.in_days(3))
        ApiTokenFactory.create(expires_at=self.in_days(8))  # Too early

        emails = self.notify()
        assert len(emails) == 1
        email = emails[0]
        assert email.to == [soon.user.email]
        assert email.from_email == "Timur <timur@example.com>"
        assert "deploy bot" in email.subject
        assert "expires" in email.subject
        assert soon.prefix in email.body
        assert "http://localhost:3000/settings/api-tokens" in email.body
        html_bodies = [content for content, mimetype in email.alternatives if mimetype == "text/html"]  # type: ignore[reportAttributeAccessIssue]
        assert len(html_bodies) == 1
        assert soon.prefix in html_bodies[0]

        soon.refresh_from_db()
        assert soon.expiry_reminder_sent_at is not None
        assert soon.expired_notice_sent_at is None

        # Only once
        assert self.notify() == []

    def test_expired_notice_sent_once(self):
        token = ApiTokenFactory.create(
            name="old script",
            expires_at=self.in_days(-1),
            expiry_reminder_sent_at=self.in_days(-6),
        )
        emails = self.notify()
        assert len(emails) == 1
        assert "old script" in emails[0].subject
        assert "expired" in emails[0].subject
        token.refresh_from_db()
        assert token.expired_notice_sent_at is not None

        assert self.notify() == []

    def test_expired_without_reminder_gets_only_expired_notice(self):
        token = ApiTokenFactory.create(expires_at=self.in_days(-1))
        emails = self.notify()
        assert len(emails) == 1
        assert "expired" in emails[0].subject
        token.refresh_from_db()
        assert token.expired_notice_sent_at is not None

    def test_never_used_text(self):
        ApiTokenFactory.create(expires_at=self.in_days(2))
        (email,) = self.notify()
        assert "seems like it isn't used" in email.body
        assert "seems like it isn't used" in html_body(email)

        ApiTokenFactory.create(expires_at=self.in_days(-1))
        (email,) = self.notify()
        assert "seems like it isn't used" in email.body
        assert "seems like it isn't used" in html_body(email)

    def test_reminder_content(self):
        user = UserFactory.create(first_name="Hari", last_name="Bahadur")
        token = ApiTokenFactory.create(
            user=user,
            name="Laptop scripts",
            # 23:59:59 in the user's browser (UTC+05:45)
            expires_at=datetime.datetime(2026, 11, 20, 18, 14, 59, tzinfo=UTC),
            last_used_at=datetime.datetime(2026, 11, 12, 4, 15, tzinfo=UTC),
        )
        mail.outbox.clear()
        send_expiry_notices(now=datetime.datetime(2026, 11, 15, 3, 15, tzinfo=UTC))
        (email,) = mail.outbox
        assert email.subject == 'Your Timur API token "Laptop scripts" expires in 5 days'
        for body in (email.body, html_body(email)):
            assert "Hi Hari Bahadur," in body
            assert "Nov 20, 2026, 18:14 UTC" in body
            assert "expires on Nov 20, 2026 UTC" in body.replace("<b>", "").replace("</b>", "")
            assert "Nov 12, 2026 UTC" in body
            assert f"tc_timur_{token.prefix}" in body
            assert "http://localhost:3000/settings/api-tokens" in body
            assert "seems like it isn't used" not in body
        assert "#a8431f" in html_body(email)
        assert "It stops working on Nov 20, 2026 UTC." in html_body(email)

    def test_expired_content_and_email_greeting_fallback(self):
        user = UserFactory.create(first_name="", last_name="")
        ApiTokenFactory.create(
            user=user,
            name="Laptop scripts",
            expires_at=datetime.datetime(2026, 11, 20, 18, 14, 59, tzinfo=UTC),
        )
        mail.outbox.clear()
        send_expiry_notices(now=datetime.datetime(2026, 11, 22, 3, 15, tzinfo=UTC))
        (email,) = mail.outbox
        assert email.subject == 'Your Timur API token "Laptop scripts" has expired'
        for body in (email.body, html_body(email)):
            assert f"Hi {user.email}," in body
            assert "Nov 20, 2026, 18:14 UTC" in body
            assert "expired on Nov 20, 2026 UTC" in body.replace("<b>", "").replace("</b>", "")

    def test_expired_notice_only_within_seven_days_of_expiry(self):
        ApiTokenFactory.create(expires_at=self.in_days(-8))
        recent = ApiTokenFactory.create(expires_at=self.in_days(-6))
        emails = self.notify()
        assert [email.to for email in emails] == [[recent.user.email]]

    def test_skips_revoked_inactive_and_invalid_email(self):
        ApiTokenFactory.create(expires_at=self.in_days(2), revoked_at=timezone.now())
        ApiTokenFactory.create(expires_at=self.in_days(-1), revoked_at=self.in_days(-2))
        ApiTokenFactory.create(expires_at=self.in_days(2), user=UserFactory.create(is_active=False))
        ApiTokenFactory.create(expires_at=self.in_days(-1), user=UserFactory.create(is_active=False))
        ApiTokenFactory.create(expires_at=self.in_days(2), user=UserFactory.create(invalid_email=True))
        ApiTokenFactory.create(expires_at=self.in_days(-1), user=UserFactory.create(invalid_email=True))
        assert self.notify() == []

    def test_failed_send_exits_non_zero_and_is_retried(self):
        token = ApiTokenFactory.create(expires_at=self.in_days(2))
        with (
            override_settings(EMAIL_BACKEND="apps.api_token.tests.test_commands.FailingEmailBackend"),
            pytest.raises(CommandError),
        ):
            call_command("api_token_expiry_notify", stdout=io.StringIO())
        token.refresh_from_db()
        assert token.expiry_reminder_sent_at is None

        # Next run sends it
        assert len(self.notify()) == 1
        token.refresh_from_db()
        assert token.expiry_reminder_sent_at is not None

    def test_token_is_claimed_before_sending(self):
        ApiTokenFactory.create(expires_at=self.in_days(2))
        with override_settings(EMAIL_BACKEND="apps.api_token.tests.test_commands.MarkerCheckingEmailBackend"):
            (email,) = self.notify()
        assert len(email.markers_at_send) == 1  # type: ignore[reportAttributeAccessIssue]
        assert email.markers_at_send[0] is not None  # type: ignore[reportAttributeAccessIssue]

    def test_token_claimed_by_another_run_is_skipped(self):
        token = ApiTokenFactory.create(expires_at=self.in_days(2))
        stale = ApiToken.objects.select_related("user").get(pk=token.pk)
        # Another run claims it after this run selected it
        ApiToken.objects.filter(pk=token.pk).update(expiry_reminder_sent_at=timezone.now())
        mail.outbox.clear()
        assert send_notice(stale, EXPIRY_REMINDER) == SendStatus.SKIPPED
        assert mail.outbox == []
