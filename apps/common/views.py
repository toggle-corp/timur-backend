from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from main import config


@csrf_exempt
def dev_sign_in(request):
    """
    For server-side development only, Used to simulate frontend sign_in
    """
    assert config.GOOGLE_SSO_ENABLED
    assert config.SOCIALACCOUNT_PROVIDERS
    return render(
        request,
        "common/sign_in.html",
        context=dict(
            GOOGLE_OAUTH_CLIENT_ID=config.SOCIALACCOUNT_PROVIDERS["google"]["APP"]["client_id"],
        ),
    )
