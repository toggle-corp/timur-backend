from django.conf import settings


def app_contexts(request):
    return {
        "request": request,
        "APP_DOMAIN": settings.APP_DOMAIN,
        "APP_FRONTEND_HOST": settings.APP_FRONTEND_HOST,
        "APP_ENVIRONMENT": settings.APP_ENVIRONMENT,
        "IS_DEBUG": settings.DEBUG,
    }
