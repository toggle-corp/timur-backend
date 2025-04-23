from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt

from apps.common.views import dev_sign_in
from main import config
from main.graphql.schema import CustomAsyncGraphQLView
from main.graphql.schema import schema as graphql_schema

admin.site.site_header = "Timur"
admin.site.index_title = "Django Admin Panel"
admin.site.site_title = "Timur web app"
admin.site.site_url = config.APP_FRONTEND_HOST.geturl()


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
    path("accounts/", include("allauth.urls")),
    path("_allauth/", include("allauth.headless.urls")),
]

if config.GOOGLE_SSO_ENABLED:
    urlpatterns.extend(
        [
            path("dev/sign_in/", dev_sign_in, name="dev-sign-in"),
            path("", dev_sign_in, name="dev-sign-in"),
        ],
    )

if config.DEBUG:
    urlpatterns.extend(
        [
            path("graphiql/", CustomAsyncGraphQLView.as_view(schema=graphql_schema), name="graphiql"),
        ],
    )

    # Static and media file URLs
    urlpatterns += static(config.MEDIA_URL, document_root=config.MEDIA_ROOT)
    urlpatterns += static(config.STATIC_URL, document_root=config.STATIC_ROOT)
