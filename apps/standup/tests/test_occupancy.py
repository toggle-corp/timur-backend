import datetime
import typing
from unittest import mock

import pytz
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from apps.common.factories import EventFactory
from apps.common.models import Event
from apps.journal.factories import JournalFactory
from apps.journal.models import Journal
from apps.project.factories import ClientFactory, ContractorFactory, ProjectFactory
from apps.standup.occupancy import get_occupancy_date_range, get_previous_range
from apps.track.factories import ContractFactory, TaskFactory, TimeEntryFactory
from apps.track.models import TimeEntry
from apps.user.factories import UserFactory
from main.tests import TestCase


def to_utc(value: str) -> datetime.datetime:
    """A date or a date and time in UTC, with a date at 06:00 UTC, which is 11:45 local time."""
    return pytz.utc.localize(datetime.datetime.fromisoformat(value if "T" in value else f"{value}T06:00"))


def get_pending_dates(user: dict) -> list[str]:
    return [day["date"] for day in user["days"] if day["isPending"]]


class TestOccupancyDateRange(TestCase):
    def test_date_range(self):
        for date, expected in [
            # First week includes the previous month
            ("2024-03-01", ("2024-02-01", "2024-02-29")),
            ("2024-03-07", ("2024-02-01", "2024-03-06")),
            ("2024-01-03", ("2023-12-01", "2024-01-02")),
            # After the first week the last 30 days
            ("2024-03-08", ("2024-02-07", "2024-03-07")),
            ("2024-03-31", ("2024-03-01", "2024-03-30")),
            ("2024-01-15", ("2023-12-16", "2024-01-14")),
        ]:
            start_date, end_date = get_occupancy_date_range(datetime.date.fromisoformat(date))
            assert (start_date.isoformat(), end_date.isoformat()) == expected, date


class TestPreviousRange(TestCase):
    def test_previous_range(self):
        for start_date, end_date, expected in [
            # Whole months
            ("2024-03-01", "2024-03-31", ("2024-02-01", "2024-02-29")),
            ("2024-02-01", "2024-02-29", ("2024-01-01", "2024-01-31")),
            ("2024-01-01", "2024-01-31", ("2023-12-01", "2023-12-31")),
            # Part of a month
            ("2024-03-01", "2024-03-14", ("2024-02-01", "2024-02-14")),
            ("2024-03-01", "2024-03-30", ("2024-02-01", "2024-02-29")),
        ]:
            previous_range = get_previous_range(
                datetime.date.fromisoformat(start_date),
                datetime.date.fromisoformat(end_date),
            )
            assert tuple(date.isoformat() for date in previous_range) == expected, (start_date, end_date)


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
                        leaveDisplay
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

        # Working days of the last 30 days without any entries
        empty_dates = [
            "2024-01-10", "2024-01-11", "2024-01-12",
            "2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18", "2024-01-19",
            "2024-01-22", "2024-01-23", "2024-01-24", "2024-01-25", "2024-01-26",
            "2024-01-29", "2024-01-30", "2024-01-31",
        ]  # fmt: skip
        assert content["data"]["private"]["dailyStandup"]["occupancy"] == {
            "startDate": "2024-01-10",
            "endDate": "2024-02-08",
            "dates": [*empty_dates, "2024-02-01", "2024-02-02", "2024-02-05", "2024-02-07", "2024-02-08"],
            "users": [
                {
                    "user": {"id": self.gID(self.user.pk)},
                    "days": [
                        *(
                            {"date": date, "hours": None, "leave": None, "leaveDisplay": None, "occupancy": None}
                            for date in empty_dates
                        ),
                        {"date": "2024-02-01", "hours": 7.0, "leave": None, "leaveDisplay": None, "occupancy": 1.0},
                        {"date": "2024-02-02", "hours": 1.0, "leave": "FULL", "leaveDisplay": "Full", "occupancy": 0.0},
                        {
                            "date": "2024-02-05",
                            "hours": 3.5,
                            "leave": "FIRST_HALF",
                            "leaveDisplay": "First Half",
                            "occupancy": 1.0,
                        },
                        {"date": "2024-02-07", "hours": None, "leave": None, "leaveDisplay": None, "occupancy": None},
                        {
                            "date": "2024-02-08",
                            "hours": None,
                            "leave": "SECOND_HALF",
                            "leaveDisplay": "Second Half",
                            "occupancy": None,
                        },
                    ],
                },
            ],
        }


