import asyncio
import logging
import typing
from unittest import mock

import strawberry
from strawberry.django.views import AsyncGraphQLView

from apps.api_token.factories import ApiTokenFactory
from apps.api_token.scopes import ApiTokenScope
from apps.project.factories import ClientFactory, ContractorFactory, ProjectFactory
from apps.track.factories import ContractFactory, TaskFactory, TimeEntryFactory
from apps.track.types import TaskType
from apps.user.factories import UserFactory
from main.graphql.errors import UNEXPECTED_ERROR_MESSAGE
from main.graphql.schema import schema
from main.tests import TestCase


class TestErrorMasking(TestCase):
    """
    Unexpected exceptions return a generic message; intended errors keep their text.
    """

    TASK = 'query { private { task(pk: "1") { id } } }'

    @typing.override
    def setUp(self):
        super().setUp()
        self.user = UserFactory.create()
        self.force_login(self.user)

    def _messages(self, query: str, variables: dict | None = None, **kwargs) -> list[str]:
        content = self.query_check(query, variables=variables, assert_errors=True, **kwargs)
        return [error["message"] for error in content["errors"]]

    def test_unexpected_exception_is_masked_and_logged(self):
        with (
            mock.patch.object(TaskType, "get_queryset", side_effect=RuntimeError("boom at /srv/app/secret.py")),
            self.assertLogs("strawberry.execution", level="ERROR") as logs,
        ):
            messages = self._messages(self.TASK)
        assert messages == [UNEXPECTED_ERROR_MESSAGE]
        assert len(logs.records) == 1
        record = logs.records[0]
        assert record.exc_info is not None
        assert isinstance(record.exc_info[1], RuntimeError)
        assert "boom at /srv/app/secret.py" in str(record.exc_info[1])

    def test_unexpected_exception_is_masked_for_tokens(self):
        token = ApiTokenFactory.create(user=self.user, scopes=[ApiTokenScope.PROJECT_READ.value])
        with mock.patch.object(TaskType, "get_queryset", side_effect=RuntimeError("boom")):
            messages = self._messages(self.TASK, HTTP_AUTHORIZATION=f"Bearer {token.secret}")
        assert messages == [UNEXPECTED_ERROR_MESSAGE]

    def test_graphql_error_keeps_text(self):
        messages = self._messages('query { private { dailySummary(dateGte: "2020-01-01", dateLte: "2024-01-01") { id } } }')
        assert messages == ["Date range can be at most 366 days."]

    def test_permission_errors_keep_text(self):
        assert self._messages("query { private { timeEntries { count } } }") == ["Only superusers can access this"]
        self.logout()
        assert self._messages("query { private { id } }") == ["User is not authenticated"]

    def test_scope_errors_keep_text(self):
        token = ApiTokenFactory.create(user=self.user, scopes=[ApiTokenScope.EVENT_READ.value])
        messages = self._messages("query { private { allProjects { id } } }", HTTP_AUTHORIZATION=f"Bearer {token.secret}")
        assert messages == ["missing scope: project:read"]

    def test_not_found_keeps_text(self):
        ur_kwargs = dict(created_by=self.user, modified_by=self.user)
        project = ProjectFactory.create(
            project_client=ClientFactory.create(**ur_kwargs),
            contractor=ContractorFactory.create(**ur_kwargs),
            **ur_kwargs,
        )
        task = TaskFactory.create(contract=ContractFactory.create(project=project, **ur_kwargs), **ur_kwargs)
        others_entry = TimeEntryFactory.create(user=UserFactory.create(), task=task, date="2024-01-10")
        messages = self._messages(
            'mutation ($id: ID!) { private { updateTimeEntry(id: $id, data: {description: "x"}) { ok } } }',
            variables={"id": str(others_entry.pk)},
        )
        assert messages == ["No TimeEntry matches the given query."]

    def test_validation_and_variable_errors_keep_text(self):
        assert self._messages("query { private { notAField } }") == [
            "Cannot query field 'notAField' on type 'PrivateQuery'.",
        ]
        messages = self._messages(
            "query ($date: Date!) { private { myTimeEntries(date: $date) { id } } }",
            variables={"date": "not-a-date"},
        )
        assert len(messages) == 1
        assert messages[0].startswith("Variable '$date' got invalid value 'not-a-date'")


