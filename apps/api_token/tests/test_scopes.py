import datetime
import typing

from django.utils import timezone

from apps.api_token.factories import ApiTokenFactory
from apps.api_token.models import ApiToken
from apps.api_token.scopes import ApiTokenScope
from apps.journal.models import Journal
from apps.project.factories import ClientFactory, ContractorFactory, ProjectFactory
from apps.track.factories import ContractFactory, TaskFactory, TimeEntryFactory
from apps.track.models import TimeEntry
from apps.user.factories import UserFactory
from main.tests import TestCase

S = ApiTokenScope


class ScopeTestCase(TestCase):
    @classmethod
    @typing.override
    def setUpClass(cls):
        super().setUpClass()
        cls.user = UserFactory.create()
        ur_kwargs = dict(created_by=cls.user, modified_by=cls.user)
        project = ProjectFactory.create(
            project_client=ClientFactory.create(**ur_kwargs),
            contractor=ContractorFactory.create(**ur_kwargs),
            **ur_kwargs,
        )
        contract = ContractFactory.create(project=project, **ur_kwargs)
        cls.task = TaskFactory.create(contract=contract, **ur_kwargs)
        cls.date = datetime.date(2024, 1, 10)
        cls.time_entry = TimeEntryFactory.create(user=cls.user, task=cls.task, date=cls.date)

    def token_query(
        self,
        query: str,
        scopes: list[ApiTokenScope],
        variables: dict | None = None,
    ) -> dict:
        token = ApiTokenFactory.create(user=self.user, scopes=[scope.value for scope in scopes])
        response = self.client.post(
            "/graphql/",
            data={"query": query, "variables": variables},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token.secret}",
        )
        assert response.status_code == 200, response.content
        return response.json()

    @staticmethod
    def error_messages(content: dict) -> set[str]:
        return {error["message"] for error in content.get("errors", [])}


class TestQueryScopes(ScopeTestCase):
    ALL_PROJECTS = """
        query {
          private {
            allProjects {
              id
              name
            }
          }
        }
    """

    MY_TIME_ENTRIES = """
        query ($date: Date!) {
          private {
            myTimeEntries(date: $date) {
              id
              task {
                id
                contract {
                  id
                  project {
                    id
                  }
                }
              }
              user {
                id
              }
            }
          }
        }
    """

    def test_root_field_with_scope(self):
        content = self.token_query(self.ALL_PROJECTS, [S.PROJECT_READ])
        assert "errors" not in content, content
        assert len(content["data"]["private"]["allProjects"]) == 1

    def test_root_field_missing_scope(self):
        content = self.token_query(self.ALL_PROJECTS, [S.TIME_ENTRY_READ, S.USER_READ])
        assert self.error_messages(content) == {"missing scope: project:read"}
        assert content["data"] is None

    def test_write_scope_grants_read(self):
        """
        Creation stores `x:read` with every `x:write`. The check also treats write as read for tokens stored without it.
        """
        content = self.token_query(
            """
            query ($date: Date!) {
              private {
                myTimeEntries(date: $date) {
                  id
                }
              }
            }
            """,
            [S.TIME_ENTRY_WRITE],
            variables={"date": self.date.isoformat()},
        )
        assert "errors" not in content, content
        assert content["data"]["private"]["myTimeEntries"][0]["id"] == self.gID(self.time_entry.pk)

    def test_nested_fields_need_their_own_scope(self):
        variables = {"date": self.date.isoformat()}
        content = self.token_query(self.MY_TIME_ENTRIES, [S.TIME_ENTRY_READ, S.USER_READ], variables=variables)
        assert self.error_messages(content) == {"missing scope: project:read"}
        assert [error["path"] for error in content["errors"]] == [["private", "myTimeEntries", 0, "task"]]

        content = self.token_query(self.MY_TIME_ENTRIES, [S.TIME_ENTRY_READ, S.PROJECT_READ], variables=variables)
        assert self.error_messages(content) == {"missing scope: user:read"}

        content = self.token_query(
            self.MY_TIME_ENTRIES,
            [S.TIME_ENTRY_READ, S.PROJECT_READ, S.USER_READ],
            variables=variables,
        )
        assert "errors" not in content, content
        entry = content["data"]["private"]["myTimeEntries"][0]
        assert entry["id"] == self.gID(self.time_entry.pk)

    def test_nested_scope_through_paginated_list(self):
        content = self.token_query(
            """
            query {
              private {
                projects {
                  count
                  items {
                    id
                    createdBy {
                      id
                    }
                  }
                }
              }
            }
            """,
            [S.PROJECT_READ],
        )
        assert self.error_messages(content) == {"missing scope: user:read"}

    def test_field_with_multiple_scopes(self):
        query = """
            query {
              private {
                dailySummary(dateGte: "2024-01-01", dateLte: "2024-01-02") {
                  id
                  totalMinutes
                  leaveType
                }
              }
            }
        """
        content = self.token_query(query, [S.TIME_ENTRY_READ])
        assert self.error_messages(content) == {"missing scope: journal:read"}
        content = self.token_query(query, [S.TIME_ENTRY_READ, S.JOURNAL_READ])
        assert "errors" not in content, content

    def test_public_and_enums_need_no_scope(self):
        content = self.token_query(
            """
            query {
              public {
                me {
                  id
                  email
                }
              }
              enums {
                TimeEntryStatus {
                  key
                  label
                }
              }
            }
            """,
            [S.EVENT_READ],
        )
        assert "errors" not in content, content
        assert content["data"]["public"]["me"]["id"] == self.gID(self.user.pk)

    def test_typename_and_private_id_need_no_scope(self):
        content = self.token_query("query { __typename private { __typename id } }", [S.EVENT_READ])
        assert "errors" not in content, content

    def test_session_requests_have_no_scope_checks(self):
        self.force_login(self.user)
        content = self.query_check(self.MY_TIME_ENTRIES, variables={"date": self.date.isoformat()})
        assert content["data"]["private"]["myTimeEntries"][0]["user"]["id"] == self.gID(self.user.pk)


