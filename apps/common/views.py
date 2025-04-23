from django.conf import settings
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def dev_sign_in(request):
    """
    For server-side development only, Used to simulate frontend sign_in
    """
    assert settings.GOOGLE_SSO_ENABLED
    return render(
        request,
        "common/sign_in.html",
        context=dict(
            GOOGLE_OAUTH_CLIENT_ID=settings.SOCIALACCOUNT_PROVIDERS["google"]["APP"]["client_id"],
        ),
    )
