import datetime
from unittest import mock

import pytest
from django.utils import timezone
from strawberry.django.views import AsyncGraphQLView

from apps.api_token.factories import ApiTokenFactory
from apps.api_token.models import ApiToken
from apps.api_token.scopes import ApiTokenScope
from apps.user.factories import UserFactory
from main.tests import TestCase


class TestBearerAuth(TestCase):
    ME = """
        query Me {
          public {
            me {
              id
            }
          }
        }
    """

    def _post(self, secret: str | None, query: str = ME, operation_name: str | None = None):
        headers = {}
        if secret is not None:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {secret}"
        return self.client.post(
            "/graphql/",
            data={"query": query, "operationName": operation_name},
            content_type="application/json",
            REMOTE_ADDR="203.0.113.7",
            **headers,
        )

    def _assert_401(self, response, code: str):
        assert response.status_code == 401, response.content
        assert response.json()["errors"][0]["extensions"]["code"] == code
        assert response["WWW-Authenticate"].startswith("Bearer")

    def test_valid_token_authenticates_as_token_user(self):
        token = ApiTokenFactory.create()
        response = self._post(token.secret)
        assert response.status_code == 200
        assert response.json() == {"data": {"public": {"me": {"id": self.gID(token.user_id)}}}}

    def test_bearer_wins_over_session(self):
        token = ApiTokenFactory.create()
        self.force_login(UserFactory.create())
        response = self._post(token.secret)
        assert response.json()["data"]["public"]["me"]["id"] == self.gID(token.user_id)

    def test_invalid_token(self):
        ApiTokenFactory.create()
        self._assert_401(self._post("tc_timur_" + "x" * 40), "invalid_token")
        self._assert_401(self._post("not-a-token"), "invalid_token")
        self._assert_401(self._post(""), "invalid_token")

    def test_invalid_token_never_falls_back_to_session(self):
        self.force_login(UserFactory.create())
        self._assert_401(self._post("tc_timur_" + "x" * 40), "invalid_token")

    def test_expired_token(self):
        token = ApiTokenFactory.create(expires_at=timezone.now() - datetime.timedelta(seconds=1))
        self._assert_401(self._post(token.secret), "token_expired")

    def test_revoked_token(self):
        token = ApiTokenFactory.create(revoked_at=timezone.now())
        self._assert_401(self._post(token.secret), "token_revoked")

    def test_inactive_user(self):
        user = UserFactory.create()
        token = ApiTokenFactory.create(user=user)
        user.is_active = False
        user.save(update_fields=("is_active",))
        self._assert_401(self._post(token.secret), "user_inactive")
        token.refresh_from_db()
        assert token.revoked_at is None

        # Works again once the user is reactivated
        user.is_active = True
        user.save(update_fields=("is_active",))
        assert self._post(token.secret).status_code == 200

    def test_session_without_bearer_is_unchanged(self):
        user = UserFactory.create()
        self.force_login(user)
        response = self._post(None)
        assert response.json()["data"]["public"]["me"]["id"] == self.gID(user.pk)

    def test_last_used_at_is_throttled(self):
        token = ApiTokenFactory.create()
        assert token.last_used_at is None

        self._post(token.secret)
        token.refresh_from_db()
        first_used_at = token.last_used_at
        assert first_used_at is not None

        # Within 60s: unchanged
        self._post(token.secret)
        token.refresh_from_db()
        assert token.last_used_at == first_used_at

        # After 60s: updated
        ApiToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now() - datetime.timedelta(seconds=61))
        self._post(token.secret)
        token.refresh_from_db()
        assert token.last_used_at is not None
        assert token.last_used_at > first_used_at

    def test_audit_log_line(self):
        token = ApiTokenFactory.create()
        with self.assertLogs("apps.api_token.auth", level="INFO") as logs:
            self._post(token.secret, operation_name="Me")
        assert len(logs.records) == 1
        context = logs.records[0].context  # type: ignore[reportAttributeAccessIssue]
        assert context == {
            "token_id": token.pk,
            "user_id": token.user_id,
            "operation_name": "Me",
            "ip": "203.0.113.7",
            "status": 200,
            "result": "executed",
        }
        assert token.secret not in logs.output[0]

    def test_audit_log_operation_name_from_document(self):
        token = ApiTokenFactory.create()
        with self.assertLogs("apps.api_token.auth", level="INFO") as logs:
            self._post(token.secret)  # No operationName in the body, the query is named "Me"
        assert logs.records[0].context["operation_name"] == "Me"  # type: ignore[reportAttributeAccessIssue]

    def test_audit_log_ip_uses_rightmost_forwarded_for(self):
        token = ApiTokenFactory.create()
        with self.assertLogs("apps.api_token.auth", level="INFO") as logs:
            self.client.post(
                "/graphql/",
                data={"query": self.ME},
                content_type="application/json",
                REMOTE_ADDR="10.42.0.1",
                HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.9",
                HTTP_AUTHORIZATION=f"Bearer {token.secret}",
            )
        assert logs.records[0].context["ip"] == "203.0.113.9"  # type: ignore[reportAttributeAccessIssue]

    def test_bearer_scheme_parsing(self):
        token = ApiTokenFactory.create()
        self.force_login(UserFactory.create())
        for header in [f"bearer {token.secret}", f"BEARER\t{token.secret}", f"Bearer   {token.secret}  "]:
            response = self.client.post(
                "/graphql/",
                data={"query": self.ME},
                content_type="application/json",
                HTTP_AUTHORIZATION=header,
            )
            assert response.status_code == 200, header
            assert response.json()["data"]["public"]["me"]["id"] == self.gID(token.user_id), header
        for header in [
            "Bearer",
            "Bearer ",
            "bearer\t",
            f"Bearer {token.secret} extra",
            "",
            f"Basic Zm9vOmJhcg==,Bearer {token.secret}",
            f"Basic Zm9vOmJhcg==, Bearer {token.secret}",
            f"Bearer {token.secret},Bearer {token.secret}",
            f"Bearer {token.secret}, Bearer {token.secret}",
            f"Bearer {token.secret},",
            "Basic Zm9vOmJhcg==",
            "Token abc",
            token.secret,
        ]:
            response = self.client.post(
                "/graphql/",
                data={"query": self.ME},
                content_type="application/json",
                HTTP_AUTHORIZATION=header,
            )
            self._assert_401(response, "invalid_token")


