import datetime

from django.utils import timezone

from apps.api_token.factories import ApiTokenFactory
from apps.user.factories import UserFactory
from main.tests import TestCase


class TestMyApiTokens(TestCase):
    class Query:
        MY_API_TOKENS = """
            query MyApiTokens {
              private {
                myApiTokens {
                  id
                  name
                  prefix
                  status
                }
              }
            }
        """
        SCOPE_ENUM = """
            query Enums {
              enums {
                ApiTokenScopes {
                  key
                  label
                  description
                  resource
                  resourceLabel
                  resourceDescription
                }
              }
            }
        """

    def test_lists_active_and_recently_expired_or_revoked(self):
        user = UserFactory.create()
        now = timezone.now()
        active = ApiTokenFactory.create(user=user)
        expired = ApiTokenFactory.create(user=user, expires_at=now - datetime.timedelta(days=29))
        recently_revoked = ApiTokenFactory.create(user=user, revoked_at=now - datetime.timedelta(days=29))
        expired_long_ago_revoked_today = ApiTokenFactory.create(
            user=user,
            expires_at=now - datetime.timedelta(days=40),
            revoked_at=now,
        )
        # Hidden
        ApiTokenFactory.create(user=user, expires_at=now - datetime.timedelta(days=31))
        ApiTokenFactory.create(
            user=user,
            expires_at=now - datetime.timedelta(days=5),
            revoked_at=now - datetime.timedelta(days=31),
        )
        ApiTokenFactory.create(user=user, revoked_at=now - datetime.timedelta(days=31))
        ApiTokenFactory.create()  # other user

        self.force_login(user)
        tokens = self.query_check(self.Query.MY_API_TOKENS)["data"]["private"]["myApiTokens"]
        assert {(t["id"], t["status"]) for t in tokens} == {
            (self.gID(active.pk), "ACTIVE"),
            (self.gID(expired.pk), "EXPIRED"),
            (self.gID(recently_revoked.pk), "REVOKED"),
            (self.gID(expired_long_ago_revoked_today.pk), "REVOKED"),
        }

    def test_scope_enum_has_label_and_description(self):
        items = self.query_check(self.Query.SCOPE_ENUM)["data"]["enums"]["ApiTokenScopes"]
        keys = [item["key"] for item in items]
        assert keys == [
            "TIME_ENTRY_READ",
            "TIME_ENTRY_WRITE",
            "JOURNAL_READ",
            "JOURNAL_WRITE",
            "PROJECT_READ",
            "USER_READ",
            "EVENT_READ",
        ]
        assert all(item["label"] and item["description"] and item["resourceDescription"] for item in items)
        resources = {item["key"]: (item["resource"], item["resourceLabel"]) for item in items}
        assert resources == {
            "TIME_ENTRY_READ": ("time_entry", "Time entries"),
            "TIME_ENTRY_WRITE": ("time_entry", "Time entries"),
            "JOURNAL_READ": ("journal", "Journal (incl. leave & WFH)"),
            "JOURNAL_WRITE": ("journal", "Journal (incl. leave & WFH)"),
            "PROJECT_READ": ("project", "Projects"),
            "USER_READ": ("user", "Users"),
            "EVENT_READ": ("event", "Events"),
        }

    def test_other_enums_have_no_extra_fields(self):
        content = self.query_check(
            "query { enums { TimeEntryStatus { key label description } } }",
            assert_errors=True,
        )
        assert "Cannot query field 'description'" in content["errors"][0]["message"]
