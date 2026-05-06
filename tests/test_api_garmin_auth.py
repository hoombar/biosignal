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

    def test_login_returns_429_when_auth_error_contains_rate_limit(self, tmp_path):
        app = _make_test_app()
        settings = _mock_settings(tmp_path)

        with patch("app.api.garmin_auth.get_settings", return_value=settings):
            with patch("app.api.garmin_auth.Garmin") as mock_garmin:
                mock_client = MagicMock()
                mock_client.login.side_effect = GarminConnectAuthenticationError(
                    "Authentication failed: Login failed (429 Rate Limit). Try again later."
                )
                mock_garmin.return_value = mock_client

                with TestClient(app) as client:
                    resp = client.post("/api/garmin/auth/login")

        assert resp.status_code == 429
        assert "Rate limit reached" in resp.json()["detail"]
        assert "429" in resp.json()["detail"]

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

    def test_login_saves_tokens_with_current_garmin_client_api(self, tmp_path):
        app = _make_test_app()
        settings = _mock_settings(tmp_path)

        garmin_session = MagicMock()
        garmin_session.login.return_value = (None, None)
        garmin_session.client = MagicMock()

        with patch("app.api.garmin_auth.get_settings", return_value=settings):
            with patch("app.api.garmin_auth.Garmin", return_value=garmin_session):
                with TestClient(app) as client:
                    resp = client.post("/api/garmin/auth/login")

        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        garmin_session.client.dump.assert_called_once_with(settings.garmin_token_dir)


class TestGarminAuthMfa:

    def test_mfa_saves_tokens_with_current_garmin_client_api(self, tmp_path):
        app = _make_test_app()
        settings = _mock_settings(tmp_path)

        garmin_session = MagicMock()
        garmin_session.login.return_value = ("needs_mfa", {"state": "abc"})
        garmin_session.client = MagicMock()

        with patch("app.api.garmin_auth.get_settings", return_value=settings):
            with patch("app.api.garmin_auth.Garmin", return_value=garmin_session):
                with TestClient(app) as client:
                    login_resp = client.post("/api/garmin/auth/login")
                    mfa_resp = client.post(
                        "/api/garmin/auth/mfa",
                        json={
                            "session_id": login_resp.json()["session_id"],
                            "mfa_code": "123456",
                        },
                    )

        assert mfa_resp.status_code == 200
        assert mfa_resp.json()["status"] == "success"
        garmin_session.resume_login.assert_called_once_with(
            {"state": "abc"},
            "123456",
        )
        garmin_session.client.dump.assert_called_once_with(settings.garmin_token_dir)


class TestGarminAuthStatus:

    def test_status_validates_tokens_without_credential_fallback(self, tmp_path):
        app = _make_test_app()
        settings = _mock_settings(tmp_path)

        token_dir = tmp_path / ".garmin_tokens"
        token_dir.mkdir()
        (token_dir / "oauth1_token.json").write_text("{}", encoding="utf-8")
        (token_dir / "oauth2_token.json").write_text("{}", encoding="utf-8")

        with patch("app.api.garmin_auth.get_settings", return_value=settings):
            with patch("app.api.garmin_auth.Garmin") as mock_garmin:
                mock_client = MagicMock()
                mock_client.login.return_value = (None, None)
                mock_garmin.return_value = mock_client

                with TestClient(app) as client:
                    resp = client.get("/api/garmin/auth/status")

        assert resp.status_code == 200
        assert resp.json()["status"] == "valid"
        mock_garmin.assert_called_once_with("", "")
        mock_client.login.assert_called_once_with(settings.garmin_token_dir)