class TestMutationScopes(ScopeTestCase):
    CREATE_TIME_ENTRY = """
        mutation ($data: TimeEntryCreateInput!) {
          private {
            createTimeEntry(data: $data) {
              ok
              errors
            }
          }
        }
    """

    UPDATE_JOURNAL = """
        mutation ($date: Date!, $data: JournalUpdateInput!) {
          private {
            updateJournal(date: $date, data: $data) {
              ok
              errors
            }
          }
        }
    """

    def _time_entry_variables(self):
        return {
            "data": {
                "clientId": "scope-test",
                "task": self.gID(self.task.pk),
                "date": self.date.isoformat(),
                "type": self.genum(TimeEntry.Type.DEVELOPMENT),
                "status": self.genum(TimeEntry.Status.TODO),
            },
        }

    def test_mutation_missing_write_scope_does_not_run(self):
        count = TimeEntry.objects.count()
        content = self.token_query(self.CREATE_TIME_ENTRY, [S.TIME_ENTRY_READ], variables=self._time_entry_variables())
        assert self.error_messages(content) == {"missing scope: time_entry:write"}
        assert TimeEntry.objects.count() == count

    def test_mutation_with_write_scope(self):
        count = TimeEntry.objects.count()
        content = self.token_query(self.CREATE_TIME_ENTRY, [S.TIME_ENTRY_WRITE], variables=self._time_entry_variables())
        assert "errors" not in content, content
        assert content["data"]["private"]["createTimeEntry"]["ok"] is True
        assert TimeEntry.objects.count() == count + 1

    def test_mutation_result_readable_with_write_scope(self):
        query = """
            mutation ($data: TimeEntryCreateInput!) {
              private {
                createTimeEntry(data: $data) {
                  ok
                  result {
                    id
                  }
                }
              }
            }
        """
        content = self.token_query(query, [S.TIME_ENTRY_WRITE], variables=self._time_entry_variables())
        assert "errors" not in content, content
        assert content["data"]["private"]["createTimeEntry"]["result"]["id"]

    def test_journal_write_scope(self):
        variables = {"date": "2024-01-11", "data": {"journalText": "Hello"}}
        content = self.token_query(self.UPDATE_JOURNAL, [S.JOURNAL_READ], variables=variables)
        assert self.error_messages(content) == {"missing scope: journal:write"}
        assert not Journal.objects.filter(user=self.user, date="2024-01-11").exists()

        content = self.token_query(self.UPDATE_JOURNAL, [S.JOURNAL_WRITE], variables=variables)
        assert "errors" not in content, content
        assert Journal.objects.get(user=self.user, date="2024-01-11").journal_text == "Hello"


class TestTokenManagementIsSessionOnly(ScopeTestCase):
    ALL_SCOPES: typing.ClassVar = list(ApiTokenScope)

    def test_my_api_tokens_denied(self):
        content = self.token_query("query { private { myApiTokens { id } } }", self.ALL_SCOPES)
        assert content["data"] is None
        assert len(content["errors"]) == 1

    def test_create_api_token_denied(self):
        count = ApiToken.objects.count()
        content = self.token_query(
            """
            mutation ($data: ApiTokenCreateInput!) {
              private {
                createApiToken(data: $data) {
                  ok
                }
              }
            }
            """,
            self.ALL_SCOPES,
            variables={
                "data": {
                    "name": "from token",
                    "scopes": ["TIME_ENTRY_READ"],
                    "expiresAt": (timezone.now() + datetime.timedelta(days=30)).isoformat(),
                },
            },
        )
        assert content["data"] is None
        # Only the token used for the request
        assert ApiToken.objects.count() == count + 1

    def test_revoke_api_token_denied(self):
        other = ApiTokenFactory.create(user=self.user)
        content = self.token_query(
            "mutation ($id: ID!) { private { revokeApiToken(id: $id) { ok } } }",
            self.ALL_SCOPES,
            variables={"id": self.gID(other.pk)},
        )
        assert content["data"] is None
        other.refresh_from_db()
        assert other.revoked_at is None


