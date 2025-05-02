import typing

from apps.user.factories import UserFactory
from main.tests import TestCase


class TestUserQuery(TestCase):
    class Query:
        ME = """
            query meQuery {
              public {
                me {
                  id
                  email
                  firstName
                  lastName
                  displayName
                  loginExpire
                }
              }
            }
        """

    @classmethod
    @typing.override
    def setUpClass(cls):
        super().setUpClass()
        cls.user = UserFactory.create()
        # Some other users as well
        cls.users = (
            UserFactory.create(first_name="Test", last_name="Hero", email="sample@test.com"),
            UserFactory.create(first_name="Example", last_name="Villain", email="sample@vil.com"),
            UserFactory.create(first_name="Test", last_name="Hero"),
        )

    def test_me(self):
        # Without authentication -----
        content = self.query_check(self.Query.ME)
        assert content["data"]["public"]["me"] is None

        user = self.user
        # With authentication -----
        self.force_login(user)
        content = self.query_check(self.Query.ME)
        assert content["data"]["public"]["me"].pop("loginExpire") is not None
        assert content["data"]["public"]["me"] == dict(
            id=self.gID(user.id),
            email=user.email,
            firstName=user.first_name,
            lastName=user.last_name,
            displayName=f"{user.first_name} {user.last_name}",
        )