# The logging deadlines in these tests are written as Kathmandu times
@override_settings(TIME_ZONE="Asia/Kathmandu")
class TestOccupancyRangeQuery(TestCase):
    JOINED = pytz.utc.localize(datetime.datetime(2024, 1, 1))

    class Query:
        OCCUPANCY = """
            query MyQuery($startDate: Date!, $endDate: Date!) {
              private {
                occupancy(startDate: $startDate, endDate: $endDate) {
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
                      workFromHome
                      occupancy
                      expectedHours
                      lateByDays
                      loggedDuringStandup
                      isPending
                    }
                    summary {
                      ...Summary
                    }
                  }
                  summary {
                    ...Summary
                  }
                  missingPeople
                  users {
                    longDates
                    topProject {
                      project {
                        id
                      }
                      hours
                      share
                    }
                    flaggedEntries {
                      date
                      hours
                      description
                      project {
                        id
                      }
                      isLong
                      isVague
                    }
                    projects {
                      project {
                        id
                      }
                      hours
                      share
                    }
                  }
                  previous {
                    startDate
                    endDate
                    summary {
                      ...Summary
                    }
                    missingPeople
                  }
                  daySummaries {
                    date
                    isWorkingDay
                    eventName
                    summary {
                      hours
                      expectedHours
                      occupancy
                      entries
                    }
                  }
                  miscEvents {
                    name
                  }
                  dataAsOf
                }
              }
            }

            fragment Summary on OccupancySummaryType {
              hours
              expectedHours
              occupancy
              leaveDays
              workFromHomeDays
              missingDays
              missingShare
              entries
              nonWorkingDayHours
              onLeaveHours
              dueDays
              lateDays
              lateShare
              standupDays
              standupShare
              projectsPerDay
              leaveConflictDays
              longEntries
              longEntryShare
              vagueEntries
              vagueEntryShare
            }
        """

        OCCUPANCY_PERSON = """
            query MyQuery($userId: ID!, $endDate: Date!) {
              private {
                occupancyPerson(userId: $userId, endDate: $endDate) {
                  months {
                    startDate
                    hours
                    expectedHours
                    occupancy
                    lateShare
                    leaveDays
                    workFromHomeDays
                  }
                  leaveDaysThisYear
                }
              }
            }
        """

    @classmethod
    @typing.override
    def setUpClass(cls):
        super().setUpClass()
        cls.user_a = UserFactory.create(first_name="A", date_joined=cls.JOINED)
        cls.user_b = UserFactory.create(first_name="B", date_joined=cls.JOINED)
        # Not listed: excluded from the standup slides
        cls.user_c = UserFactory.create(first_name="C", date_joined=cls.JOINED, exclude_from_slides=True)

        ur_kwargs = dict(created_by=cls.user_a, modified_by=cls.user_a)
        cls.project, cls.project_2 = ProjectFactory.create_batch(
            2,
            project_client=ClientFactory.create(**ur_kwargs),
            contractor=ContractorFactory.create(**ur_kwargs),
            **ur_kwargs,
        )
        cls.task, cls.task_2 = [
            TaskFactory.create(contract=ContractFactory.create(project=project, **ur_kwargs), **ur_kwargs)
            for project in [cls.project, cls.project_2]
        ]
        for event_type, name, start_date, end_date in [
            (Event.Type.HOLIDAY, "Holiday", "2024-02-06", "2024-02-06"),
            # Spans beyond the end of the range
            (Event.Type.RETREAT, "Retreat", "2024-02-09", "2024-02-12"),
            (Event.Type.MISC, "Misc", "2024-02-07", "2024-02-07"),
            (Event.Type.MISC, "Misc outside", "2024-03-01", "2024-03-01"),
        ]:
            EventFactory.create(type=event_type, name=name, start_date=start_date, end_date=end_date, **ur_kwargs)

    def _time_entry(
        self,
        user,
        date: str,
        duration: int,
        created_date: str | None = None,
        task=None,
        status=TimeEntry.Status.DONE,
        description="Reviewed the pull requests",
    ):
        entry = TimeEntryFactory.create(
            user=user,
            task=task or self.task,
            date=date,
            duration=duration,
            status=status,
            description=description,
        )
        TimeEntry.objects.filter(pk=entry.pk).update(created_at=to_utc(created_date or date))

    def _query(self, start_date: str, end_date: str, now: str = "2024-12-02", **kwargs) -> dict:
        self.force_login(self.user_a)
        # By default the holiday is more than 200 days before now
        with mock.patch("apps.common.models.timezone.now") as now_mock:
            now_mock.return_value = to_utc(now)
            cache.clear()
            return self.query_check(
                self.Query.OCCUPANCY,
                variables={"startDate": start_date, "endDate": end_date},
                **kwargs,
            )

    def test_occupancy(self):
        self._time_entry(self.user_a, "2024-02-01", 420)
        # Worked while on leave
        self._time_entry(self.user_a, "2024-02-02", 60)
        JournalFactory.create(user=self.user_a, date="2024-02-02", leave_type=Journal.LeaveType.FULL)
        # Worked on a weekend
        self._time_entry(self.user_a, "2024-02-03", 60)
        self._time_entry(self.user_a, "2024-02-05", 210)
        JournalFactory.create(
            user=self.user_a,
            date="2024-02-05",
            leave_type=Journal.LeaveType.FIRST_HALF,
            wfh_type=Journal.WorkFromHomeType.SECOND_HALF,
        )
        # Worked on a holiday
        self._time_entry(self.user_a, "2024-02-06", 120)
        # Leave on a holiday is not leave
        JournalFactory.create(user=self.user_a, date="2024-02-06", leave_type=Journal.LeaveType.FULL)
        # 2024-02-07: Missing
        self._time_entry(self.user_a, "2024-02-08", 420)
        JournalFactory.create(user=self.user_a, date="2024-02-08", wfh_type=Journal.WorkFromHomeType.FULL)
        # Two entries on the same day
        self._time_entry(self.user_b, "2024-02-01", 105)
        self._time_entry(self.user_b, "2024-02-01", 105)

        content = self._query("2024-02-01", "2024-02-09")["data"]["private"]["occupancy"]

        # Every day, including the weekend, the holiday and the retreat
        assert content["dates"] == [f"2024-02-0{day}" for day in range(1, 10)]
        assert content["miscEvents"] == [{"name": "Misc"}]

        user_a, user_b = content["users"]
        assert user_a["user"]["id"] == self.gID(self.user_a.pk)
        assert user_b["user"]["id"] == self.gID(self.user_b.pk)
        day_kwargs = {
            "workFromHome": None,
            "expectedHours": 7.0,
            "lateByDays": None,
            "loggedDuringStandup": False,
            "isPending": False,
        }
        off_day_kwargs = {**day_kwargs, "leave": None, "expectedHours": 0.0}
        assert user_a["days"] == [
            {**day_kwargs, "date": "2024-02-01", "hours": 7.0, "leave": None, "occupancy": 1.0},
            {**day_kwargs, "date": "2024-02-02", "hours": 1.0, "leave": "FULL", "occupancy": 0.0, "expectedHours": 0.0},
            # Hours on a non-working day are against a full working day
            {**off_day_kwargs, "date": "2024-02-03", "hours": 1.0, "occupancy": 0.14},
            {**off_day_kwargs, "date": "2024-02-04", "hours": None, "occupancy": None},
            {
                "date": "2024-02-05",
                "hours": 3.5,
                "leave": "FIRST_HALF",
                "workFromHome": "SECOND_HALF",
                "occupancy": 1.0,
                "expectedHours": 3.5,
                "lateByDays": None,
                "loggedDuringStandup": False,
                "isPending": False,
            },
            {**off_day_kwargs, "date": "2024-02-06", "hours": 2.0, "occupancy": 0.29},
            {**day_kwargs, "date": "2024-02-07", "hours": None, "leave": None, "occupancy": None},
            {**day_kwargs, "date": "2024-02-08", "hours": 7.0, "leave": None, "occupancy": 1.0, "workFromHome": "FULL"},
            {**off_day_kwargs, "date": "2024-02-09", "hours": None, "occupancy": None},
        ]
        assert user_a["summary"] == {
            # Includes hours on the leave day, the weekend and the holiday
            "hours": 21.5,
            # 5 working days, minus a full and a half day of leave
            "expectedHours": 24.5,
            "occupancy": 0.88,
            "leaveDays": 1.5,
            "workFromHomeDays": 1.5,
            "missingDays": 1,
            "missingShare": 0.25,
            # Includes the entries on the weekend and the holiday
            "entries": 6,
            # Working days without leave hold the rest of the hours
            "nonWorkingDayHours": 3.0,
            "onLeaveHours": 1.0,
            "dueDays": 4,
            # The day without entries is missing, not late
            "lateDays": 0,
            "lateShare": 0.0,
            "standupDays": 0,
            "standupShare": 0.0,
            "projectsPerDay": 1.0,
            "leaveConflictDays": 1,
            "longEntries": 2,
            "longEntryShare": 0.6512,
            "vagueEntries": 0,
            "vagueEntryShare": 0.0,
        }
        assert user_b["summary"] == {
            "hours": 3.5,
            "expectedHours": 35.0,
            "occupancy": 0.1,
            "leaveDays": 0.0,
            "workFromHomeDays": 0.0,
            "missingDays": 4,
            "missingShare": 0.8,
            "entries": 2,
            "nonWorkingDayHours": 0.0,
            "onLeaveHours": 0.0,
            "dueDays": 5,
            "lateDays": 0,
            "lateShare": 0.0,
            "standupDays": 0,
            "standupShare": 0.0,
            "projectsPerDay": 1.0,
            "leaveConflictDays": 0,
            "longEntries": 0,
            "longEntryShare": 0.0,
            "vagueEntries": 0,
            "vagueEntryShare": 0.0,
        }
        assert content["summary"] == {
            "hours": 25.0,
            "expectedHours": 59.5,
            "occupancy": 0.42,
            "leaveDays": 1.5,
            "workFromHomeDays": 1.5,
            "missingDays": 5,
            "missingShare": 0.5556,
            "entries": 8,
            "nonWorkingDayHours": 3.0,
            "onLeaveHours": 1.0,
            "dueDays": 9,
            "lateDays": 0,
            "lateShare": 0.0,
            "standupDays": 0,
            "standupShare": 0.0,
            "projectsPerDay": 1.0,
            "leaveConflictDays": 1,
            "longEntries": 2,
            "longEntryShare": 0.56,
            "vagueEntries": 0,
            "vagueEntryShare": 0.0,
        }
        assert content["missingPeople"] == 2
        working_day = {"isWorkingDay": True, "eventName": None}
        off_day = {"isWorkingDay": False, "eventName": None}
        assert content["daySummaries"] == [
            {
                **working_day,
                "date": "2024-02-01",
                "summary": {"hours": 10.5, "expectedHours": 14.0, "occupancy": 0.75, "entries": 3},
            },
            {
                **working_day,
                "date": "2024-02-02",
                "summary": {"hours": 1.0, "expectedHours": 7.0, "occupancy": 0.14, "entries": 1},
            },
            {
                **off_day,
                "date": "2024-02-03",
                "summary": {"hours": 1.0, "expectedHours": 0, "occupancy": None, "entries": 1},
            },
            {**off_day, "date": "2024-02-04", "summary": {"hours": 0, "expectedHours": 0, "occupancy": None, "entries": 0}},
            {
                **working_day,
                "date": "2024-02-05",
                "summary": {"hours": 3.5, "expectedHours": 10.5, "occupancy": 0.33, "entries": 1},
            },
            {
                **off_day,
                "eventName": "Holiday",
                "date": "2024-02-06",
                "summary": {"hours": 2.0, "expectedHours": 0, "occupancy": None, "entries": 1},
            },
            {
                **working_day,
                "date": "2024-02-07",
                "summary": {"hours": 0.0, "expectedHours": 14.0, "occupancy": 0.0, "entries": 0},
            },
            {
                **working_day,
                "date": "2024-02-08",
                "summary": {"hours": 7.0, "expectedHours": 14.0, "occupancy": 0.5, "entries": 1},
            },
            {
                **off_day,
                "eventName": "Retreat",
                "date": "2024-02-09",
                "summary": {"hours": 0, "expectedHours": 0, "occupancy": None, "entries": 0},
            },
        ]

    def test_late_logging(self):
        for date, duration, created_date in [
            # Created at 08:45 local time on the next working day: on time
            ("2024-02-01", 420, "2024-02-02T03:00"),
            # The next working day of a Friday is the Monday
            ("2024-02-02", 420, "2024-02-05T03:15"),
            # The next working day skips the holiday
            ("2024-02-05", 60, "2024-02-07T03:00"),
            ("2024-02-07", 240, "2024-02-10"),
            # Created at 09:15 local time on the next working day, after the retreat: late
            ("2024-02-08", 180, "2024-02-13T03:30"),
            # Hours on a weekend are late, but the day is not a working day
            ("2024-02-03", 60, "2024-02-08"),
        ]:
            self._time_entry(self.user_a, date, duration, created_date)
        # The next working day of user B skips their leave
        JournalFactory.create(user=self.user_b, date="2024-02-02", leave_type=Journal.LeaveType.FULL)
        for date, created_date in [
            # Created at 08:45 local time on the Monday after the leave: on time
            ("2024-02-01", "2024-02-05T03:00"),
            # Created at 09:20 local time: late, during the standup
            ("2024-02-05", "2024-02-07T03:35"),
            # Created at 09:30 local time: late, after the standup
            ("2024-02-07", "2024-02-08T03:45"),
        ]:
            self._time_entry(self.user_b, date, 420, created_date)

        content = self._query("2024-02-01", "2024-02-09")["data"]["private"]["occupancy"]

        user_a, user_b = content["users"]
        late_by_days = {day["date"]: day["lateByDays"] for day in user_a["days"] if day["lateByDays"]}
        assert late_by_days == {"2024-02-07": 3, "2024-02-08": 5}
        late_by_days = {day["date"]: day["lateByDays"] for day in user_b["days"] if day["lateByDays"]}
        assert late_by_days == {"2024-02-05": 2, "2024-02-07": 1}
        assert [day["date"] for day in user_b["days"] if day["loggedDuringStandup"]] == ["2024-02-05"]
        assert content["dataAsOf"] == "2024-02-13T03:30:00+00:00"
        late_figures = {"dueDays": 5, "lateDays": 2, "lateShare": 0.4, "standupDays": 1}
        assert {key: user_a["summary"][key] for key in late_figures} == late_figures
        # Leaves out the day without entries, which is missing
        late_figures = {"dueDays": 4, "lateDays": 2, "lateShare": 0.5, "standupDays": 1}
        assert {key: user_b["summary"][key] for key in late_figures} == late_figures
        late_figures = {"dueDays": 9, "lateDays": 4, "lateShare": 0.4444, "standupDays": 2}
        assert {key: content["summary"][key] for key in late_figures} == late_figures

    def test_pending_days(self):
        self._time_entry(self.user_a, "2024-02-05", 420)
        self._time_entry(self.user_b, "2024-02-01", 420)
        # The next working day of user B is after the leave
        JournalFactory.create(user=self.user_b, date="2024-02-07", leave_type=Journal.LeaveType.FULL)

        # At 09:00 local time on the first working day after the holiday
        content = self._query("2024-02-01", "2024-02-06", now="2024-02-07T03:15")["data"]["private"]["occupancy"]

        user_a, user_b = content["users"]
        assert get_pending_dates(user_a) == ["2024-02-05", "2024-02-06"]
        assert user_a["summary"]["missingDays"] == 2
        # Without entries on the pending day
        assert user_b["summary"]["missingDays"] == 1
        assert user_b["summary"]["expectedHours"] == 21
        assert content["summary"]["missingDays"] == 3

        # At 09:15 local time, the deadline of user A
        content = self._query("2024-02-01", "2024-02-06", now="2024-02-07T03:30")["data"]["private"]["occupancy"]
        user_a, user_b = content["users"]
        assert get_pending_dates(user_a) == []
        assert get_pending_dates(user_b) == ["2024-02-05", "2024-02-06"]
        assert content["summary"]["missingDays"] == 3

        # Past months have no pending dates
        content = self._query("2024-02-01", "2024-02-06")["data"]["private"]["occupancy"]
        assert [get_pending_dates(user) for user in content["users"]] == [[], []]
        assert content["dataAsOf"] == "2024-02-05T06:00:00+00:00"
        assert content["summary"]["missingDays"] == 4

    def test_previous(self):
        self._time_entry(self.user_a, "2024-01-02", 420)
        self._time_entry(self.user_a, "2024-02-01", 210)

        content = self._query("2024-02-01", "2024-02-09")["data"]["private"]["occupancy"]

        previous = content["previous"]
        assert (previous["startDate"], previous["endDate"]) == ("2024-01-01", "2024-01-09")
        assert previous["missingPeople"] == 2
        assert {key: previous["summary"][key] for key in ["hours", "expectedHours", "missingDays"]} == {
            "hours": 7.0,
            "expectedHours": 98.0,
            "missingDays": 13,
        }
        assert content["summary"]["hours"] == 3.5

    def test_projects_and_long_days(self):
        self._time_entry(self.user_a, "2024-02-01", 300)
        self._time_entry(self.user_a, "2024-02-02", 300)
        # Ties with the first project, with later activity
        self._time_entry(self.user_a, "2024-02-05", 600, task=self.task_2)
        # Outside the range
        self._time_entry(self.user_a, "2024-01-31", 600)

        content = self._query("2024-02-01", "2024-02-09")["data"]["private"]["occupancy"]

        user_a, user_b = content["users"]
        assert user_a["longDates"] == ["2024-02-05"]
        assert user_a["projects"] == [
            {"project": {"id": self.gID(project.pk)}, "hours": 10.0, "share": 0.5}
            for project in [self.project_2, self.project]
        ]
        assert user_b["longDates"] == []
        assert user_b["projects"] == []

    def test_flagged_entries(self):
        for date, duration, status, description in [
            # Long
            ("2024-02-01", 360, TimeEntry.Status.DONE, "Built the export of the report"),
            ("2024-02-01", 359, TimeEntry.Status.DONE, "Built the export of the report"),
            # Vague at any length
            ("2024-02-01", 15, TimeEntry.Status.DONE, "  Standup "),
            ("2024-02-02", 15, TimeEntry.Status.DONE, ""),
            # Two words are vague from two hours
            ("2024-02-02", 119, TimeEntry.Status.DONE, "Daily standup"),
            ("2024-02-02", 120, TimeEntry.Status.DONE, "Random meetings"),
            # TODO is not logged, so neither long nor vague
            ("2024-02-05", 420, TimeEntry.Status.TODO, "Export"),
            ("2024-02-08", 60, TimeEntry.Status.DOING, "Built the export of the report"),
        ]:
            self._time_entry(self.user_a, date, duration, status=status, description=description)

        content = self._query("2024-02-01", "2024-02-09")["data"]["private"]["occupancy"]

        user_a, user_b = content["users"]
        assert [
            (entry["date"], entry["hours"], entry["isLong"], entry["isVague"]) for entry in user_a["flaggedEntries"]
        ] == [
            ("2024-02-01", 6.0, True, False),
            ("2024-02-01", 0.25, False, True),
            ("2024-02-02", 0.25, False, True),
            ("2024-02-02", 2.0, False, True),
        ]
        assert user_a["flaggedEntries"][0]["project"] == {"id": self.gID(self.project.pk)}
        flag_counts = {
            "longEntries": 1,
            "longEntryShare": 0.3436,
            "vagueEntries": 3,
            "vagueEntryShare": 0.4286,
        }
        assert {key: user_a["summary"][key] for key in flag_counts} == flag_counts
        assert {key: content["summary"][key] for key in flag_counts} == flag_counts
        assert user_b["flaggedEntries"] == []

    def test_projects_per_day(self):
        ur_kwargs = dict(created_by=self.user_a, modified_by=self.user_a)
        blanket_project = ProjectFactory.create(
            name="Togglecorp",
            project_client=self.project.project_client,
            contractor=self.project.contractor,
            **ur_kwargs,
        )
        blanket_task = TaskFactory.create(
            contract=ContractFactory.create(project=blanket_project, **ur_kwargs),
            **ur_kwargs,
        )
        for date, duration, task in [
            ("2024-02-01", 60, self.task),
            ("2024-02-01", 60, self.task_2),
            ("2024-02-01", 300, blanket_task),
            # Only the blanket project
            ("2024-02-02", 420, blanket_task),
            # Two entries of one project
            ("2024-02-05", 120, self.task_2),
            ("2024-02-05", 60, self.task_2),
        ]:
            self._time_entry(self.user_a, date, duration, task=task)

        content = self._query("2024-02-01", "2024-02-09")["data"]["private"]["occupancy"]

        user_a, user_b = content["users"]
        assert user_a["summary"]["projectsPerDay"] == 1.0
        # The blanket project has the most hours, but is left out
        assert user_a["topProject"] == {"project": {"id": self.gID(self.project_2.pk)}, "hours": 4.0, "share": 0.8}
        assert user_b["summary"]["projectsPerDay"] is None
        assert user_b["topProject"] is None

    def test_query_count_is_constant(self):
        self._time_entry(self.user_a, "2024-02-01", 60)
        # Leaves the session queries of the first request out of the counts
        self._query("2024-02-01", "2024-02-09")
        with CaptureQueriesContext(connection) as before:
            self._query("2024-02-01", "2024-02-09")
        user = UserFactory.create(first_name="D", date_joined=self.JOINED)
        for date in ["2024-01-03", "2024-02-01", "2024-02-05"]:
            self._time_entry(user, date, 60, created_date="2024-02-09", task=self.task_2)
            self._time_entry(self.user_b, date, 60)
        JournalFactory.create(user=user, date="2024-01-04", leave_type=Journal.LeaveType.FULL)
        with CaptureQueriesContext(connection) as after:
            content = self._query("2024-02-01", "2024-02-09")
        assert len(content["data"]["private"]["occupancy"]["users"]) == 3
        assert len(after) == len(before)

    def _query_person(self, user_id, end_date: str) -> dict:
        self.force_login(self.user_a)
        with mock.patch("apps.common.models.timezone.now") as now_mock:
            now_mock.return_value = pytz.utc.localize(datetime.datetime(2024, 12, 2))
            cache.clear()
            return self.query_check(
                self.Query.OCCUPANCY_PERSON,
                variables={"userId": user_id, "endDate": end_date},
            )["data"]["private"]["occupancyPerson"]

    def test_person(self):
        # Logged late
        self._time_entry(self.user_a, "2024-01-02", 420, created_date="2024-01-10")
        self._time_entry(self.user_a, "2024-02-01", 420)
        for date, leave_type in [
            ("2024-01-15", Journal.LeaveType.FULL),
            # Not a working day
            ("2024-02-03", Journal.LeaveType.FULL),
            ("2024-02-05", Journal.LeaveType.FIRST_HALF),
            ("2024-02-07", Journal.LeaveType.FULL),
        ]:
            JournalFactory.create(user=self.user_a, date=date, leave_type=leave_type)
        for date, wfh_type in [
            ("2024-01-03", Journal.WorkFromHomeType.FULL),
            # Not a working day
            ("2024-02-04", Journal.WorkFromHomeType.FULL),
            ("2024-02-08", Journal.WorkFromHomeType.SECOND_HALF),
        ]:
            JournalFactory.create(user=self.user_a, date=date, wfh_type=wfh_type)

        # Leaves the session queries of the first request out of the counts
        self._query_person(self.gID(self.user_b.pk), "2024-02-09")
        with CaptureQueriesContext(connection) as before:
            self._query_person(self.gID(self.user_b.pk), "2024-02-09")
        with CaptureQueriesContext(connection) as after:
            content = self._query_person(self.gID(self.user_a.pk), "2024-02-09")
        assert len(after) == len(before)

        # Joined in January
        before_joining = [
            {
                "startDate": f"2023-{month:02}-01",
                "hours": 0.0,
                "expectedHours": 0.0,
                "occupancy": None,
                "lateShare": None,
                "leaveDays": 0.0,
                "workFromHomeDays": 0.0,
            }
            for month in range(3, 13)
        ]
        assert content == {
            "months": [
                *before_joining,
                # 23 working days, less a day of leave, with one logged late and the rest missing
                {
                    "startDate": "2024-01-01",
                    "hours": 7.0,
                    "expectedHours": 154.0,
                    "occupancy": 0.0455,
                    "lateShare": 0.0455,
                    "leaveDays": 1.0,
                    "workFromHomeDays": 1.0,
                },
                # Up to the end date, less one and a half days of leave
                {
                    "startDate": "2024-02-01",
                    "hours": 7.0,
                    "expectedHours": 24.5,
                    "occupancy": 0.2857,
                    "lateShare": 0.0,
                    "leaveDays": 1.5,
                    "workFromHomeDays": 0.5,
                },
            ],
            "leaveDaysThisYear": 2.5,
        }
        assert self._query_person("0", "2024-02-09") is None

    def test_employment_range(self):
        joiner = UserFactory.create(first_name="D", date_joined=pytz.utc.localize(datetime.datetime(2024, 2, 5)))
        # Left, so excluded from the slides, with entries within the range
        leaver = UserFactory.create(first_name="E", date_joined=self.JOINED, is_active=False, exclude_from_slides=True)
        self._time_entry(leaver, "2024-02-01", 420)
        # Not listed: joined after the range
        UserFactory.create(first_name="G", date_joined=pytz.utc.localize(datetime.datetime(2024, 2, 10)))

        content = self._query("2024-02-01", "2024-02-09")["data"]["private"]["occupancy"]

        users_by_id = {user["user"]["id"]: user for user in content["users"]}
        assert set(users_by_id) == {self.gID(user.pk) for user in [self.user_a, self.user_b, joiner, leaver]}
        # Employed up to the last entry
        assert [day["expectedHours"] for day in users_by_id[self.gID(leaver.pk)]["days"]] == [7, 0, 0, 0, 0, 0, 0, 0, 0]
        joiner_content = users_by_id[self.gID(joiner.pk)]
        assert [day["expectedHours"] for day in joiner_content["days"]] == [0, 0, 0, 0, 7, 0, 7, 7, 0]
        assert joiner_content["summary"]["expectedHours"] == 21
        assert joiner_content["summary"]["missingDays"] == 3

        # Not listed in the months after leaving
        content = self._query("2024-03-01", "2024-03-09")["data"]["private"]["occupancy"]
        assert self.gID(leaver.pk) not in [user["user"]["id"] for user in content["users"]]

    def test_range_validation(self):
        for start_date, end_date in [
            ("2024-02-09", "2024-02-01"),
            ("2024-01-01", "2024-03-03"),
        ]:
            content = self._query(start_date, end_date, assert_errors=True)
            assert content["data"] is None, (start_date, end_date)
        # Longest accepted range
        content = self._query("2024-01-01", "2024-03-02")
        assert content["data"]["private"]["occupancy"]["endDate"] == "2024-03-02"
