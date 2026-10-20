"""Read actual responses from an explicitly started Compose or Kind preview.

Lifecycle belongs to Make/Compose/Helm. This file does not start applications.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(
        base_url=os.environ["PLATFORM_TEST_URL"], timeout=15, trust_env=False
    ) as connection:
        yield connection


def test_routes_security_and_real_flutter_identity(client: httpx.Client) -> None:
    lock = json.loads(
        Path(
            os.environ.get("PLATFORM_TEST_MANIFEST", str(ROOT / "artifacts.lock.json"))
        ).read_text()
    )
    for path in ("/", "/game", "/game/", "/about"):
        response = client.get(path)
        assert response.status_code == 200
        assert "no-cache" in response.headers["cache-control"]
        assert "'self'" in response.headers["content-security-policy"]
        assert response.headers["x-content-type-options"] == "nosniff"
    manifest = client.get(
        "/game/" + lock["game"]["manifestSha256"] + "/artifact-manifest.json"
    )
    assert manifest.status_code == 200
    assert (
        hashlib.sha256(manifest.content).hexdigest() == lock["game"]["manifestSha256"]
    )
    assert manifest.json()["clientCommit"] == lock["game"]["clientCommit"]
    assert "max-age=31536000" in manifest.headers["cache-control"]
    bootstrap = client.get(
        "/game/" + lock["game"]["manifestSha256"] + "/flutter_bootstrap.js"
    )
    assert bootstrap.status_code == 200
    assert (
        hashlib.sha256(bootstrap.content).hexdigest()
        == manifest.json()["files"]["flutter_bootstrap.js"]
    )
    assert client.get("/healthz").status_code == 404
    for path in ("/metrics", "/health/live", "/health/ready"):
        assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/api/unknown", "/realtime", "/game/missing/file.js"])
def test_unmapped_requests_never_fall_back_to_spa(
    client: httpx.Client, path: str
) -> None:
    response = client.get(path)
    assert response.status_code == 404 and '<div id="app">' not in response.text
