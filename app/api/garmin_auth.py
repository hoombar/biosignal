"""Garmin authentication API endpoints."""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from garminconnect import Garmin, GarminConnectAuthenticationError

from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/garmin/auth", tags=["garmin-auth"])


@dataclass
class MfaSession:
    """Holds in-progress MFA authentication state."""
    client: Garmin
    mfa_result: Any
    created_at: datetime = field(default_factory=datetime.utcnow)


_mfa_sessions: dict[str, MfaSession] = {}
MFA_SESSION_TTL = timedelta(minutes=5)


def _cleanup_expired_sessions():
    now = datetime.utcnow()
    expired = [
        sid for sid, session in _mfa_sessions.items()
        if now - session.created_at > MFA_SESSION_TTL
    ]
    for sid in expired:
        del _mfa_sessions[sid]
        logger.info(f"Cleaned up expired MFA session {sid}")


class AuthStatusResponse(BaseModel):
    status: str  # "valid", "not_configured", "expired"
    message: str


class LoginResponse(BaseModel):
    status: str  # "success", "mfa_required"
    message: str
    session_id: str | None = None


class MfaRequest(BaseModel):
    session_id: str
    mfa_code: str


class MfaResponse(BaseModel):
    status: str  # "success"
    message: str


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status():
    """Check if Garmin authentication is configured and valid."""
    settings = get_settings()
    token_dir = settings.garmin_token_dir

    oauth1_path = os.path.join(token_dir, "oauth1_token.json")
    oauth2_path = os.path.join(token_dir, "oauth2_token.json")

    if not os.path.exists(oauth1_path) or not os.path.exists(oauth2_path):
        return AuthStatusResponse(
            status="not_configured",
            message="No Garmin tokens found. Please set up authentication.",
        )

    def _validate():
        client = Garmin(settings.garmin_email, settings.garmin_password)
        client.login(token_dir)

    try:
        await asyncio.to_thread(_validate)
        return AuthStatusResponse(
            status="valid",
            message="Garmin authentication is active.",
        )
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return AuthStatusResponse(
            status="expired",
            message="Garmin tokens are expired or invalid. Please re-authenticate.",
        )


@router.post("/login", response_model=LoginResponse)
async def initiate_login():
    """Start Garmin login. Returns MFA session if MFA is required."""
    _cleanup_expired_sessions()
    settings = get_settings()

    os.environ.pop("GARMINTOKENS", None)

    def _login():
        client = Garmin(
            settings.garmin_email,
            settings.garmin_password,
            return_on_mfa=True,
        )
        result = client.login()
        return client, result

    try:
        client, result = await asyncio.to_thread(_login)
    except GarminConnectAuthenticationError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")
    except Exception as e:
        logger.error(f"Login initiation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {e}")

    # Check if MFA is required
    if isinstance(result, tuple) and len(result) == 2 and result[0] == "needs_mfa":
        session_id = str(uuid.uuid4())
        _mfa_sessions[session_id] = MfaSession(
            client=client,
            mfa_result=result[1],
        )
        return LoginResponse(
            status="mfa_required",
            message="MFA code required. Check your email or authenticator app.",
            session_id=session_id,
        )

    # No MFA needed - save tokens directly
    os.makedirs(settings.garmin_token_dir, exist_ok=True)
    client.garth.dump(settings.garmin_token_dir)
    os.environ["GARMINTOKENS"] = settings.garmin_token_dir
    return LoginResponse(
        status="success",
        message="Login successful. Tokens saved.",
    )


@router.post("/mfa", response_model=MfaResponse)
async def submit_mfa(request: MfaRequest):
    """Submit MFA code to complete login."""
    _cleanup_expired_sessions()
    settings = get_settings()

    session = _mfa_sessions.get(request.session_id)
    if not session:
        raise HTTPException(
            status_code=400,
            detail="MFA session not found or expired. Please restart login.",
        )

    def _resume():
        session.client.resume_login(session.mfa_result, request.mfa_code)
        os.makedirs(settings.garmin_token_dir, exist_ok=True)
        session.client.garth.dump(settings.garmin_token_dir)

    try:
        await asyncio.to_thread(_resume)
    except Exception as e:
        logger.error(f"MFA resume failed: {e}")
        raise HTTPException(
            status_code=401,
            detail=f"MFA verification failed: {e}",
        )

    del _mfa_sessions[request.session_id]
    os.environ["GARMINTOKENS"] = settings.garmin_token_dir

    return MfaResponse(
        status="success",
        message="Authentication complete. Garmin tokens saved.",
    )
