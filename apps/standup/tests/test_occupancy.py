import datetime
import typing
from unittest import mock

import pytz
from django.core.cache import cache

from apps.common.factories import EventFactory
from apps.common.models import Event
from apps.journal.factories import JournalFactory
from apps.journal.models import Journal
from apps.project.factories import ClientFactory, ContractorFactory, ProjectFactory
from apps.standup.occupancy import get_occupancy_date_range
from apps.track.factories import ContractFactory, TaskFactory, TimeEntryFactory
from apps.track.models import TimeEntry
from apps.user.factories import UserFactory
from main.tests import TestCase


class TestOccupancyDateRange(TestCase):
    def test_date_range(self):
        for date, expected in [
            # First week includes the previous month
            ("2024-03-01", ("2024-02-01", "2024-02-29")),
            ("2024-03-07", ("2024-02-01", "2024-03-06")),
            ("2024-01-03", ("2023-12-01", "2024-01-02")),
            # After the first week only the current month
            ("2024-03-08", ("2024-03-01", "2024-03-07")),
            ("2024-03-31", ("2024-03-01", "2024-03-30")),
        ]:
            start_date, end_date = get_occupancy_date_range(datetime.date.fromisoformat(date))
            assert (start_date.isoformat(), end_date.isoformat()) == expected, date


class TestOccupancyQuery(TestCase):
    class Query:
        DAILY_STANDUP_OCCUPANCY = """
            query MyQuery($date: Date!) {
              private {
                dailyStandup(date: $date) {
                  occupancy {
                    startDate
                    endDate
                    dates
                    users {
                      user {
                        id
                      }
                      days {
                        date
                        hours
                        leave
                        occupancy
                      }
                    }
                  }
                }
              }
            }
        """

    @classmethod
    @typing.override
    def setUpClass(cls):
        super().setUpClass()
        cls.user = UserFactory.create(first_name="A")
        # Not part of the occupancy
        UserFactory.create(first_name="B", exclude_from_slides=True)
        UserFactory.create(first_name="C", is_active=False)

        ur_kwargs = dict(created_by=cls.user, modified_by=cls.user)
        project = ProjectFactory.create(
            project_client=ClientFactory.create(**ur_kwargs),
            contractor=ContractorFactory.create(**ur_kwargs),
            **ur_kwargs,
        )
        contract = ContractFactory.create(project=project, **ur_kwargs)
        cls.task = TaskFactory.create(contract=contract, **ur_kwargs)

    def test_occupancy(self):
        # 2024-02-03/04 are weekends and 2024-02-06 is a holiday
        EventFactory.create(
            type=Event.Type.HOLIDAY,
            start_date="2024-02-06",
            end_date="2024-02-06",
            created_by=self.user,
            modified_by=self.user,
        )

        def _time_entry(date: str, duration: int, status: TimeEntry.Status = TimeEntry.Status.DONE):
            TimeEntryFactory.create(user=self.user, task=self.task, date=date, duration=duration, status=status)

        # Full day
        _time_entry("2024-02-01", 420)
        _time_entry("2024-02-01", 60, status=TimeEntry.Status.TODO)
        _time_entry("2024-02-01", 0)
        # Full leave
        _time_entry("2024-02-02", 60)
        JournalFactory.create(user=self.user, date="2024-02-02", leave_type=Journal.LeaveType.FULL)
        # Half leave
        _time_entry("2024-02-05", 210, status=TimeEntry.Status.DOING)
        JournalFactory.create(user=self.user, date="2024-02-05", leave_type=Journal.LeaveType.FIRST_HALF)
        # Holiday
        _time_entry("2024-02-06", 120)
        # 2024-02-07: Nothing
        # Half leave without time entries
        JournalFactory.create(user=self.user, date="2024-02-08", leave_type=Journal.LeaveType.SECOND_HALF)
        # Standup date
        _time_entry("2024-02-09", 120)

        self.force_login(self.user)
        with mock.patch("apps.common.models.timezone.now") as now_mock:
            now_mock.return_value = pytz.utc.localize(datetime.datetime(2024, 2, 9))
            cache.clear()
            content = self.query_check(self.Query.DAILY_STANDUP_OCCUPANCY, variables={"date": "2024-02-09"})

        assert content["data"]["private"]["dailyStandup"]["occupancy"] == {
            "startDate": "2024-02-01",
            "endDate": "2024-02-08",
            "dates": ["2024-02-01", "2024-02-02", "2024-02-05", "2024-02-07", "2024-02-08"],
            "users": [
                {
                    "user": {"id": self.gID(self.user.pk)},
                    "days": [
                        {"date": "2024-02-01", "hours": 7.0, "leave": None, "occupancy": 1.0},
                        {"date": "2024-02-02", "hours": 1.0, "leave": "FULL", "occupancy": 0.0},
                        {"date": "2024-02-05", "hours": 3.5, "leave": "FIRST_HALF", "occupancy": 1.0},
                        {"date": "2024-02-07", "hours": None, "leave": None, "occupancy": None},
                        {"date": "2024-02-08", "hours": None, "leave": "SECOND_HALF", "occupancy": None},
                    ],
                },
            ],
        }
