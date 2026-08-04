"""SPA fallback must never serve index.html for unmatched /api/* paths.

The fallback (app.main spa_fallback) exists so React Router owns client-side
routing.  But an unmatched /api/* path returning HTML 200 hides typos and
missing routes from the frontend (JSON.parse explodes on HTML).  Contract:
unknown /api/* -> 404 JSON (401 JSON when unauthenticated, via the auth
gate); unknown non-api path -> index.html.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    from app.config import settings
    import app.main
    from app.services import auth as auth_service

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>spa</body></html>", encoding="utf-8")
    monkeypatch.setattr(settings, "static_dir", dist)
    monkeypatch.setattr(app.main, "_static", dist)
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "auth_password", "host-test-password")
    monkeypatch.setattr(auth_service, "_configured_cache", None)
    auth_service._sessions.clear()

    fallback = next(
        (r for r in app.main.app.routes if getattr(r, "path", None) == "/{full_path:path}"),
        None,
    )
    if fallback is None:
        pytest.skip("SPA fallback not registered (no static dir at import time)")

    return TestClient(app.main.app)


def test_unknown_api_path_unauthenticated_is_401_json(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/api/definitely-not-a-route")
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/json")


def test_unknown_api_path_authenticated_returns_404_json(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        login = client.post("/api/auth/login", json={"password": "host-test-password"})
        assert login.status_code == 200
        response = client.get("/api/definitely-not-a-route")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        assert response.json() == {"detail": "Not Found"}


def test_bare_api_prefix_authenticated_returns_404_json(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        client.post("/api/auth/login", json={"password": "host-test-password"})
        response = client.get("/api")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")


def test_unknown_non_api_path_serves_spa(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        response = client.get("/some/client/route")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "spa" in response.text