class TestScalarFieldsFromOtherResources(ScopeTestCase):
    """
    Scalar/enum fields that expose another resource's data carry their own field tag.
    """

    def assert_field_scope(self, query: str, granted: list[ApiTokenScope], needed: ApiTokenScope):
        content = self.token_query(query, granted)
        assert self.error_messages(content) == {f"missing scope: {needed.value}"}, content
        content = self.token_query(query, [*granted, needed])
        assert "errors" not in content, content

    def test_user_leave_and_wfh_today_need_journal_read(self):
        for field in ["leaveToday", "workFromHomeToday"]:
            self.assert_field_scope(
                f"query {{ private {{ users {{ items {{ id {field} }} }} }} }}",
                [S.USER_READ],
                S.JOURNAL_READ,
            )

    def test_me_leave_and_wfh_today_need_journal_read(self):
        for field in ["leaveToday", "workFromHomeToday"]:
            self.assert_field_scope(f"query {{ public {{ me {{ id {field} }} }} }}", [], S.JOURNAL_READ)

    def test_me_last_working_date_needs_journal_and_event_read(self):
        query = "query { public { me { id myLastWorkingDate } } }"
        content = self.token_query(query, [])
        assert self.error_messages(content) == {"missing scope: event:read, journal:read"}, content
        content = self.token_query(query, [S.JOURNAL_READ])
        assert self.error_messages(content) == {"missing scope: event:read"}, content
        # NOTE: The resolver itself fails in async context (sync ORM call), so only scope errors are checked here
        content = self.token_query(query, [S.JOURNAL_READ, S.EVENT_READ])
        assert not any(message.startswith("missing scope") for message in self.error_messages(content)), content


class TestSessionOnlyFields(ScopeTestCase):
    def test_all_users_time_entries_not_available_to_tokens(self):
        superuser = UserFactory.create(is_superuser=True)
        token = ApiTokenFactory.create(user=superuser, scopes=[scope.value for scope in ApiTokenScope])
        for query, field in [
            ("query { private { timeEntries { count } } }", "timeEntries"),
            ("query { private { allTimeEntries(filters: {}) { id } } }", "allTimeEntries"),
        ]:
            response = self.client.post(
                "/graphql/",
                data={"query": query},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {token.secret}",
            )
            content = response.json()
            assert content["data"] is None
            assert self.error_messages(content) == {f"PrivateQuery.{field} is not available to API tokens"}

    def test_standup_not_available_to_tokens(self):
        content = self.token_query(
            'query { private { dailyStandup(date: "2024-01-10") { id } } }',
            list(ApiTokenScope),
        )
        assert content["data"] is None
        assert self.error_messages(content) == {"PrivateQuery.dailyStandup is not available to API tokens"}

    def test_login_expire_not_available_to_tokens(self):
        content = self.token_query("query { public { me { id loginExpire } } }", list(ApiTokenScope))
        assert self.error_messages(content) == {"UserMeType.loginExpire is not available to API tokens"}

    def test_logout_not_available_to_tokens(self):
        self.force_login(self.user)
        session_key = self.client.session.session_key
        content = self.token_query("mutation { public { logout { ok } } }", list(ApiTokenScope))
        assert self.error_messages(content) == {"PublicMutation.logout is not available to API tokens"}
        # The session sent along with the token is untouched
        assert self.client.session.session_key == session_key
        assert self.query_check("query { public { me { id } } }")["data"]["public"]["me"]["id"] == self.gID(self.user.pk)

    def test_login_not_available_to_tokens(self):
        content = self.token_query(
            "mutation ($data: LoginInput!) { public { login(data: $data) { ok } } }",
            list(ApiTokenScope),
            variables={"data": {"email": self.user.email, "password": "wrong"}},
        )
        assert self.error_messages(content) == {"PublicMutation.login is not available to API tokens"}


class TestScopeDenialLogging(ScopeTestCase):
    def test_denials_logged_at_info_without_traceback(self):
        with self.assertLogs("strawberry.execution", level="DEBUG") as logs:
            content = self.token_query(TestQueryScopes.ALL_PROJECTS, [S.TIME_ENTRY_READ])
            self.token_query("query { private { myApiTokens { id } } }", list(ApiTokenScope))
        assert self.error_messages(content) == {"missing scope: project:read"}
        assert [(record.levelname, record.getMessage()) for record in logs.records] == [
            ("INFO", "API token scope denial: missing scope: project:read"),
            ("INFO", "API token scope denial: PrivateQuery.myApiTokens is not available to API tokens"),
        ]
        assert all(record.exc_info is None for record in logs.records)

    def test_other_errors_still_logged_at_error(self):
        self.force_login(self.user)
        with self.assertLogs("strawberry.execution", level="DEBUG") as logs:
            self.query_check(
                'query { private { dailySummary(dateGte: "2020-01-01", dateLte: "2024-01-01") { id } } }',
                assert_errors=True,
            )
        assert [record.levelname for record in logs.records] == ["ERROR"]
