import typing

from apps.project.factories import ClientFactory, ContractorFactory, ProjectFactory
from apps.track.factories import ContractFactory, TaskFactory, TimeEntryFactory
from apps.track.models import TimeEntry
from apps.user.factories import UserFactory
from main.tests import TestCase


class TestEntryQuery(TestCase):
    class Query:
        ALL_ACTIVE_CONTRACTS = """
            query MyQuery {
              private {
                allActiveContracts {
                  id
                  isArchived
                  name
                  projectId
                  totalEstimatedHours
                  totalTasksEstimatedHours
                  project {
                    id
                    name
                  }
                }
              }
            }
        """

        ALL_ACTIVE_TASKS = """
            query MyQuery {
              private {
                allActiveTasks {
                  id
                  isArchived
                  name
                  contractId
                  contract {
                    id
                    name
                  }
                  estimatedHours
                }
              }
            }
        """

        MY_TIME_ENTRIES = """
            query MyQuery($date: Date!) {
              private {
                myTimeEntries(date: $date) {
                  id
                  date
                  taskId
                  task {
                    id
                    name
                  }
                  type
                  typeDisplay
                  userId
                  user {
                    id
                    displayName
                  }
                  status
                  duration
                  description
                  startTime
                }
              }
            }
        """

    @classmethod
    @typing.override
    def setUpClass(cls):
        super().setUpClass()
        cls.user = UserFactory.create()
        cls.user_2 = UserFactory.create()
        cls.ur_kwargs = dict(created_by=cls.user, modified_by=cls.user)
        cls.client = ClientFactory.create(**cls.ur_kwargs)
        cls.contractor = ContractorFactory.create(**cls.ur_kwargs)

        cls.project = ProjectFactory.create(
            project_client=cls.client,
            contractor=cls.contractor,
            **cls.ur_kwargs,
        )

        # Contracts
        cls.active_contracts = ContractFactory.create_batch(
            5,
            project=cls.project,
            **cls.ur_kwargs,
        )
        cls.archived_contracts = ContractFactory.create_batch(
            5,
            project=cls.project,
            is_archived=True,
            **cls.ur_kwargs,
        )

        # Tasks
        cls.active_tasks = TaskFactory.create_batch(
            5,
            **cls.ur_kwargs,
            contract=cls.active_contracts[0],
            estimated_hours=10,
        )
        cls.archived_tasks = TaskFactory.create_batch(
            5,
            **cls.ur_kwargs,
            contract=cls.active_contracts[0],
            is_archived=True,
            estimated_hours=20,
        )

    def test_active_contracts(self):
        # Without authentication -----
        content = self.query_check(
            self.Query.ALL_ACTIVE_CONTRACTS,
            assert_errors=True,
        )
        assert content["data"] is None

        # With authentication -----
        self.force_login(self.user)
        content = self.query_check(self.Query.ALL_ACTIVE_CONTRACTS)
        assert content["data"]["private"]["allActiveContracts"] == [
            dict(
                id=self.gID(contract.pk),
                isArchived=contract.is_archived,
                name=contract.name,
                projectId=self.gID(contract.project_id),
                totalEstimatedHours=contract.total_estimated_hours,
                totalTasksEstimatedHours=sum(
                    [
                        task.estimated_hours
                        for task in contract.tasks.all()
                        # if not task.is_archived
                    ],
                ),
                project=dict(
                    id=self.gID(contract.project.id),
                    name=contract.project.name,
                ),
            )
            for contract in self.active_contracts[::-1]
        ]

    def test_active_tasks(self):
        # Without authentication -----
        content = self.query_check(
            self.Query.ALL_ACTIVE_TASKS,
            assert_errors=True,
        )
        assert content["data"] is None

        # With authentication -----
        self.force_login(self.user)
        content = self.query_check(self.Query.ALL_ACTIVE_TASKS)
        assert content["data"]["private"]["allActiveTasks"] == [
            dict(
                id=self.gID(task.pk),
                isArchived=task.is_archived,
                name=task.name,
                contractId=self.gID(task.contract_id),
                estimatedHours=task.estimated_hours,
                contract=dict(
                    id=self.gID(task.contract.id),
                    name=task.contract.name,
                ),
            )
            for task in self.active_tasks[::-1]
        ]

    def test_my_time_entries(self):
        # Dataset
        # -- MY
        tasks = [
            (5, self.active_tasks[0]),
            (4, self.active_tasks[1]),
            (3, self.archived_tasks[0]),
            (2, self.archived_tasks[1]),
        ]
        date = "2024-01-01"
        time_entries = []
        for count, task in tasks:
            common_kwargs = dict(
                user=self.user,
                type=TimeEntry.Type.DEVELOPMENT,
                duration=45,
                task=task,
                date=date,
            )
            time_entries.extend(TimeEntryFactory.create_batch(count, **common_kwargs))
            # Noise data
            # -- Another date
            TimeEntryFactory.create_batch(count, **{**common_kwargs, "date": "2024-01-07"})
            # -- Another user
            TimeEntryFactory.create_batch(count, **{**common_kwargs, "user": self.user_2})

        # Without authentication -----
        content = self.query_check(
            self.Query.MY_TIME_ENTRIES,
            assert_errors=True,
        )
        assert content["data"] is None

        # With authentication -----
        self.force_login(self.user)
        content = self.query_check(self.Query.MY_TIME_ENTRIES, variables={"date": date})
        self.maxDiff = None

        assert content["data"]["private"]["myTimeEntries"] == [
            dict(
                id=self.gID(entry.pk),
                date=date,
                taskId=self.gID(entry.task_id),
                task=dict(
                    id=self.gID(entry.task.id),
                    name=self.gID(entry.task.name),
                ),
                type=self.genum(entry.type),
                typeDisplay=entry.type.label,
                userId=self.gID(self.user.id),
                user=dict(
                    id=self.gID(self.user.id),
                    displayName=self.gID(self.user.display_name),
                ),
                status=self.genum(entry.status),
                duration=45,
                description=None,
                startTime=None,
            )
            for entry in time_entries[::-1]
        ]

    # TODO:
    # - Client
    # - Clients
    # - Contractors
    # - Contractor
    # - TimeEntrys


