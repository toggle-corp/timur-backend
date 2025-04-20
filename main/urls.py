from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt

from apps.common.views import dev_sign_in, google_oauth
from main.graphql.schema import CustomAsyncGraphQLView
from main.graphql.schema import schema as graphql_schema

admin.site.site_header = "Timur"
admin.site.index_title = "Django Admin Panel"
admin.site.site_title = "HTML title from adminsitration"


urlpatterns = [
    path("admin/", admin.site.urls, name="admin"),
    path("health-check/", include("health_check.urls")),
    # path('health-check/', include('health_check.urls')),
    path(
        "graphql/",
        # TODO: Remove this after updating the frontend to send csrf tokens
        csrf_exempt(
            CustomAsyncGraphQLView.as_view(
                schema=graphql_schema,
                graphql_ide=False,
            ),
        ),
        name="graphql",
    ),
    path("o/google", google_oauth, name="google_oauth"),
]

if settings.GOOGLE_OAUTH_ENABLED:
    urlpatterns.append(path("dev/sign_in/", dev_sign_in, name="dev-sign-in"))

if settings.DEBUG:
    urlpatterns.extend(
        [
            path("graphiql/", CustomAsyncGraphQLView.as_view(schema=graphql_schema), name="graphiql"),
        ],
    )

    # Static and media file URLs
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
