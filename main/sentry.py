import json

import sentry_sdk
from asgiref.sync import sync_to_async
from sentry_sdk import Scope, set_user
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.strawberry import StrawberryIntegration

IGNORED_ERRORS = []
IGNORED_LOGGERS = [
    "graphql.execution.utils",
    "strawberry.http.exceptions.HTTPException",
]

for _logger in IGNORED_LOGGERS:
    ignore_logger(_logger)


def init_sentry(app_type, tags: dict | None = None, **config):
    integrations = [
        DjangoIntegration(),
        CeleryIntegration(),
        RedisIntegration(),
        StrawberryIntegration(async_execution=True),
    ]
    sentry_sdk.init(
        **config,
        ignore_errors=IGNORED_ERRORS,
        integrations=integrations,
    )
    with sentry_sdk.configure_scope() as scope:
        scope.set_tag("app_type", app_type)
        for tag, value in (tags or {}).items():
            scope.set_tag(tag, value)


class SentryTransactionMiddlewareHelper:
    @classmethod
    @sync_to_async
    def atrack_transaction(cls, graphql_urls: set[str], request):
        return cls.track_transaction(graphql_urls, request)

    @staticmethod
    def track_transaction(graphql_urls: set[str], request):
        if request.path in graphql_urls:
            operation_type = "Query"
            operation_name = "Unknown"
            try:
                body = request.body.decode("utf-8")
                if body:
                    # XXX: This will be repeated by Strawberry as well.
                    data = json.loads(body)
                    operation_name = data.get("operationName", operation_name)
                    if data.get("query", "").startswith("mutation"):
                        operation_type = "Mutation"
            except Exception:
                ...

            scope = Scope.get_current_scope()
            scope.set_transaction_name(f"GraphQL/{operation_type}/{operation_name}")
            if (user := request.user) and user.pk:
                set_user(
                    {
                        "id": user.pk,
                        "email": user.email,
                        "is_superuser": user.is_superuser,
                    },
                )
