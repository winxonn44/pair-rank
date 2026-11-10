"""URL routes: the API, then the Angular page for every other path."""

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest
from django.urls import include, path, re_path
from django.views.decorators.http import require_safe


@require_safe
def angular_app(request: HttpRequest) -> FileResponse:
    """Deep links load the page and Angular takes over. WhiteNoise serves real files first."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise Http404("The frontend isn't built. Run `npm run build` in frontend/.")
    return FileResponse(index.open("rb"), content_type="text/html")


urlpatterns = [
    path("api/", include("ranking.urls")),
    # Paths under api/ and static/, and anything with a file extension, stay real 404s.
    re_path(r"^(?!(?:api|static)(?:/|$))[^.]*$", angular_app),
]
