"""Settings for pytest: the development defaults, always on Postgres."""

import os

os.environ.setdefault("DEBUG", "1")

from config.settings import *  # noqa: E402, F403
