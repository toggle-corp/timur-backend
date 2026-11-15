import datetime
import typing

from django.urls import reverse
from django.utils import timezone

from apps.api_token.factories import ApiTokenFactory
from apps.user.factories import UserFactory
from main.tests import TestCase


class TestApiTokenAdmin(TestCase):
    @typing.override
    def setUp(self):
        super().setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.client.force_login(self.superuser)

    def test_list_and_change_pages_never_show_hash(self):
        token = ApiTokenFactory.create()
        for url in [
            reverse("admin:api_token_apitoken_changelist"),
            reverse("admin:api_token_apitoken_change", args=[token.pk]),
        ]:
            response = self.client.get(url)
            assert response.status_code == 200
            content = response.content.decode()
            assert token.prefix in content
            assert token.hash not in content
            assert token.secret not in content

    def test_revoke_action(self):
        active = ApiTokenFactory.create()
        expired = ApiTokenFactory.create(expires_at=timezone.now() - datetime.timedelta(days=1))
        other = ApiTokenFactory.create()
        response = self.client.post(
            reverse("admin:api_token_apitoken_changelist"),
            {"action": "revoke_tokens", "_selected_action": [active.pk, expired.pk]},
        )
        assert response.status_code == 302
        for token in (active, expired, other):
            token.refresh_from_db()
        assert active.revoked_at is not None
        assert expired.revoked_at is not None
        assert other.revoked_at is None

    def test_no_add(self):
        response = self.client.get(reverse("admin:api_token_apitoken_add"))
        assert response.status_code == 403

    def test_staff_without_superuser_cannot_view_or_revoke(self):
        from django.contrib.auth.models import Permission

        token = ApiTokenFactory.create()
        staff = UserFactory.create(is_staff=True)
        staff.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="api_token"),
        )
        self.client.force_login(staff)
        assert self.client.get(reverse("admin:api_token_apitoken_changelist")).status_code == 403
        self.client.post(
            reverse("admin:api_token_apitoken_changelist"),
            {"action": "revoke_tokens", "_selected_action": [token.pk]},
        )
        token.refresh_from_db()
        assert token.revoked_at is None
