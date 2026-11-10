"""Django serves the Angular page, and never hides an API or file 404 behind it."""

from pathlib import Path
from typing import Any

import pytest
from django.test import Client


@pytest.fixture
def built_frontend(tmp_path: Path, settings: Any) -> Path:
    (tmp_path / "index.html").write_text("<app-root>built page</app-root>", encoding="utf-8")
    settings.FRONTEND_DIST = tmp_path
    return tmp_path


def body(response: Any) -> bytes:
    return b"".join(response.streaming_content)


@pytest.mark.parametrize("url", ["/", "/list/3", "/some/deep/link/"])
def test_page_paths_get_the_angular_page(client: Client, built_frontend: Path, url: str) -> None:
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/html"
    assert b"built page" in body(response)


@pytest.mark.parametrize("url", ["/api/nope/", "/static/app.js", "/missing.js", "/api"])
def test_api_and_file_paths_are_not_swallowed(
    client: Client, built_frontend: Path, url: str
) -> None:
    assert client.get(url).status_code == 404


def test_api_still_answers_as_json(client: Client, built_frontend: Path) -> None:
    response = client.get("/api/lists/")
    assert response.status_code == 200
    assert response.json() == []


def test_page_rejects_a_post(client: Client, built_frontend: Path) -> None:
    assert client.post("/list/3").status_code == 405


def test_unbuilt_frontend_is_a_404_not_a_crash(
    client: Client, tmp_path: Path, settings: Any
) -> None:
    settings.FRONTEND_DIST = tmp_path
    assert client.get("/").status_code == 404