class TestErrorLogging(TestCase):
    @typing.override
    def setUp(self):
        super().setUp()
        self.force_login(UserFactory.create())

    def _post(self, query: str, variables: dict | None = None):
        return self.client.post(
            "/graphql/",
            data={"query": query, "variables": variables},
            content_type="application/json",
        )

    def test_request_errors_logged_at_info_without_values(self):
        sentinel = "s3cr3tSENTINELvalue"
        cases = [
            ("query { private { notAField } }", None, "validation_error"),
            ("query { private { id }", None, "syntax_error"),
            ("query ($date: Date!) { private { myTimeEntries(date: $date) { id } } }", {"date": sentinel}, "variable_error"),
            ("query { private { myTimeEntries(date: " + f'"{sentinel}"' + ") { id } } }", None, "validation_error"),
        ]
        for query, variables, category in cases:
            with self.assertLogs("strawberry.execution", level="DEBUG") as logs:
                self._post(query, variables)
            assert [(record.levelname, record.getMessage()) for record in logs.records] == [
                ("INFO", f"GraphQL request rejected: {category}"),
            ], query
            assert logs.records[0].exc_info is None

    def test_limit_errors_logged_at_info_with_message(self):
        with self.assertLogs("strawberry.execution", level="DEBUG") as logs:
            self._post("query { " + " ".join(f"a{i}: __typename" for i in range(16)) + " }")
        assert [(record.levelname, record.getMessage()) for record in logs.records] == [
            ("INFO", "GraphQL request rejected: 16 aliases found. Allowed: 15"),
        ]

    def test_exception_in_extension_hook_is_masked_and_logged(self):
        with (
            mock.patch("main.graphql.limits.parse", side_effect=RuntimeError("boom at /srv/app/secret.py")),
            self.assertLogs("strawberry.execution", level="DEBUG") as logs,
        ):
            response = self._post("query { public { id } }")
        errors = response.json()["errors"]
        assert [error["message"] for error in errors] == [UNEXPECTED_ERROR_MESSAGE]
        assert errors[0]["extensions"] == {"code": "internal_error"}
        error_records = [record for record in logs.records if record.levelname == "ERROR"]
        assert len(error_records) == 1
        assert error_records[0].exc_info is not None
        assert isinstance(error_records[0].exc_info[1], RuntimeError)
        assert "boom" not in response.content.decode()

    def test_exception_in_extension_hook_audited_for_tokens(self):
        token = ApiTokenFactory.create()
        with (
            mock.patch("main.graphql.limits.parse", side_effect=RuntimeError("boom")),
            self.assertLogs("apps.api_token.auth", level="INFO") as logs,
        ):
            self.client.post(
                "/graphql/",
                data={"query": "query { public { id } }"},
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {token.secret}",
            )
        context = logs.records[0].context  # type: ignore[reportAttributeAccessIssue]
        assert context["result"] == "pre_execution_error"
        assert context["error"] == "internal_error"


class TestExtensionsPerOperation(TestCase):
    def test_extensions_registered_as_classes(self):
        """
        strawberry reuses extension instances for every operation and overwrites their `execution_context`, so only
        classes (instantiated per operation) are safe.
        """
        assert all(isinstance(extension, type) for extension in schema.extensions), schema.extensions

    def test_masking_isolated_between_concurrent_operations(self):
        @strawberry.type
        class Query:
            @strawberry.field
            async def slow(self) -> str:
                await asyncio.sleep(0.05)
                raise RuntimeError("raw slow error")

            @strawberry.field
            async def fast(self) -> str:
                return "ok"

        test_schema = strawberry.Schema(query=Query, extensions=schema.extensions)

        async def run():
            return await asyncio.gather(test_schema.execute("{ slow }"), test_schema.execute("{ fast }"))

        slow, fast = asyncio.run(run())
        assert fast.errors is None
        assert slow.errors is not None
        assert [error.message for error in slow.errors] == [UNEXPECTED_ERROR_MESSAGE]


