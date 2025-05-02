import datetime
import typing

from django.contrib.sessions.models import Session
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from main import config

if typing.TYPE_CHECKING:
    from django.http import HttpRequest


def get_login_expire(request: "HttpRequest") -> datetime.datetime | None:
    session_model_class = getattr(request.session, "model", None)
    if session_model_class == Session:
        session_key = request.session.session_key
        if session := Session.objects.filter(session_key=session_key).first():
            return session.expire_date
    return None


@csrf_exempt
def sso_sign_in(request):
    """
    For server-side development only, Used to simulate frontend sign_in
    """
    assert config.GOOGLE_SSO_ENABLED
    assert config.SOCIALACCOUNT_PROVIDERS

    login_expire_in_days = None
    if login_expire := get_login_expire(request):
        login_expire_in_days = (login_expire - timezone.now()).days

    return render(
        request,
        "common/sign_in.html",
        context=dict(
            GOOGLE_OAUTH_CLIENT_ID=config.SOCIALACCOUNT_PROVIDERS["google"]["APP"]["client_id"],
            login_expire_threshold=4,
            login_expire_in_days=login_expire_in_days,
        ),
    )
