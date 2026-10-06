from apps.user.factories import UserFactory
from apps.user.models import User
from main.tests import TestCase


class TestUserModel(TestCase):
    def test_get_display_name(self):
        assert User.get_display_name(1, "Test Hero") == "Test Hero"
        assert User.get_display_name(1, "") == "User#1"
        assert User.get_display_name(1, None) == "User#1"

    def test_display_name_on_save(self):
        user = UserFactory.create(first_name="Test", last_name="Hero")
        assert user.display_name == "Test Hero"

        user.first_name = ""
        user.last_name = ""
        user.save()
        assert user.display_name == f"User#{user.pk}"
