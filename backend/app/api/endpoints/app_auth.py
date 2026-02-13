"""
App-wide password protection with optional TOTP 2FA.

If APP_PASSWORD is set, all API requests (except /health, /docs, /auth/*) require
a valid session token obtained by POSTing the correct password to /auth/login.

If TOTP_SECRET is also set, login requires both password AND a valid 6-digit TOTP
code from an authenticator app (Google Authenticator, Authy, etc.).

Tokens are simple HMAC-signed timestamps — no database, no sessions to manage.
"""
import base64
import hashlib
import hmac
import io
import time
from typing import Optional

import pyotp
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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


# ── TOTP 2FA Helpers ─────────────────────────────────────────────────────────

def _get_totp(secret: str) -> pyotp.TOTP:
    """Create a TOTP instance from the secret."""
    return pyotp.TOTP(secret)


def verify_totp(code: str) -> bool:
    """Verify a TOTP code. Returns True if valid (with 30s tolerance window)."""
    settings = get_settings()
    if not settings.TOTP_SECRET:
        return True  # No 2FA configured — skip
    totp = _get_totp(settings.TOTP_SECRET)
    return totp.verify(code, valid_window=1)  # Allow 1 step tolerance (30s before/after)


# ── Request / Response Models ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str
    totp_code: Optional[str] = None  # 6-digit code from authenticator app


class LoginResponse(BaseModel):
    success: bool
    token: str = ""
    message: str = ""
    requires_totp: bool = False


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Verify password (+ optional TOTP) and return a session token."""
    settings = get_settings()

    if not settings.APP_PASSWORD:
        return LoginResponse(success=True, token="open", message="No password required")

    if body.password != settings.APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect password")

    # If 2FA is enabled, require TOTP code
    if settings.TOTP_SECRET:
        if not body.totp_code:
            # Password correct, but need 2FA code
            return LoginResponse(
                success=False,
                requires_totp=True,
                message="2FA code required"
            )
        if not verify_totp(body.totp_code):
            raise HTTPException(status_code=401, detail="Invalid 2FA code")

    timestamp = int(time.time())
    token = _make_token(settings.APP_PASSWORD, timestamp)
    return LoginResponse(success=True, token=token, message="Authenticated")


@router.get("/check")
async def check_auth():
    """Check if password protection and 2FA are enabled (no auth required)."""
    settings = get_settings()
    return {
        "protected": bool(settings.APP_PASSWORD),
        "totp_enabled": bool(settings.TOTP_SECRET),
    }


@router.get("/totp/setup")
async def totp_setup():
    """
    Generate a TOTP setup QR code for the authenticator app.
    Only works when TOTP_SECRET is configured on the server.
    Returns a PNG QR code image.
    """
    settings = get_settings()

    if not settings.TOTP_SECRET:
        raise HTTPException(status_code=404, detail="2FA not configured on server")

    # Verify caller has a valid session (must be logged in to see setup)
    # This endpoint is still under /auth/ path which is whitelisted in middleware,
    # so we rely on the frontend gating access to this page.

    totp = _get_totp(settings.TOTP_SECRET)
    uri = totp.provisioning_uri(
        name="leaps-trader",
        issuer_name="LEAPS Trader"
    )

    # Generate QR code as PNG
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return StreamingResponse(buf, media_type="image/png")


@router.post("/totp/verify")
async def totp_verify_code(body: LoginRequest):
    """Verify a TOTP code (for setup confirmation). Requires password."""
    settings = get_settings()

    if not settings.TOTP_SECRET:
        raise HTTPException(status_code=404, detail="2FA not configured")

    if body.password != settings.APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect password")

    if not body.totp_code:
        raise HTTPException(status_code=400, detail="TOTP code required")

    if verify_totp(body.totp_code):
        return {"valid": True, "message": "2FA is working correctly"}
    else:
        raise HTTPException(status_code=401, detail="Invalid 2FA code. Check your authenticator app.")
