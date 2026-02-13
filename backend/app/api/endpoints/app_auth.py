"""
App-wide password protection.

If APP_PASSWORD is set, all API requests (except /health, /docs, /auth/*) require
a valid session token obtained by POSTing the correct password to /auth/login.

Tokens are simple HMAC-signed timestamps — no database, no sessions to manage.
"""
import hashlib
import hmac
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter()

# Token validity: 30 days (single user, convenience)
TOKEN_TTL_SECONDS = 30 * 24 * 3600


def _make_token(password: str, timestamp: int) -> str:
    """Create an HMAC-signed token from password + timestamp."""
    msg = f"{timestamp}".encode()
    key = password.encode()
    sig = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"{timestamp}.{sig}"


def verify_token(token: str) -> bool:
    """Verify a session token is valid and not expired."""
    settings = get_settings()
    password = settings.APP_PASSWORD

    if not password:
        return True  # No password set — everything passes

    if not token:
        return False

    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False

        timestamp_str, sig = parts
        timestamp = int(timestamp_str)

        # Check expiry
        if time.time() - timestamp > TOKEN_TTL_SECONDS:
            return False

        # Verify signature
        expected = _make_token(password, timestamp)
        return hmac.compare_digest(token, expected)
    except (ValueError, TypeError):
        return False


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: str = ""
    message: str = ""


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Verify password and return a session token."""
    settings = get_settings()

    if not settings.APP_PASSWORD:
        # No password configured — return a dummy token
        return LoginResponse(success=True, token="open", message="No password required")

    if body.password != settings.APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect password")

    timestamp = int(time.time())
    token = _make_token(settings.APP_PASSWORD, timestamp)
    return LoginResponse(success=True, token=token, message="Authenticated")


@router.get("/check")
async def check_auth():
    """Check if password protection is enabled (no auth required)."""
    settings = get_settings()
    return {"protected": bool(settings.APP_PASSWORD)}