class TestFieldErrorLogging(TestCase):
    def test_field_error_log_has_no_query_source(self):
        """
        The query source (with literals of other arguments on the same line) must not reach the logs.
        """
        sentinel = "s3cr3tSENTINELvalue"
        self.force_login(UserFactory.create())
        with (
            mock.patch.object(TaskType, "get_queryset", side_effect=RuntimeError("boom")),
            self.assertLogs("strawberry.execution", level="DEBUG") as logs,
        ):
            response = self.client.post(
                "/graphql/",
                data={"query": 'query Leak { private { task(pk: "%s") { id } } }' % sentinel},
                content_type="application/json",
            )
        assert response.json()["errors"][0]["message"] == UNEXPECTED_ERROR_MESSAGE
        assert len(logs.records) == 1
        record = logs.records[0]
        assert record.levelname == "ERROR"
        assert record.exc_info is not None
        assert isinstance(record.exc_info[1], RuntimeError)
        formatted = logging.Formatter().format(record)
        assert "boom" in formatted
        assert sentinel not in formatted
        assert sentinel not in str(getattr(record, "context", ""))
        assert record.context == {  # type: ignore[reportAttributeAccessIssue]
            "path": ["private", "task"],
            "operation_name": "Leak",
            "exception": "RuntimeError",
        }


class TestUnknownOperation(TestCase):
    def _post(self, data: dict, **kwargs):
        return self.client.post("/graphql/", data=data, content_type="application/json", **kwargs)

    def test_unknown_or_missing_operation_name_is_a_request_error(self):
        for data, message in [
            ({"query": "query A { public { id } }", "operationName": "B"}, "Unknown operation named 'B'."),
            ({"query": "fragment F on Query { __typename }"}, "Must provide an operation."),
        ]:
            with self.assertLogs("strawberry.execution", level="DEBUG") as logs:
                response = self._post(data)
            assert response.status_code == 200
            errors = response.json()["errors"]
            assert errors == [{"message": message, "extensions": {"code": "invalid_operation"}}], errors
            assert [(record.levelname, record.getMessage()) for record in logs.records] == [
                ("INFO", "GraphQL request rejected: invalid_operation"),
            ]

    def test_unknown_operation_audited_as_pre_execution_error(self):
        token = ApiTokenFactory.create()
        with self.assertLogs("apps.api_token.auth", level="INFO") as logs:
            self._post(
                {"query": "query A { public { id } }", "operationName": "B"},
                HTTP_AUTHORIZATION=f"Bearer {token.secret}",
            )
        context = logs.records[0].context  # type: ignore[reportAttributeAccessIssue]
        assert context["result"] == "pre_execution_error"
        assert context["error"] == "invalid_operation"


class TestErrorResponseHeaders(TestCase):
    """
    Responses Django builds for unhandled exceptions get the same cache headers as normal ones.
    """

    def _post(self, **headers):
        self.client.raise_request_exception = False
        with mock.patch.object(AsyncGraphQLView, "dispatch", side_effect=RuntimeError("boom")):
            return self.client.post(
                "/graphql/",
                data={"query": "query { public { id } }"},
                content_type="application/json",
                **headers,
            )

    def test_session_500_varies_on_authorization(self):
        self.force_login(UserFactory.create())
        response = self._post()
        assert response.status_code == 500
        assert "Authorization" in response["Vary"]
        assert "Cache-Control" not in response

    def test_bearer_500_is_private(self):
        token = ApiTokenFactory.create()
        response = self._post(HTTP_AUTHORIZATION=f"Bearer {token.secret}")
        assert response.status_code == 500
        assert "Authorization" in response["Vary"]
        assert response["Cache-Control"] == "private, no-store"
