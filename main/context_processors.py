from django.conf import settings


def app_contexts(request):
    return {
        "request": request,
        "APP_ENVIRONMENT": settings.APP_ENVIRONMENT,
        "APP_FRONTEND_HOST": settings.APP_FRONTEND_HOST,
        "IS_DEBUG": settings.DEBUG,
    }
