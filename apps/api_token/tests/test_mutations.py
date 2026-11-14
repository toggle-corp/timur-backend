import datetime
import re
import typing

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.api_token.factories import ApiTokenFactory
from apps.api_token.models import ApiToken
from apps.user.factories import UserFactory
from apps.user.models import User
from main.tests import TestCase


def utc_iso(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).isoformat()


def in_days(days: float) -> datetime.datetime:
    return timezone.now() + datetime.timedelta(days=days)


class TestCreateApiToken(TestCase):
    class Mutation:
        CREATE = """
            mutation CreateApiToken($data: ApiTokenCreateInput!) {
              private {
                createApiToken(data: $data) {
                  ok
                  errors
                  result {
                    secret
                    token {
                      id
                      name
                      prefix
                      scopes
                      status
                      expiresAt
                      lastUsedAt
                      revokedAt
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
        cls.user = UserFactory.create()

    def test_create_returns_secret_once(self):
        # End of day in the user's browser (UTC+05:45), sent as UTC
        expires_at = datetime.datetime.combine(
            (timezone.now() + datetime.timedelta(days=30)).date(),
            datetime.time(23, 59, 59),
            tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=45)),
        )
        self.force_login(self.user)
        content = self.query_check(
            self.Mutation.CREATE,
            variables={
                "data": {
                    "name": "My script",
                    "scopes": ["TIME_ENTRY_READ", "PROJECT_READ"],
                    "expiresAt": utc_iso(expires_at),
                },
            },
        )
        response = content["data"]["private"]["createApiToken"]
        assert response["ok"] is True, response
        result = response["result"]
        assert re.fullmatch(r"tc_timur_[A-Za-z0-9]{40}", result["secret"])
        token = result["token"]
        assert token["name"] == "My script"
        assert token["prefix"] == result["secret"][len("tc_timur_") :][:8]
        assert sorted(token["scopes"]) == ["PROJECT_READ", "TIME_ENTRY_READ"]
        assert token["status"] == "ACTIVE"
        assert token["lastUsedAt"] is None
        assert token["revokedAt"] is None
        # Stored as given, returned in UTC
        assert token["expiresAt"] == expires_at.astimezone(datetime.UTC).isoformat()
        assert token["expiresAt"].endswith("+00:00")

    def _create(self, **data):
        variables = {
            "data": {
                "name": "Token",
                "scopes": ["TIME_ENTRY_READ"],
                "expiresAt": utc_iso(in_days(30)),
                **data,
            },
        }
        return self.query_check(self.Mutation.CREATE, variables=variables)["data"]["private"]["createApiToken"]

    def _error_fields(self, response) -> set[str]:
        return {error["field"] for error in response["errors"]}

    def test_name_unique_among_active_tokens(self):
        user = UserFactory.create()
        self.force_login(user)
        assert self._create(name="ci")["ok"] is True
        response = self._create(name="CI ")
        assert response["ok"] is False
        assert self._error_fields(response) == {"name"}

        # Revoked and expired tokens free the name
        ApiTokenFactory.create(user=user, name="old", revoked_at=timezone.now())
        ApiTokenFactory.create(user=user, name="older", expires_at=timezone.now() - datetime.timedelta(days=1))
        assert self._create(name="old")["ok"] is True
        assert self._create(name="older")["ok"] is True

        # Other user's names don't matter
        self.force_login(UserFactory.create())
        assert self._create(name="ci")["ok"] is True

    def test_max_ten_active_tokens(self):
        user = UserFactory.create()
        ApiTokenFactory.create_batch(9, user=user)
        ApiTokenFactory.create(user=user, revoked_at=timezone.now())
        ApiTokenFactory.create(user=user, expires_at=timezone.now() - datetime.timedelta(days=1))
        self.force_login(user)
        assert self._create(name="tenth")["ok"] is True
        response = self._create(name="eleventh")
        assert response["ok"] is False
        assert self._error_fields(response) == {"nonFieldErrors"}

    def test_expiry_range(self):
        """
        More than 1 hour and at most 367 days from now.
        """
        self.force_login(self.user)
        hour = 1 / 24
        for days, ok in [
            (-1, False),
            (0, False),
            (hour - 0.001, False),
            (hour + 0.001, True),
            (90, True),
            (367 - 0.001, True),
            (367 + 0.001, False),
        ]:
            response = self._create(name=f"expiry {days}", expiresAt=utc_iso(in_days(days)))
            assert response["ok"] is ok, (days, response)
            if not ok:
                assert self._error_fields(response) == {"expiresAt"}
                assert "from now" in response["errors"][0]["messages"]

    def test_expiry_offset_is_converted_to_utc(self):
        self.force_login(self.user)
        expires_at = in_days(10).astimezone(datetime.timezone(datetime.timedelta(hours=-7)))
        response = self._create(name="offset", expiresAt=expires_at.isoformat())
        assert response["result"]["token"]["expiresAt"] == utc_iso(expires_at)

    def test_write_scope_adds_read_scope(self):
        self.force_login(self.user)
        response = self._create(name="writer", scopes=["TIME_ENTRY_WRITE", "JOURNAL_WRITE", "EVENT_READ"])
        assert response["ok"] is True
        assert sorted(response["result"]["token"]["scopes"]) == [
            "EVENT_READ",
            "JOURNAL_READ",
            "JOURNAL_WRITE",
            "TIME_ENTRY_READ",
            "TIME_ENTRY_WRITE",
        ]

    def test_name_length_and_blank(self):
        self.force_login(self.user)
        for name in ["x" * 101, "   ", ""]:
            response = self._create(name=name)
            assert response["ok"] is False, name
            assert self._error_fields(response) == {"name"}, name
        response = self._create(name=f"  {'y' * 100}  ")
        assert response["ok"] is True
        assert response["result"]["token"]["name"] == "y" * 100

    def test_scopes_required(self):
        self.force_login(self.user)
        response = self._create(name="no scopes", scopes=[])
        assert response["ok"] is False
        assert self._error_fields(response) == {"scopes"}

    def test_requires_login(self):
        self.logout()
        content = self.query_check(
            self.Mutation.CREATE,
            assert_errors=True,
            variables={
                "data": {"name": "x", "scopes": ["TIME_ENTRY_READ"], "expiresAt": utc_iso(in_days(30))},
            },
        )
        assert content["data"] is None

    def test_name_must_be_printable(self):
        self.force_login(self.user)
        response = self._create(name="line\nbreak")
        assert response["ok"] is False
        assert self._error_fields(response) == {"name"}

    def test_create_checks_limits_under_user_row_lock(self):
        """
        Concurrent creates for one user are serialized by locking the user row before the limit and name checks.
        """
        user = UserFactory.create()
        self.force_login(user)
        with CaptureQueriesContext(connection) as queries:
            assert self._create(name="locked")["ok"] is True
        sqls = [query["sql"] for query in queries.captured_queries]
        user_table = User._meta.db_table
        token_table = ApiToken._meta.db_table
        lock_index = next(i for i, sql in enumerate(sqls) if f'FROM "{user_table}"' in sql and "FOR UPDATE" in sql)
        check_indexes = [i for i, sql in enumerate(sqls) if f'FROM "{token_table}"' in sql]
        insert_index = next(i for i, sql in enumerate(sqls) if f'INSERT INTO "{token_table}"' in sql)
        assert check_indexes
        assert lock_index < min(check_indexes) < insert_index


class TestRevokeApiToken(TestCase):
    class Mutation:
        REVOKE = """
            mutation RevokeApiToken($id: ID!) {
              private {
                revokeApiToken(id: $id) {
                  ok
                  errors
                  result {
                    id
                    status
                    revokedAt
                  }
                }
              }
            }
        """

    def test_revoke_own_token(self):
        user = UserFactory.create()
        token = ApiTokenFactory.create(user=user)
        self.force_login(user)
        response = self.query_check(self.Mutation.REVOKE, variables={"id": self.gID(token.pk)})["data"]["private"][
            "revokeApiToken"
        ]
        assert response["ok"] is True
        assert response["result"]["status"] == "REVOKED"
        assert response["result"]["revokedAt"] is not None
        token.refresh_from_db()
        assert token.revoked_at is not None

    def test_expired_token_cannot_be_revoked(self):
        user = UserFactory.create()
        token = ApiTokenFactory.create(user=user, expires_at=timezone.now() - datetime.timedelta(days=1))
        self.force_login(user)
        response = self.query_check(self.Mutation.REVOKE, variables={"id": self.gID(token.pk)})["data"]["private"][
            "revokeApiToken"
        ]
        assert response["ok"] is False
        assert response["errors"][0]["messages"] == "Token has already expired"
        token.refresh_from_db()
        assert token.revoked_at is None

    def test_malformed_id_is_not_found(self):
        self.force_login(UserFactory.create())
        for token_id in ["abc", "\u00b2", "\u0661", "1.5", "-1", " 1", "", "9" * 20]:
            response = self.query_check(self.Mutation.REVOKE, variables={"id": token_id})["data"]["private"][
                "revokeApiToken"
            ]
            assert response["ok"] is False, token_id
            assert response["errors"][0]["messages"] == "Token not found", token_id

    def test_cannot_revoke_other_users_token(self):
        token = ApiTokenFactory.create()
        self.force_login(UserFactory.create())
        response = self.query_check(self.Mutation.REVOKE, variables={"id": self.gID(token.pk)})["data"]["private"][
            "revokeApiToken"
        ]
        assert response["ok"] is False
        token.refresh_from_db()
        assert token.revoked_at is None
