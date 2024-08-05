from apps.project.factories import ClientFactory, ContractorFactory, ProjectFactory
from apps.track.factories import ContractFactory, TaskFactory, TimeTrackFactory
from apps.track.models import TimeTrack
from apps.user.factories import UserFactory
from main.tests import TestCase


class TestTrackQuery(TestCase):
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

        MY_TIME_TRACKS = """
            query MyQuery($date: Date!) {
              private {
                myTimeTracks(date: $date) {
                  id
                  date
                  taskId
                  task {
                    id
                    name
                  }
                  taskType
                  taskTypeDisplay
                  userId
                  user {
                    id
                    displayName
                  }
                  isDone
                  duration
                  description
                  startTime
                }
              }
            }
        """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = UserFactory.create()
        cls.user_2 = UserFactory.create()
        cls.ur_kwargs = dict(created_by=cls.user, modified_by=cls.user)
        cls.client = ClientFactory.create(**cls.ur_kwargs)
        cls.contractor = ContractorFactory.create(**cls.ur_kwargs)

        cls.project = ProjectFactory.create(
            client=cls.client,
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
        self.assertEqual(
            content["data"]["private"]["allActiveContracts"],
            [
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
                        ]
                    ),
                    project=dict(
                        id=self.gID(contract.project.id),
                        name=contract.project.name,
                    ),
                )
                for contract in self.active_contracts[::-1]
            ],
        )

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
        self.assertEqual(
            content["data"]["private"]["allActiveTasks"],
            [
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
            ],
            None,
        )

    def test_my_time_tracks(self):
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
                task_type=TimeTrack.TaskType.DEVELOPMENT,
                duration="00:30",
                task=task,
                date=date,
            )
            time_entries.extend(TimeTrackFactory.create_batch(count, **common_kwargs))
            # Noise data
            # -- Another date
            TimeTrackFactory.create_batch(count, **{**common_kwargs, "date": "2024-01-07"})
            # -- Another user
            TimeTrackFactory.create_batch(count, **{**common_kwargs, "user": self.user_2})

        # Without authentication -----
        content = self.query_check(
            self.Query.MY_TIME_TRACKS,
            assert_errors=True,
        )
        assert content["data"] is None

        # With authentication -----
        self.force_login(self.user)
        content = self.query_check(self.Query.MY_TIME_TRACKS, variables={"date": date})
        self.maxDiff = None
        self.assertEqual(
            content["data"]["private"]["myTimeTracks"],
            [
                dict(
                    id=self.gID(entry.pk),
                    date=date,
                    taskId=self.gID(entry.task_id),
                    task=dict(
                        id=self.gID(entry.task.id),
                        name=self.gID(entry.task.name),
                    ),
                    taskType=self.genum(entry.task_type),
                    taskTypeDisplay=entry.task_type.label,
                    userId=self.gID(self.user.id),
                    user=dict(
                        id=self.gID(self.user.id),
                        displayName=self.gID(self.user.display_name),
                    ),
                    isDone=False,
                    duration=30 * 60,
                    description=None,
                    startTime=None,
                )
                for entry in time_entries[::-1]
            ],
            None,
        )

    # TODO:
    # - Client
    # - Clients
    # - Contractors
    # - Contractor
    # - TimeTracks
