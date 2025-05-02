import typing
from unittest import mock

from django.core import management

from apps.standup.tests.test_tasks import TimurSlackMock
from apps.user.factories import UserFactory
from main.tests import TestCase


@mock.patch("apps.user.tasks.TimurSlack", TimurSlackMock)
class TestStandup(TestCase):
    @classmethod
    @typing.override
    def setUpClass(cls):
        super().setUpClass()

        UserFactory.create_batch(3, slack_user_id=None)

    def test_cli(self):
        management.call_command("sync_slack_users_id", verbosity=0)
        management.call_command("sync_slack_users_id", "--only-list", verbosity=0)
