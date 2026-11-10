"""Settings for pytest: the development defaults, always on Postgres."""

import os

os.environ.setdefault("DEBUG", "1")

from config.settings import *  # noqa: E402, F403

API_THROTTLE_RATE = None

# Tests supply their own build; a local frontend/dist must not change their results.
WHITENOISE_ROOT = None
