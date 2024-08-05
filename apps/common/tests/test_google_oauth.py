from unittest.mock import patch

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.common.views import google_oauth
from apps.user.factories import UserFactory
from apps.user.models import User
from main.tests import TestCase


class TestGoogleOAuth(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.mock_oauth2_valid_response = {
            "hd": "togglecorp.com",
            "email": "john.cena@togglecorp.com",
            "email_verified": True,
            "picture": "https://lh3.googleusercontent.com/a/john.cena.png",
            "given_name": "John",
            "family_name": "Cena",
        }
        UserFactory.create_batch(3)  # Noise data

    @patch("apps.common.views.id_token.verify_oauth2_token")
    def test_sign_up(self, verify_oauth2_token_mock):
        request = self.factory.post(
            reverse("google_oauth"),
            data={"credential": "XYZ"},
            # NOTE: Using content_type='application/json' ignores the data param
        )
        middleware = SessionMiddleware(self.no_op)  # type: ignore[reportArgumentType]
        middleware.process_request(request)
        request.session.save()

        def _query_count_check(count):
            assert User.objects.filter(email=self.mock_oauth2_valid_response["email"]).count() == count

        _query_count_check(0)
        assert list(request.session.items()) == []

        # Failure response 01
        verify_oauth2_token_mock.return_value = {
            **self.mock_oauth2_valid_response,
            "email_verified": False,
        }
        response = google_oauth(request)
        assert response.status_code == 400
        assert list(request.session.items()) == []
        _query_count_check(0)

        # Failure response 02
        verify_oauth2_token_mock.side_effect = lambda *_: (_ for _ in ()).throw(ValueError("Random error"))
        response = google_oauth(request)
        assert response.status_code == 403
        assert list(request.session.items()) == []
        _query_count_check(0)

        # Success response
        verify_oauth2_token_mock.reset_mock(side_effect=True)
        verify_oauth2_token_mock.return_value = {**self.mock_oauth2_valid_response}
        response = google_oauth(request)
        assert response.status_code == 302
        assert list(request.session.items()) != []
        assert len(list(request.session.items())) == 3
        assert list(request.session.items())[0] == (
            "_auth_user_id",
            str(User.objects.get(email=self.mock_oauth2_valid_response["email"]).pk),
        )
        _query_count_check(1)

    @patch("apps.common.views.id_token.verify_oauth2_token")
    def test_sign_in(self, verify_oauth2_token_mock):
        user = UserFactory.create(email=self.mock_oauth2_valid_response["email"])
        UserFactory.create_batch(3)  # Noise data

        request = self.factory.post(
            reverse("google_oauth"),
            data={"credential": "XYZ"},
            # NOTE: Using content_type='application/json' ignores the data param
        )
        middleware = SessionMiddleware(self.no_op)  # type: ignore[reportArgumentType]
        middleware.process_request(request)
        request.session.save()

        # Failure response 01
        verify_oauth2_token_mock.return_value = {
            **self.mock_oauth2_valid_response,
            "email_verified": False,
        }
        response = google_oauth(request)
        assert list(request.session.items()) == []
        assert response.status_code == 400

        # Failure response 02
        verify_oauth2_token_mock.side_effect = lambda *_: (_ for _ in ()).throw(ValueError("Random error"))
        response = google_oauth(request)
        assert list(request.session.items()) == []
        assert response.status_code == 403

        # Success response
        verify_oauth2_token_mock.reset_mock(side_effect=True)
        verify_oauth2_token_mock.return_value = {**self.mock_oauth2_valid_response}
        response = google_oauth(request)
        assert list(request.session.items()) != []
        assert len(list(request.session.items())) == 3
        assert list(request.session.items())[0] == ("_auth_user_id", str(user.pk))
        assert response.status_code == 302
