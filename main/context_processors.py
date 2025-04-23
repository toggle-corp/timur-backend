from main import config


def app_contexts(request):
    return {
        "request": request,
        "APP_DOMAIN": config.APP_DOMAIN.geturl(),
        "APP_FRONTEND_HOST": config.APP_FRONTEND_HOST.geturl(),
        "APP_ENVIRONMENT": config.APP_ENVIRONMENT,
        "IS_DEBUG": config.DEBUG,
    }
