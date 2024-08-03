from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from apps.common.views import dev_sign_in, google_oauth
from main.graphql.schema import CustomAsyncGraphQLView
from main.graphql.schema import schema as graphql_schema

urlpatterns = [
    path("admin/", admin.site.urls, name="admin"),
    # path('health-check/', include('health_check.urls')),
    path(
        "graphql/",
        CustomAsyncGraphQLView.as_view(
            schema=graphql_schema,
            graphiql=False,
        ),
    ),
    path("o/google", google_oauth),
]


if settings.DEBUG:
    urlpatterns.extend(
        [
            path("graphiql/", CustomAsyncGraphQLView.as_view(schema=graphql_schema)),
            path("dev/sign_in/", dev_sign_in, name="dev-sign-in"),
        ]
    )

    # Static and media file URLs
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
