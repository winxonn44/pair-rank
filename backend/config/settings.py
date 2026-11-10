"""Settings come from the environment, so no secret ever lives in the repo.

DEBUG=1 turns on development defaults that match docker-compose.yml. With DEBUG
off, SECRET_KEY and DATABASE_URL are required and startup fails without them.
"""

import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DEBUG", "0") == "1"

_DEV_SECRET_KEY = "dev-only-not-a-secret"
_DEV_DATABASE_URL = "postgres://pairrank:pairrank@127.0.0.1:5432/pairrank"


def _required(name: str, dev_default: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    if DEBUG:
        return dev_default
    raise ImproperlyConfigured(f"{name} must be set when DEBUG is off")


def parse_database_url(url: str) -> dict[str, Any]:
    """Turn postgres://user:password@host:port/name?sslmode=require into a Django entry."""
    parts = urlsplit(url)
    if parts.scheme not in ("postgres", "postgresql"):
        raise ImproperlyConfigured(f"DATABASE_URL must be Postgres, got {parts.scheme!r}")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parts.path.lstrip("/"),
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "",
        "PORT": str(parts.port or ""),
        "OPTIONS": dict(parse_qsl(parts.query)),
    }


SECRET_KEY = _required("SECRET_KEY", _DEV_SECRET_KEY)
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "ranking",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": parse_database_url(_required("DATABASE_URL", _DEV_DATABASE_URL))}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True