class TestNonBearerAuthorization(TestCase):
    """
    Any Authorization header that is not exactly one `Bearer <secret>` is rejected, never falling back to the session.
    """

    def test_other_schemes_with_session_cookie_rejected(self):
        self.force_login(UserFactory.create())
        for header in ["Basic Zm9vOmJhcg==", "Token abc", "Digest x", "raw-value"]:
            response = self.client.post(
                "/graphql/",
                data={"query": TestBearerAuth.ME},
                content_type="application/json",
                HTTP_AUTHORIZATION=header,
            )
            assert response.status_code == 401, header
            assert response.json()["errors"][0]["extensions"]["code"] == "invalid_token"
            assert response["WWW-Authenticate"].startswith("Bearer")


class TestBearerResponseHeaders(TestCase):
    def _post(self, **headers):
        return self.client.post(
            "/graphql/",
            data={"query": TestBearerAuth.ME},
            content_type="application/json",
            **headers,
        )

    def _assert_private(self, response):
        assert "Authorization" in response["Vary"]
        assert response["Cache-Control"] == "private, no-store"

    def test_success_and_401_are_private(self):
        token = ApiTokenFactory.create()
        response = self._post(HTTP_AUTHORIZATION=f"Bearer {token.secret}")
        assert response.status_code == 200
        self._assert_private(response)

        response = self._post(HTTP_AUTHORIZATION="Bearer tc_timur_" + "x" * 40)
        assert response.status_code == 401
        self._assert_private(response)

    def test_get_request_is_private(self):
        token = ApiTokenFactory.create()
        response = self.client.get(
            "/graphql/",
            {"query": TestBearerAuth.ME},
            HTTP_AUTHORIZATION=f"Bearer {token.secret}",
        )
        assert response.status_code == 200
        self._assert_private(response)

    def test_session_and_anonymous_responses_vary_on_authorization(self):
        """
        Caches must not reuse a response without a token for a request with one. Only token responses are private.
        """
        response = self._post()
        assert response.status_code == 200
        assert "Authorization" in response["Vary"]
        assert "Cache-Control" not in response

        self.force_login(UserFactory.create())
        response = self._post()
        assert response.status_code == 200
        assert "Authorization" in response["Vary"]
        assert "Cache-Control" not in response


