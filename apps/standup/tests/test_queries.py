import datetime
import typing
from unittest import mock

import pytz

from apps.standup.factories import DailyUserStandupFactory, QuoteFactory
from apps.user.factories import UserFactory
from main.tests import TestCase

if typing.TYPE_CHECKING:
    from apps.standup.models import DailyUserStandup


class TestUserQuery(TestCase):
    class Query:
        DAILY_STANDUP = """
            query MyQuery($date: Date!) {
              private {
                dailyStandup(date: $date) {
                  id
                  date
                  conductor {
                    id
                    displayName
                  }
                  fallbackConductor {
                    id
                    displayName
                  }
                  quote {
                    id
                    text
                    author
                  }
                }
              }
            }
        """
        # TODO: Add tests for projectStat (project_stat)

    @classmethod
    @typing.override
    def setUpClass(cls):
        super().setUpClass()
        cls.user = UserFactory.create()
        ur_kwargs = {"created_by": cls.user, "modified_by": cls.user}

        cls.base_datetime = pytz.utc.localize(datetime.datetime(year=2024, month=2, day=1) - datetime.timedelta(days=1))

        cls.quotes = QuoteFactory.create_batch(10, **ur_kwargs)

        cls.standups = [
            DailyUserStandupFactory.create(
                date="2024-02-01",
                conductor=cls.user,
                quote=cls.quotes[0],
            ),
            DailyUserStandupFactory.create(
                date="2024-02-12",
                conductor=cls.user,
                fallback_conductor=cls.user,
                quote=cls.quotes[2],
            ),
            DailyUserStandupFactory.create(
                date="2024-02-19",
                fallback_conductor=cls.user,
                quote=cls.quotes[7],
            ),
            DailyUserStandupFactory.create(
                date="2024-02-26",
                quote=cls.quotes[8],
            ),
        ]
        cls.standups_by_date: dict[str, DailyUserStandup] = {standup.date: standup for standup in cls.standups}

    def test_standup(self):
        def _query_check(date: datetime.date, assert_errors=False):
            return self.query_check(
                self.Query.DAILY_STANDUP,
                variables={"date": date.isoformat()},
                assert_errors=assert_errors,
            )

        # Without authentication -----
        _query_check(self.base_datetime.date(), assert_errors=True)

        user = self.user
        # With authentication -----
        self.force_login(user)
        with mock.patch("apps.standup.tasks.timezone.now") as now_mock:
            for day in range(300):
                mocked_datetime = self.base_datetime + datetime.timedelta(days=day)
                now_mock.return_value = mocked_datetime
                content = _query_check(mocked_datetime.date())

                if pre_created_standup := self.standups_by_date.get(mocked_datetime.date().isoformat()):
                    assert content["data"]["private"]["dailyStandup"] == {
                        "id": self.gID(pre_created_standup.pk),
                        "date": pre_created_standup.date,
                        "conductor": pre_created_standup.conductor_id
                        and {
                            "id": self.gID(pre_created_standup.conductor.pk),
                            "displayName": pre_created_standup.conductor.display_name,
                        },
                        "fallbackConductor": pre_created_standup.fallback_conductor_id
                        and {
                            "id": self.gID(pre_created_standup.fallback_conductor.pk),
                            "displayName": pre_created_standup.fallback_conductor.display_name,
                        },
                        "quote": pre_created_standup.quote_id
                        and {
                            "id": self.gID(pre_created_standup.quote.pk),
                            "author": pre_created_standup.quote.author,
                            "text": pre_created_standup.quote.text,
                        },
                    }
                    continue

                # Auto generated standups
                assert content["data"]["private"]["dailyStandup"].pop("id") is not None
                assert content["data"]["private"]["dailyStandup"].pop("quote") is not None
                assert content["data"]["private"]["dailyStandup"] == {
                    "date": mocked_datetime.date().isoformat(),
                    "conductor": None,
                    "fallbackConductor": None,
                }
