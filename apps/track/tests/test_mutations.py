from apps.project.factories import ClientFactory, ContractorFactory, ProjectFactory
from apps.track.factories import ContractFactory, TaskFactory, TimeTrackFactory
from apps.track.models import TimeTrack
from apps.user.factories import UserFactory
from main.tests import TestCase


class TestTrackBulkMutation(TestCase):
    class Mutation:
        BULK_TIME_TRACK = """
            fragment TimeTrackTypeResponse on TimeTrackType {
              id
              clientId
              userId
              date
              taskId
              taskType
              isDone
              duration
              description
              startTime
            }

            mutation MyMutation(
                $deleteIds: [ID!],
                $items: [TimeTrackBulkCreateInput!],
            ) {
              private {
                bulkTimeTrack(items: $items, deleteIds: $deleteIds) {
                  errors
                  results {
                    ...TimeTrackTypeResponse
                  }
                  deleted {
                    ...TimeTrackTypeResponse
                  }
                }
              }
            }
        """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = UserFactory.create()
        cls.user_02 = UserFactory.create()

        cls.ur_kwargs = dict(created_by=cls.user, modified_by=cls.user)
        cls.client = ClientFactory.create(**cls.ur_kwargs)
        cls.contractor = ContractorFactory.create(**cls.ur_kwargs)

        cls.project = ProjectFactory.create(
            client=cls.client,
            contractor=cls.contractor,
            **cls.ur_kwargs,
        )

        # Contracts
        cls.active_contract = ContractFactory.create(project=cls.project, **cls.ur_kwargs)
        cls.archived_contract = ContractFactory.create(project=cls.project, is_archived=True, **cls.ur_kwargs)

        # Tasks
        cls.active_tasks = TaskFactory.create_batch(
            5,
            **cls.ur_kwargs,
            contract=cls.active_contract,
            estimated_hours=10,
        )
        cls.archived_tasks = TaskFactory.create_batch(
            5,
            **cls.ur_kwargs,
            contract=cls.active_contract,
            is_archived=True,
            estimated_hours=20,
        )

        cls.common_time_track_kwargs = dict(
            task=cls.active_tasks[1],
            date="2021-01-02",
            task_type=TimeTrack.TaskType.DEVELOPMENT,
            description="Norm description",
            is_done=False,
            duration="00:40",
            start_time="09:30:00",
        )

    def _query(self, _data, **kwargs):
        return self.query_check(
            self.Mutation.BULK_TIME_TRACK,
            variables=_data,
            **kwargs,
        )

    def _get_ids(self, items):
        return [item.pk for item in items]

    def test_bulk_time_track_unauthenticated(self):
        # Without authentication -----
        content = self._query({}, assert_errors=True)
        assert content["data"] is None

    def test_bulk_time_track_create(self):
        # With authentication -----
        self.force_login(self.user)

        data = {
            "items": [
                dict(
                    task=self.gID(self.active_tasks[0].pk),
                    date="2021-01-01",
                    taskType=self.genum(TimeTrack.TaskType.DEVELOPMENT),
                    description="Normal description",
                    isDone=True,
                    duration=30 * 60,
                    startTime="09:30:00",
                    clientId="client-id-01",
                ),
            ],
        }

        content = self._query(data)
        resp_data = content["data"]["private"]["bulkTimeTrack"]
        assert resp_data["errors"] == []
        assert resp_data["deleted"] == []
        self.assertListDictEqual(
            resp_data["results"],
            [
                {
                    **data["items"][0],
                    "userId": self.gID(self.user.pk),
                    "taskId": self.gID(self.active_tasks[0].pk),
                },
            ],
            ignore_keys=["id", "task"],
        )

    def test_bulk_time_track_update(self):
        # With authentication -----
        self.force_login(self.user)
        time_tracks = TimeTrackFactory.create_batch(5, **self.common_time_track_kwargs, user=self.user)

        data = {
            "items": [
                dict(
                    id=self.gID(time_tracks[0].pk),
                    task=self.gID(self.active_tasks[0].pk),
                    date="2021-01-01",
                    taskType=self.genum(TimeTrack.TaskType.DESIGN),
                    description="Normal description - 0",
                    isDone=True,
                    duration=30 * 60,
                    startTime="09:31:00",
                    clientId="client-id-01",
                ),
                dict(
                    id=self.gID(time_tracks[1].pk),
                    task=self.gID(self.active_tasks[0].pk),
                    date="2021-01-02",
                    taskType=self.genum(TimeTrack.TaskType.DEV_OPS),
                    description="Normal description - 1",
                    duration=30 * 60,
                    startTime="09:32:00",
                    clientId="client-id-02",
                ),
                dict(
                    id=self.gID(time_tracks[2].pk),
                    task=self.gID(self.active_tasks[0].pk),
                    taskType=self.genum(TimeTrack.TaskType.DEV_OPS),
                    date="2021-01-02",
                    description="Normal description - 2",
                    clientId="client-id-03",
                ),
            ],
        }

        default_time_track_kwargs = {
            "date": self.common_time_track_kwargs["date"],
            "isDone": self.common_time_track_kwargs["is_done"],
            "startTime": self.common_time_track_kwargs["start_time"],
            "duration": 40 * 60,  # self.common_time_track_kwargs["duration"]
            "userId": self.gID(self.user.pk),
            "taskId": self.gID(self.active_tasks[0].pk),
        }

        content = self._query(data)
        resp_data = content["data"]["private"]["bulkTimeTrack"]
        assert resp_data["errors"] == []
        assert resp_data["deleted"] == []
        self.assertListDictEqual(
            resp_data["results"],
            [
                {
                    **default_time_track_kwargs,
                    **item,
                }
                for item in data["items"][:3]
            ],
            ignore_keys=["task"],
        )

    def test_bulk_time_track_delete(self):
        # With authentication -----
        self.force_login(self.user)
        time_tracks = TimeTrackFactory.create_batch(5, **self.common_time_track_kwargs, user=self.user)
        others_time_tracks = TimeTrackFactory.create_batch(5, **self.common_time_track_kwargs, user=self.user_02)

        try_to_deleted = [*time_tracks[:4], *others_time_tracks]
        needs_to_be_deleted = time_tracks[:4]
        needs_to_be_preserved = [*time_tracks[4:], *others_time_tracks]
        data = {
            "deleteIds": [time_track.pk for time_track in try_to_deleted],
        }

        content = self._query(data)
        resp_data = content["data"]["private"]["bulkTimeTrack"]
        assert resp_data["errors"] == []
        assert resp_data["results"] == []
        self.assertListDictEqual(
            resp_data["deleted"],
            [
                {
                    "id": self.gID(time_track.pk),
                }
                for time_track in needs_to_be_deleted
            ],
            include_keys=["id"],
        )

        current_time_track_ids = set(TimeTrack.objects.values_list("id", flat=True))

        assert current_time_track_ids.isdisjoint(
            set([i.pk for i in needs_to_be_deleted])
        ), "Most of the user's time_track should be deleted"

        assert set(self._get_ids(needs_to_be_preserved)).issubset(
            current_time_track_ids
        ), "All other user's time_track should't be deleted"

    def test_bulk_time_track_mix(self):
        """
        This is mix of all of the above cases.
        NOTE: Will have duplicate piece of code
        """
        # With authentication -----
        self.force_login(self.user)
        time_tracks = TimeTrackFactory.create_batch(5, **self.common_time_track_kwargs, user=self.user)
        others_time_tracks = TimeTrackFactory.create_batch(5, **self.common_time_track_kwargs, user=self.user_02)

        # From test_bulk_time_track_delete
        try_to_deleted = [*time_tracks[2:], *others_time_tracks]
        needs_to_be_deleted = time_tracks[2:]
        needs_to_be_preserved = [*time_tracks[:2], *others_time_tracks]

        data = {
            # From test_bulk_time_track_delete
            "deleteIds": [time_track.pk for time_track in try_to_deleted],
            "items": [
                # From test_bulk_time_track_create
                dict(
                    task=self.gID(self.active_tasks[0].pk),
                    date="2021-01-01",
                    taskType=self.genum(TimeTrack.TaskType.DEVELOPMENT),
                    description="Normal description - 0",
                    isDone=True,
                    duration=30 * 60,
                    startTime="09:30:00",
                    clientId="client-id-00",
                ),
                # From test_bulk_time_track_update
                dict(
                    id=self.gID(time_tracks[0].pk),
                    task=self.gID(self.active_tasks[0].pk),
                    date="2021-01-01",
                    taskType=self.genum(TimeTrack.TaskType.DESIGN),
                    description="Normal description - 1",
                    isDone=True,
                    duration=30 * 60,
                    startTime="09:31:00",
                    clientId="client-id-01",
                ),
                dict(
                    id=self.gID(time_tracks[1].pk),
                    task=self.gID(self.active_tasks[0].pk),
                    date="2021-01-02",
                    taskType=self.genum(TimeTrack.TaskType.DEV_OPS),
                    description="Normal description - 2",
                    duration=30 * 60,
                    startTime="09:32:00",
                    clientId="client-id-02",
                ),
                # -- NOTE: This will be deleted and re-created
                dict(
                    id=self.gID(time_tracks[2].pk),
                    task=self.gID(self.active_tasks[0].pk),
                    taskType=self.genum(TimeTrack.TaskType.DEV_OPS),
                    date="2021-01-02",
                    description="Normal description - 3",
                    clientId="client-id-03",
                ),
            ],
        }

        # From test_bulk_time_track_update
        default_time_track_kwargs = {
            "date": self.common_time_track_kwargs["date"],
            "isDone": self.common_time_track_kwargs["is_done"],
            "startTime": self.common_time_track_kwargs["start_time"],
            "duration": 40 * 60,  # self.common_time_track_kwargs["duration"]
            "userId": self.gID(self.user.pk),
            "taskId": self.gID(self.active_tasks[0].pk),
        }

        self.maxDiff = None

        content = self._query(data)
        resp_data = content["data"]["private"]["bulkTimeTrack"]
        assert resp_data["errors"] == []

        # Create
        self.assertListDictEqual(
            [
                resp_data["results"][0],
                resp_data["results"][3],
            ],
            [
                {
                    **default_time_track_kwargs,
                    **data["items"][0],
                },
                {
                    **default_time_track_kwargs,
                    **data["items"][3],
                    "startTime": None,
                    "duration": None,
                },
            ],
            ignore_keys=["id", "task"],
        )
        # As this is deleted the id should be new
        assert resp_data["results"][3]["id"] > data["items"][3]["id"]

        # Update -- id should be same
        self.assertListDictEqual(
            resp_data["results"][1:2],
            [
                {
                    **default_time_track_kwargs,
                    **item,
                }
                for item in data["items"][1:2]
            ],
            ignore_keys=["task"],
        )

        self.assertListDictEqual(
            resp_data["deleted"],
            [
                {
                    "id": self.gID(time_track.pk),
                }
                for time_track in needs_to_be_deleted
            ],
            include_keys=["id"],
        )

        current_time_track_ids = set(TimeTrack.objects.values_list("id", flat=True))

        assert current_time_track_ids.isdisjoint(
            set(self._get_ids(needs_to_be_deleted))
        ), "Most of the user's time_track should be deleted"

        assert set(self._get_ids(needs_to_be_preserved)).issubset(
            current_time_track_ids
        ), "All other user's time_track should't be deleted"
