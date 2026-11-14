from asgiref.sync import iscoroutinefunction
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.utils.decorators import sync_and_async_middleware
from django.utils.deprecation import MiddlewareMixin

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


GRAPHQL_URL_NAMES = frozenset({"graphql", "graphiql"})
BEARER_CACHE_CONTROL = "private, no-store"


class GraphQLCacheHeadersMiddleware(MiddlewareMixin):
    """
    Cache headers for GraphQL responses, including 401s and the error pages Django builds for unhandled exceptions.
    Every response varies on Authorization, so a cache never reuses a response without a token for a request with
    one. Responses to requests with an Authorization header are also private and never stored.
    """

    def process_response(self, request, response):
        match = getattr(request, "resolver_match", None)
        if match is not None and match.url_name in GRAPHQL_URL_NAMES:
            patch_vary_headers(response, ("Authorization",))
            if "Authorization" in request.headers:
                response["Cache-Control"] = BEARER_CACHE_CONTROL
        return response
