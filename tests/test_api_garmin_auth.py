"""Tests for Garmin auth API endpoints."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from app.api.garmin_auth import _mfa_sessions, router


def _make_test_app():
    app = FastAPI()
    app.include_router(router)
    return app


def _mock_settings(tmp_path):
    return SimpleNamespace(
        garmin_email="user@example.com",
        garmin_password="password",
        garmin_token_dir=str(tmp_path / ".garmin_tokens"),
    )


@pytest.fixture(autouse=True)
def clear_mfa_sessions():
    _mfa_sessions.clear()
    yield
    _mfa_sessions.clear()


class TestGarminAuthLogin:

    def test_login_returns_429_when_garmin_rate_limits(self, tmp_path):
        app = _make_test_app()
        settings = _mock_settings(tmp_path)

        with patch("app.api.garmin_auth.get_settings", return_value=settings):
            with patch("app.api.garmin_auth.Garmin") as mock_garmin:
                mock_client = MagicMock()
                mock_client.login.side_effect = GarminConnectTooManyRequestsError(
                    "Login failed (429 Rate Limit). Try again later."
                )
                mock_garmin.return_value = mock_client

                with TestClient(app) as client:
                    resp = client.post("/api/garmin/auth/login")

        assert resp.status_code == 429
        assert "Rate limit reached" in resp.json()["detail"]
        assert "429" in resp.json()["detail"]

    def test_login_returns_401_for_authentication_error(self, tmp_path):
        app = _make_test_app()
        settings = _mock_settings(tmp_path)

        with patch("app.api.garmin_auth.get_settings", return_value=settings):
            with patch("app.api.garmin_auth.Garmin") as mock_garmin:
                mock_client = MagicMock()
                mock_client.login.side_effect = GarminConnectAuthenticationError(
                    "401 Unauthorized"
                )
                mock_garmin.return_value = mock_client

                with TestClient(app) as client:
                    resp = client.post("/api/garmin/auth/login")

        assert resp.status_code == 401
        assert "Authentication failed" in resp.json()["detail"]

    def test_login_returns_500_for_unexpected_errors(self, tmp_path):
        app = _make_test_app()
        settings = _mock_settings(tmp_path)

        with patch("app.api.garmin_auth.get_settings", return_value=settings):
            with patch("app.api.garmin_auth.Garmin") as mock_garmin:
                mock_client = MagicMock()
                mock_client.login.side_effect = RuntimeError("boom")
                mock_garmin.return_value = mock_client

                with TestClient(app) as client:
                    resp = client.post("/api/garmin/auth/login")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "Login failed: boom"
