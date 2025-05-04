import datetime
import typing
from unittest import mock

from django.core import management
from slack_sdk.models.blocks.blocks import Block
from slack_sdk.web.slack_response import SlackResponse

from apps.common.factories import EventFactory
from apps.common.models import Event
from apps.journal.factories import JournalFactory
from apps.journal.models import Journal
from apps.standup.management.commands.standup import CommandActionType
from apps.standup.models import DailyUserStandup
from apps.standup.tasks import (
    before_standup_reminder,
    morning_reminder,
    read_doc_reminder,
    setup_next_standup,
)
from apps.user.factories import UserFactory
from main.tests import TestCase
from utils.slack import TimurSlack

slack_thread_ts_counter = 0


class TimurSlackMock(TimurSlack):
    class DummySlackClient:
        @staticmethod
        def users_list(**_):
            counter = 0

            def _get_obj(*, is_bot, deleted):
                nonlocal counter
                counter += 1
                return {
                    "id": f"slack-user-{counter}",
                    "is_bot": is_bot,
                    "deleted": deleted,
                    **(
                        {}
                        if is_bot
                        else {
                            "profile": {
                                "email": f"{counter}@xyz.com",
                            },
                        }
                    ),
                }

            return {
                "members": [
                    {"id": "USLACKBOT", "is_bot": False},
                    _get_obj(is_bot=False, deleted=False),
                    _get_obj(is_bot=False, deleted=True),
                    _get_obj(is_bot=False, deleted=False),
                    _get_obj(is_bot=False, deleted=False),
                    _get_obj(is_bot=False, deleted=True),
                    _get_obj(is_bot=True, deleted=True),
                    _get_obj(is_bot=True, deleted=True),
                ],
                "response_metadata": {
                    "next_cursor": "",
                },
            }

    @typing.override
    def __init__(self):
        self.client = self.DummySlackClient()

    @typing.override
    def lookup_user_by_email(self, email: str):
        return typing.cast(
            "SlackResponse",
            {
                "user": {"id": email},
            },
        )

    @typing.override
    def send_slack_message(
        self,
        text: str | None = None,
        blocks: str | typing.Sequence[dict | Block] | None = None,
        thread_ts: str | None = None,
    ) -> SlackResponse:
        print(  # noqa: T201
            {"text": text, "blocks": blocks, "thread_ts": thread_ts},
        )
        global slack_thread_ts_counter
        slack_thread_ts_counter += 1
        return typing.cast(
            "SlackResponse",
            {"ts": f"{slack_thread_ts_counter}.7890"},
        )


@mock.patch("apps.standup.tasks.TimurSlack", TimurSlackMock)
class TestStandup(TestCase):
    @classmethod
    @typing.override
    def setUpClass(cls):
        super().setUpClass()
        cls.user = UserFactory.create()
        cls.base_date = datetime.datetime(year=2024, month=2, day=1) - datetime.timedelta(days=1)
        ur_kwargs = {"created_by": cls.user, "modified_by": cls.user}

        # Some users as well
        cls.assignable_users = UserFactory.create_batch(10, assign_for_standup=True)
        cls.unassignable_users = [
            UserFactory.create(is_active=False, assign_for_standup=True),
            *UserFactory.create_batch(5, assign_for_standup=False),
        ]

        # Some users with leaves, wfh as well
        for days_delta_gap, user in [
            (5, cls.assignable_users[0]),
            (10, cls.assignable_users[1]),
            (20, cls.assignable_users[2]),
        ]:
            for index, (leave_type, wfh_type) in enumerate(
                [
                    (Journal.LeaveType.FULL, None),
                    (Journal.LeaveType.FIRST_HALF, None),
                    (Journal.LeaveType.FIRST_HALF, Journal.WorkFromHomeType.SECOND_HALF),
                    (None, Journal.WorkFromHomeType.FULL),
                    (None, Journal.WorkFromHomeType.FIRST_HALF),
                    (Journal.LeaveType.SECOND_HALF, Journal.WorkFromHomeType.FIRST_HALF),
                ],
            ):
                journal_kwargs = dict(
                    user=user,
                    leave_type=leave_type,
                    wfh_type=wfh_type,
                )
                JournalFactory.create(
                    **journal_kwargs,
                    date=cls.base_date + datetime.timedelta(days=days_delta_gap * index),
                )

        # Create some events
        cls.events_holidays = [
            EventFactory.create(
                **ur_kwargs,
                type=Event.Type.HOLIDAY,
                start_date=cls.base_date + datetime.timedelta(days=5),
                end_date=cls.base_date + datetime.timedelta(days=5),
            ),
            EventFactory.create(
                **ur_kwargs,
                type=Event.Type.RETREAT,
                start_date=cls.base_date + datetime.timedelta(days=10),
                end_date=cls.base_date + datetime.timedelta(days=12),
            ),
            EventFactory.create(
                **ur_kwargs,
                type=Event.Type.HOLIDAY,
                start_date=cls.base_date + datetime.timedelta(weeks=2, days=5),
                end_date=cls.base_date + datetime.timedelta(weeks=2, days=5),
            ),
            # Weekend holiday
            EventFactory.create(
                **ur_kwargs,
                type=Event.Type.HOLIDAY,
                start_date=cls.base_date + datetime.timedelta(weeks=2, days=4),
                end_date=cls.base_date + datetime.timedelta(weeks=2, days=4),
            ),
            # Misc
            EventFactory.create(
                **ur_kwargs,
                type=Event.Type.MISC,
                start_date=cls.base_date + datetime.timedelta(days=20),
                end_date=cls.base_date + datetime.timedelta(days=25),
            ),
        ]

    def test_assign(self):
        assert DailyUserStandup.objects.count() == 0

        with mock.patch("apps.standup.tasks.timezone.now") as now_mock:
            for days in range(300):
                now_mock.return_value = self.base_date + datetime.timedelta(days=days)
                morning_reminder()
                before_standup_reminder()
                setup_next_standup()
                read_doc_reminder()

        assert DailyUserStandup.objects.filter(conductor__in=self.unassignable_users).count() == 0
        assert DailyUserStandup.objects.filter(fallback_conductor__in=self.unassignable_users).count() == 0

        assert DailyUserStandup.objects.filter(conductor__in=self.assignable_users).count() > 0
        assert DailyUserStandup.objects.filter(fallback_conductor__in=self.assignable_users).count() > 0
        assert DailyUserStandup.objects.count() == 211

        # TODO: Add duplicate checks

    def test_cli(self):
        for sub_command in typing.get_args(CommandActionType):
            management.call_command("standup", sub_command, verbosity=0)
