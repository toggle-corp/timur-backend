from django.conf import settings
from django.contrib.auth import login
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from google.auth.transport import requests
from google.oauth2 import id_token

from apps.user.models import User


@csrf_exempt
def dev_sign_in(request):
    """
    For server-side development only, Used to simulate frontend sign_in
    """
    return render(
        request,
        "common/sign_in.html",
        context=dict(
            GOOGLE_OAUTH_CLIENT_ID=settings.GOOGLE_OAUTH_CLIENT_ID,
            GOOGLE_OAUTH_REDIRECT_URL=settings.GOOGLE_OAUTH_REDIRECT_URL,
        ),
    )


@csrf_exempt
def google_oauth(request):
    """
    Google calls this URL after the user has signed in with their Google account.
    """
    error_postfix = (
        f"</br> Go back to the application here: <a href='{settings.APP_FRONTEND_HOST}'>{settings.APP_FRONTEND_HOST}</a>"
    )
    if request.method.upper() == "GET":
        return HttpResponse(
            f"Not sure what you are trying to do here {error_postfix}",
            status=405,
        )

    token = request.POST.get("credential")

    if token is None:
        return HttpResponse(
            f"No credential provided {error_postfix}",
            status=400,
        )

    try:
        user_data = id_token.verify_oauth2_token(token, requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID)
        if user_data["email_verified"] is not True:
            return HttpResponse(
                "Email is not verified {error_postfix}",
                status=400,
            )
    except ValueError:
        return HttpResponse(
            f"Failed to process {error_postfix}",
            status=403,
        )

    email = user_data["email"].lower()
    if user := User.objects.filter(email=email).first():
        if not user.is_active:
            return HttpResponse("User is inactive. Please contact admin", status=403)
        user.first_name = user_data["given_name"]
        user.last_name = user_data["family_name"]
        user.display_picture = user_data["picture"]
        user.save(update_fields=("first_name", "last_name", "display_name", "display_picture"))
        login(request, user)
    else:
        new_user = User.objects.create(
            email=email,
            first_name=user_data["given_name"],
            last_name=user_data["family_name"],
            display_picture=user_data["picture"],
        )
        login(request, new_user)

    return redirect(settings.APP_FRONTEND_HOST)
