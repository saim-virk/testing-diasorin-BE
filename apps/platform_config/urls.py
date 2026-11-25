from django.urls import path

from .api import HealthView, PublicSiteView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("public/site", PublicSiteView.as_view(), name="public-site"),
]
