"""
Simple API token authentication for protected endpoints (trading, restart).

If TRADING_API_TOKEN is configured, requests must include either:
  - Header: X-API-Key: <token>
  - Header: Authorization: Bearer <token>

If TRADING_API_TOKEN is empty/unset, all requests are allowed (dev mode).
"""
import logging

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from app.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

_auth_warned = False


async def require_trading_auth(
    api_key: str = Security(api_key_header),
    bearer: HTTPAuthorizationCredentials = Security(bearer_scheme),
):
    """Dependency that enforces API token auth on protected endpoints."""
    global _auth_warned
    settings = get_settings()
    token = settings.TRADING_API_TOKEN

    # If no token configured, skip auth (local dev)
    if not token:
        if not _auth_warned:
            logging.warning("TRADING_API_TOKEN not set -- all endpoints are UNPROTECTED")
            _auth_warned = True
        return

    # Accept X-API-Key header
    if api_key and api_key == token:
        return

    # Accept Authorization: Bearer <token>
    if bearer and bearer.credentials == token:
        return

    raise HTTPException(
        status_code=401,
        detail="Invalid or missing API key. Set X-API-Key or Authorization: Bearer header.",
    )
