from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # Django Admin lives here; /admin/ is the React admin panel.
    path("django-admin/", admin.site.urls),
    path("api/", include("apps.platform_config.urls")),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.masterdata.urls")),
    path("api/", include("apps.shipments.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    ]
