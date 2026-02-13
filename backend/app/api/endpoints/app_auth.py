"""
App-wide password protection with optional TOTP 2FA.

If APP_PASSWORD is set, all API requests (except /health, /docs, /auth/*) require
a valid session token obtained by POSTing the correct password to /auth/login.

If TOTP_SECRET is also set, login requires both password AND a valid 6-digit TOTP
code from an authenticator app (Google Authenticator, Authy, etc.).

Tokens are simple HMAC-signed timestamps — no database, no sessions to manage.
"""
import hashlib
import hmac
import io
import os
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

# Device trust: 14 days — skip TOTP on trusted devices
DEVICE_TRUST_TTL = 14 * 24 * 3600


# ── Env var helpers (Railway injects env vars; pydantic-settings may cache empty defaults) ──

def _get_app_password() -> str:
    """Get APP_PASSWORD — prefer os.environ for Railway, fallback to Settings."""
    return os.environ.get("APP_PASSWORD", "") or get_settings().APP_PASSWORD


def _get_totp_secret() -> str:
    """Get TOTP_SECRET — prefer os.environ for Railway, fallback to Settings."""
    return os.environ.get("TOTP_SECRET", "") or get_settings().TOTP_SECRET


# ── Token helpers ────────────────────────────────────────────────────────────

def _make_token(password: str, timestamp: int) -> str:
    """Create an HMAC-signed token from password + timestamp."""
    msg = f"{timestamp}".encode()
    key = password.encode()
    sig = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"{timestamp}.{sig}"


def verify_token(token: str) -> bool:
    """Verify a session token is valid and not expired."""
    password = _get_app_password()

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


# ── Device Trust Token (2FA remember-me) ────────────────────────────────────

def _make_device_token(password: str, timestamp: int) -> str:
    """Create an HMAC-signed device trust token (prefixed to distinguish from session tokens)."""
    msg = f"device:{timestamp}".encode()
    key = password.encode()
    sig = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"d.{timestamp}.{sig}"


def verify_device_token(token: str) -> bool:
    """Verify a device trust token is valid and not expired (14-day TTL)."""
    password = _get_app_password()
    if not password:
        return True
    if not token or not token.startswith("d."):
        return False
    try:
        parts = token.split(".", 2)
        if len(parts) != 3:
            return False
        _, timestamp_str, sig = parts
        timestamp = int(timestamp_str)
        if time.time() - timestamp > DEVICE_TRUST_TTL:
            return False
        expected = _make_device_token(password, timestamp)
        return hmac.compare_digest(token, expected)
    except (ValueError, TypeError):
        return False


# ── TOTP 2FA Helpers ─────────────────────────────────────────────────────────

def _get_totp(secret: str) -> pyotp.TOTP:
    """Create a TOTP instance from the secret."""
    return pyotp.TOTP(secret)


def verify_totp(code: str) -> bool:
    """Verify a TOTP code. Returns True if valid (with 30s tolerance window)."""
    secret = _get_totp_secret()
    if not secret:
        return True  # No 2FA configured — skip
    totp = _get_totp(secret)
    return totp.verify(code, valid_window=1)


# ── Request / Response Models ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    password: str
    totp_code: Optional[str] = None
    device_token: Optional[str] = None  # Device trust token to skip 2FA


class LoginResponse(BaseModel):
    success: bool
    token: str = ""
    message: str = ""
    requires_totp: bool = False
    device_token: str = ""  # Issued after successful 2FA, valid 14 days


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Verify password (+ optional TOTP) and return a session token."""
    app_pw = _get_app_password()
    totp_secret = _get_totp_secret()

    if not app_pw:
        return LoginResponse(success=True, token="open", message="No password required")

    if body.password != app_pw:
        raise HTTPException(status_code=401, detail="Incorrect password")

    # If 2FA is enabled, check device trust or require TOTP code
    device_token_out = ""
    if totp_secret:
        # Check if this device is trusted (skip TOTP)
        trusted = body.device_token and verify_device_token(body.device_token)

        if not trusted:
            if not body.totp_code:
                return LoginResponse(
                    success=False,
                    requires_totp=True,
                    message="2FA code required"
                )
            if not verify_totp(body.totp_code):
                raise HTTPException(status_code=401, detail="Invalid 2FA code")

            # 2FA succeeded — issue a device trust token (14-day remember-me)
            device_token_out = _make_device_token(app_pw, int(time.time()))

    timestamp = int(time.time())
    token = _make_token(app_pw, timestamp)
    return LoginResponse(
        success=True, token=token, message="Authenticated",
        device_token=device_token_out,
    )


@router.get("/check")
async def check_auth():
    """Check if password protection and 2FA are enabled (no auth required)."""
    app_pw = _get_app_password()
    totp_secret = _get_totp_secret()
    return {
        "protected": bool(app_pw),
        "totp_enabled": bool(totp_secret),
    }


@router.get("/totp/setup")
async def totp_setup():
    """
    Generate a TOTP setup QR code for the authenticator app.
    Returns a PNG QR code image.
    """
    secret = _get_totp_secret()

    if not secret:
        raise HTTPException(status_code=404, detail="2FA not configured on server")

    totp = _get_totp(secret)
    uri = totp.provisioning_uri(
        name="leaps-trader",
        issuer_name="LEAPS Trader"
    )

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
    secret = _get_totp_secret()
    app_pw = _get_app_password()

    if not secret:
        raise HTTPException(status_code=404, detail="2FA not configured")

    if body.password != app_pw:
        raise HTTPException(status_code=401, detail="Incorrect password")

    if not body.totp_code:
        raise HTTPException(status_code=400, detail="TOTP code required")

    if verify_totp(body.totp_code):
        return {"valid": True, "message": "2FA is working correctly"}
    else:
        raise HTTPException(status_code=401, detail="Invalid 2FA code. Check your authenticator app.")