class TestAllUsersTimeEntriesQuery(TestCase):
    """
    `timeEntries` and `allTimeEntries` return every user's entries, so they are superuser only.
    """

    TIME_ENTRIES = """
        query {
          private {
            timeEntries {
              count
              items {
                id
              }
            }
          }
        }
    """

    ALL_TIME_ENTRIES = """
        query ($filters: TimeEntryFilter!) {
          private {
            allTimeEntries(filters: $filters) {
              id
            }
          }
        }
    """

    @classmethod
    @typing.override
    def setUpClass(cls):
        super().setUpClass()
        cls.user = UserFactory.create()
        cls.superuser = UserFactory.create(is_superuser=True)
        ur_kwargs = dict(created_by=cls.user, modified_by=cls.user)
        project = ProjectFactory.create(
            project_client=ClientFactory.create(**ur_kwargs),
            contractor=ContractorFactory.create(**ur_kwargs),
            **ur_kwargs,
        )
        task = TaskFactory.create(contract=ContractFactory.create(project=project, **ur_kwargs), **ur_kwargs)
        cls.time_entries = [
            TimeEntryFactory.create(user=cls.user, task=task, date="2024-01-10"),
            TimeEntryFactory.create(user=cls.superuser, task=task, date="2024-01-10"),
        ]

    def _queries(self):
        return [
            (self.TIME_ENTRIES, None),
            (self.ALL_TIME_ENTRIES, {"filters": {}}),
        ]

    def test_denied_for_non_superusers(self):
        self.force_login(self.user)
        for query, variables in self._queries():
            content = self.query_check(query, variables=variables, assert_errors=True)
            assert content["data"] is None
            assert [error["message"] for error in content["errors"]] == ["Only superusers can access this"]

    def test_allowed_for_superusers(self):
        self.force_login(self.superuser)
        content = self.query_check(self.TIME_ENTRIES)
        assert content["data"]["private"]["timeEntries"]["count"] == 2
        content = self.query_check(self.ALL_TIME_ENTRIES, variables={"filters": {}})
        assert len(content["data"]["private"]["allTimeEntries"]) == 2


class TestDailySummaryQuery(TestCase):
    DAILY_SUMMARY = """
        query ($dateGte: Date!, $dateLte: Date!) {
          private {
            dailySummary(dateGte: $dateGte, dateLte: $dateLte) {
              id
            }
          }
        }
    """

    @typing.override
    def setUp(self):
        super().setUp()
        self.force_login(UserFactory.create())

    def test_range_up_to_366_days(self):
        content = self.query_check(self.DAILY_SUMMARY, variables={"dateGte": "2024-01-01", "dateLte": "2024-12-31"})
        assert len(content["data"]["private"]["dailySummary"]) == 366

    def test_range_over_366_days_rejected(self):
        content = self.query_check(
            self.DAILY_SUMMARY,
            variables={"dateGte": "2024-01-01", "dateLte": "2025-01-01"},
            assert_errors=True,
        )
        assert [error["message"] for error in content["errors"]] == ["Date range can be at most 366 days."]
