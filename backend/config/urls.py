"""URL routes."""

from django.urls import include, path

urlpatterns = [path("api/", include("ranking.urls"))]
