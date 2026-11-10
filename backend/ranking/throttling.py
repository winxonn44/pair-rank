"""A per-IP request limit, so a bot can't fill the database."""

from django.conf import settings
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle


class IPRateThrottle(SimpleRateThrottle):
    """Applies to every request. DRF's AnonRateThrottle would skip logged-in guests."""

    scope = "ip"

    def get_rate(self) -> str | None:
        return settings.API_THROTTLE_RATE

    def get_cache_key(self, request: Request, view: object) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
