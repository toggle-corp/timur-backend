from asgiref.sync import iscoroutinefunction
from django.urls import reverse
from django.utils.decorators import sync_and_async_middleware

from main.sentry import SentryTransactionMiddlewareHelper


@sync_and_async_middleware
def sentry_middleware(get_response):
    from main import config

    # One-time configuration and initialization goes here.
    graphql_urls = set([reverse("graphql")])
    if config.DEBUG:
        graphql_urls.add(reverse("graphiql"))

    if iscoroutinefunction(get_response):

        async def amiddleware(request):
            if config.SENTRY_ENABLED:
                await SentryTransactionMiddlewareHelper.atrack_transaction(graphql_urls, request)
            return await get_response(request)

        return amiddleware

    def middleware(request):
        if config.SENTRY_ENABLED:
            SentryTransactionMiddlewareHelper.track_transaction(graphql_urls, request)
        return get_response(request)

    return middleware