class TestAuditLog(TestCase):
    """
    One audit log line for every request with an Authorization header, including 401s and rejected operations.
    """

    LOGGER = "apps.api_token.auth"

    def _post(self, authorization: str, data: dict | str, content_type: str = "application/json"):
        return self.client.post(
            "/graphql/",
            data=data,
            content_type=content_type,
            REMOTE_ADDR="203.0.113.7",
            HTTP_AUTHORIZATION=authorization,
        )

    def _single_context(self, logs) -> dict:
        assert len(logs.records) == 1, logs.output
        return logs.records[0].context

    def test_invalid_token_logged_with_prefix_only(self):
        secret = "tc_timur_" + "A1b2C3d4" + "x" * 32
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            response = self._post(f"Bearer {secret}", {"query": TestBearerAuth.ME})
        assert response.status_code == 401
        assert self._single_context(logs) == {
            "token_id": None,
            "user_id": None,
            "token_prefix": "A1b2C3d4",
            "ip": "203.0.113.7",
            "status": 401,
            "result": "unauthorized",
            "code": "invalid_token",
        }
        assert secret not in logs.output[0]
        assert "x" * 32 not in logs.output[0]

    def test_malformed_header_logged_without_prefix(self):
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            self._post("Basic Zm9vOmJhcg==", {"query": TestBearerAuth.ME})
        context = self._single_context(logs)
        assert context["token_prefix"] is None
        assert context["code"] == "invalid_token"
        assert "Zm9vOmJhcg" not in logs.output[0]

    def test_revoked_token_logged_with_token_id(self):
        token = ApiTokenFactory.create(revoked_at=timezone.now())
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            self._post(f"Bearer {token.secret}", {"query": TestBearerAuth.ME})
        context = self._single_context(logs)
        assert context["token_id"] == token.pk
        assert context["user_id"] == token.user_id
        assert context["token_prefix"] == token.prefix
        assert context["code"] == "token_revoked"
        assert token.secret not in logs.output[0]

    def test_pre_execution_errors_logged_by_category(self):
        token = ApiTokenFactory.create()
        for data, error, limit in [
            ({"query": "query Broken { public { me { id }"}, "syntax_error", None),
            ({"query": "query Unknown { public { notAField } }"}, "validation_error", None),
            (
                {"query": "query Aliased { " + " ".join(f"a{i}: __typename" for i in range(16)) + " }"},
                "limit_exceeded",
                "aliases",
            ),
            ({"query": "query Deep { " + "a { " * 13 + "b" + " }" * 13 + " }"}, "limit_exceeded", "depth"),
            ({"query": "query Big { " + " ".join(["__typename"] * 500) + " }"}, "limit_exceeded", "tokens"),
            (
                {"query": "query Var($date: Date!) { private { myTimeEntries(date: $date) { id } } }"},
                "variable_error",
                None,
            ),
        ]:
            with self.assertLogs(self.LOGGER, level="INFO") as logs:
                response = self._post(f"Bearer {token.secret}", data)
            assert response.status_code == 200, data
            context = self._single_context(logs)
            assert context["result"] == "pre_execution_error", (data, context)
            assert context["status"] == 200
            assert context["token_id"] == token.pk
            assert context["error"] == error, (data, context)
            assert context.get("limit") == limit, (data, context)

    def test_submitted_values_never_logged(self):
        """
        Error messages can quote the query or variable values; no log line may contain them.
        """
        sentinel = "s3cr3tSENTINELvalue"
        token = ApiTokenFactory.create(scopes=[ApiTokenScope.TIME_ENTRY_READ.value])
        for data, error in [
            ({"query": "query { private { myTimeEntries(date: " + f'"{sentinel}"' + ") { id } } }"}, "validation_error"),
            (
                {
                    "query": "query ($date: Date!) { private { myTimeEntries(date: $date) { id } } }",
                    "variables": {"date": sentinel},
                },
                "variable_error",
            ),
            ({"query": f"query {{ {sentinel}(x: 1 }}"}, "syntax_error"),
        ]:
            # `apps.*` loggers don't propagate to the root logger, so both are captured
            with self.assertLogs("apps", level="DEBUG") as app_logs, self.assertLogs(level="DEBUG") as root_logs:
                response = self._post(f"Bearer {token.secret}", data)
            if error != "syntax_error":
                assert sentinel in response.content.decode(), "the client still gets the full message"
            audit = [record for record in app_logs.records if record.name == self.LOGGER]
            assert len(audit) == 1
            assert audit[0].context["result"] == "pre_execution_error"  # type: ignore[reportAttributeAccessIssue]
            assert audit[0].context["error"] == error  # type: ignore[reportAttributeAccessIssue]
            for record in [*app_logs.records, *root_logs.records]:
                assert sentinel not in record.getMessage(), record
                assert sentinel not in str(getattr(record, "context", "")), record

    def test_missing_query_and_disallowed_operation_logged_as_http_error(self):
        token = ApiTokenFactory.create()
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            response = self._post(f"Bearer {token.secret}", {"query": ""})
        assert response.status_code == 400
        assert self._single_context(logs)["result"] == "http_error"

        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            response = self.client.get(
                "/graphql/",
                {"query": "mutation { public { logout { ok } } }"},
                HTTP_AUTHORIZATION=f"Bearer {token.secret}",
            )
        assert response.status_code == 400
        context = self._single_context(logs)
        assert context["result"] == "http_error"
        assert context["status"] == 400

    def test_exception_in_view_logged_as_http_error(self):
        token = ApiTokenFactory.create()
        with (
            mock.patch.object(AsyncGraphQLView, "dispatch", side_effect=RuntimeError("boom")),
            self.assertLogs(self.LOGGER, level="INFO") as logs,
            pytest.raises(RuntimeError),
        ):
            self._post(f"Bearer {token.secret}", {"query": TestBearerAuth.ME})
        context = self._single_context(logs)
        assert context["result"] == "http_error"
        assert context["status"] == 500
        assert context["token_id"] == token.pk

    def test_http_level_rejection_logged(self):
        token = ApiTokenFactory.create()
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            response = self._post(f"Bearer {token.secret}", "{not json", content_type="application/json")
        assert response.status_code == 400
        context = self._single_context(logs)
        assert context["result"] == "http_error"
        assert context["status"] == 400
        assert context["operation_name"] is None
        assert context["token_id"] == token.pk
