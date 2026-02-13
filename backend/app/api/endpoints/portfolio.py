"""
Portfolio API endpoints
Broker connections and aggregated portfolio management
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from loguru import logger
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

from app.database import get_db

# Auto-sync threshold: re-fetch from broker if data is older than this
AUTO_SYNC_STALE_MINUTES = 5
from app.models.broker_connection import BrokerConnection, PortfolioPosition, PortfolioHistory
from app.services.brokers.robinhood_service import get_robinhood_service
from app.services.data_fetcher.alpaca_service import alpaca_service
from app.utils.crypto import encrypt_value, decrypt_value

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class BrokerLoginRequest(BaseModel):
    """Request to connect a broker account"""
    broker_type: str  # robinhood, alpaca, etc.
    username: str
    password: str
    mfa_code: Optional[str] = None
    device_token: Optional[str] = None
    account_name: Optional[str] = None


class MFASubmitRequest(BaseModel):
    """Submit MFA code for pending connection"""
    connection_id: int
    mfa_code: str


class BrokerConnectionResponse(BaseModel):
    """Response for broker connection operations"""
    success: bool
    message: str
    connection: Optional[Dict[str, Any]] = None
    requires_mfa: bool = False


# =============================================================================
# Broker Status Endpoints
# =============================================================================

@router.get("/brokers/status")
async def get_brokers_status():
    """Get status of all supported brokers"""
    robinhood_service = get_robinhood_service()

    return {
        "brokers": [
            {
                "type": "robinhood",
                "name": "Robinhood",
                "available": robinhood_service.is_available,
                "logged_in": robinhood_service.is_logged_in,
                "logo": "🟢",
                "features": ["stocks", "options", "crypto"],
            },
            {
                "type": "alpaca",
                "name": "Alpaca",
                "available": True,  # Always available via existing service
                "logged_in": False,  # Check via alpaca_trading_service
                "logo": "🦙",
                "features": ["stocks", "paper_trading"],
            },
            {
                "type": "webull",
                "name": "Webull",
                "available": False,  # Coming soon
                "logged_in": False,
                "logo": "🐂",
                "features": ["stocks", "options", "crypto"],
                "coming_soon": True,
            },
            {
                "type": "td_ameritrade",
                "name": "TD Ameritrade",
                "available": False,  # Coming soon
                "logged_in": False,
                "logo": "💚",
                "features": ["stocks", "options", "futures"],
                "coming_soon": True,
            },
        ]
    }


# =============================================================================
# Broker Connection Endpoints
# =============================================================================

@router.get("/connections")
async def get_connections(db: Session = Depends(get_db)):
    """Get all broker connections"""
    connections = db.query(BrokerConnection).all()

    return {
        "connections": [c.to_dict() for c in connections],
        "count": len(connections),
    }


@router.post("/connections")
async def connect_broker(request: BrokerLoginRequest, db: Session = Depends(get_db)):
    """
    Connect to a broker account.
    Returns connection status and may require MFA.
    """
    if request.broker_type == "robinhood":
        return await _connect_robinhood(request, db)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Broker type '{request.broker_type}' not supported yet"
        )


async def _connect_robinhood(request: BrokerLoginRequest, db: Session) -> Dict[str, Any]:
    """Handle Robinhood connection"""
    robinhood_service = get_robinhood_service()

    if not robinhood_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Robinhood service not available. Install robin_stocks: pip install robin_stocks"
        )

    # Check for existing connection
    existing = db.query(BrokerConnection).filter(
        BrokerConnection.broker_type == "robinhood",
        BrokerConnection.username == request.username
    ).first()

    if existing and existing.status == "connected":
        return {
            "success": True,
            "message": "Already connected to Robinhood",
            "connection": existing.to_dict(),
            "requires_mfa": False,
        }

    # Attempt login
    login_result = robinhood_service.login(
        username=request.username,
        password=request.password,
        mfa_code=request.mfa_code,
        device_token=request.device_token,
    )

    if login_result.get("requires_mfa") and not login_result.get("success"):
        # Create pending connection
        if not existing:
            connection = BrokerConnection(
                broker_type="robinhood",
                username=request.username,
                account_name=request.account_name or f"Robinhood ({request.username})",
                status="pending_mfa",
            )
            db.add(connection)
            db.commit()
            db.refresh(connection)
        else:
            existing.status = "pending_mfa"
            db.commit()
            connection = existing

        return {
            "success": False,
            "message": "MFA code required. Check your authenticator app or SMS.",
            "requires_mfa": True,
            "connection": connection.to_dict(),
        }

    if login_result.get("success"):
        # Get account info
        account_info = robinhood_service.get_account_info()

        # Encrypt password for auto re-login on session expiry
        encrypted_pw = ""
        if request.password:
            try:
                encrypted_pw = encrypt_value(request.password)
                logger.info("🔐 Password encrypted for auto re-login")
            except Exception as e:
                logger.warning(f"Could not encrypt password: {e} — auto re-login disabled")

        # Save or update connection
        if existing:
            existing.status = "connected"
            existing.device_token = login_result.get("device_token")
            existing.last_sync_at = datetime.now(timezone.utc)
            existing.last_error = None
            if encrypted_pw:
                existing.encrypted_password = encrypted_pw
            if account_info:
                existing.account_type = account_info.get("account_type")
                existing.buying_power = account_info.get("buying_power")
                existing.portfolio_value = account_info.get("portfolio_value")
                existing.cash_balance = account_info.get("cash")
                existing.account_id = account_info.get("account_number")
            db.commit()
            connection = existing
        else:
            connection = BrokerConnection(
                broker_type="robinhood",
                username=request.username,
                account_name=request.account_name or f"Robinhood ({request.username})",
                device_token=login_result.get("device_token"),
                encrypted_password=encrypted_pw or None,
                status="connected",
                last_sync_at=datetime.now(timezone.utc),
                account_type=account_info.get("account_type") if account_info else None,
                buying_power=account_info.get("buying_power") if account_info else None,
                portfolio_value=account_info.get("portfolio_value") if account_info else None,
                cash_balance=account_info.get("cash") if account_info else None,
                account_id=account_info.get("account_number") if account_info else None,
            )
            db.add(connection)
            db.commit()
            db.refresh(connection)

        # Sync positions
        await _sync_robinhood_positions(connection.id, db)

        return {
            "success": True,
            "message": "Successfully connected to Robinhood",
            "requires_mfa": False,
            "connection": connection.to_dict(),
        }

    # Login failed
    error_msg = login_result.get("error", "Login failed")
    if existing:
        existing.status = "error"
        existing.last_error = error_msg
        db.commit()

    raise HTTPException(status_code=401, detail=error_msg)


@router.post("/connections/{connection_id}/mfa")
async def submit_mfa(connection_id: int, request: MFASubmitRequest, db: Session = Depends(get_db)):
    """Submit MFA code for pending connection"""
    connection = db.query(BrokerConnection).filter(BrokerConnection.id == connection_id).first()

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    if connection.status != "pending_mfa":
        raise HTTPException(status_code=400, detail="Connection is not pending MFA")

    # Re-attempt login with MFA code
    login_request = BrokerLoginRequest(
        broker_type=connection.broker_type,
        username=connection.username,
        password="",  # Password stored in session
        mfa_code=request.mfa_code,
        device_token=connection.device_token,
    )

    if connection.broker_type == "robinhood":
        return await _connect_robinhood(login_request, db)

    raise HTTPException(status_code=400, detail="Unsupported broker type")


@router.delete("/connections/{connection_id}")
async def disconnect_broker(connection_id: int, db: Session = Depends(get_db)):
    """Disconnect a broker account"""
    connection = db.query(BrokerConnection).filter(BrokerConnection.id == connection_id).first()

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Logout from broker
    if connection.broker_type == "robinhood":
        robinhood_service = get_robinhood_service()
        robinhood_service.logout()

    # Delete positions
    db.query(PortfolioPosition).filter(
        PortfolioPosition.broker_connection_id == connection_id
    ).delete()

    # Delete connection
    db.delete(connection)
    db.commit()

    return {
        "success": True,
        "message": f"Disconnected from {connection.broker_type}",
    }


@router.post("/connections/{connection_id}/sync")
async def sync_connection(connection_id: int, db: Session = Depends(get_db)):
    """Manually sync positions for a connection"""
    logger.info(f"📡 Sync requested for connection {connection_id}")

    connection = db.query(BrokerConnection).filter(BrokerConnection.id == connection_id).first()

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    if connection.status not in ("connected", "session_expired"):
        raise HTTPException(status_code=400, detail="Connection is not active")

    if connection.broker_type == "robinhood":
        robinhood_service = get_robinhood_service()

        # Try to ensure we have a live session before syncing
        # (will attempt auto re-login if credentials are stored)
        session_ok = _ensure_robinhood_session(connection)

        if not session_ok or not robinhood_service.is_logged_in:
            # Session expired — mark the connection so the frontend can prompt re-login
            connection.status = "session_expired"
            connection.last_error = "Robinhood session expired. Please re-login."
            db.commit()
            logger.warning(f"⚠️ Robinhood session expired for connection {connection_id}")
            raise HTTPException(
                status_code=401,
                detail="Robinhood session expired. Please disconnect and re-connect your account."
            )

        # If auto re-login restored the session, persist the status change
        if connection.status == "connected":
            db.commit()

        positions_count = await _sync_robinhood_positions(connection_id, db)
        logger.info(f"✅ Synced {positions_count} positions")
        return {
            "success": True,
            "message": f"Synced {positions_count} positions",
            "positions_count": positions_count,
        }

    raise HTTPException(status_code=400, detail="Unsupported broker type")


def _ensure_robinhood_session(connection=None) -> bool:
    """
    Ensure the Robinhood singleton has an active session.

    robin_stocks persists sessions in pickle files on disk.  If the in-memory
    ``_logged_in`` flag is False (e.g. after a server restart) we try to
    restore the session from the pickle file by making a lightweight API call.

    If the pickle session is expired or missing, and the connection has an
    encrypted password stored, we automatically re-login to Robinhood without
    any user intervention.

    Hardened to handle:
    - Missing pickle file (expected after logout or first run)
    - Corrupted pickle file (auto-removed so fresh login can proceed)
    - Expired session tokens (detected via failed API call → auto re-login)
    """
    robinhood_service = get_robinhood_service()
    if robinhood_service.is_logged_in:
        return True

    # Step 1: Validate pickle file health before attempting restore
    session_info = robinhood_service.validate_session()

    if not session_info["pickle_exists"]:
        logger.info("No Robinhood pickle file found - login required")
        # Try auto re-login with stored credentials
        return _auto_relogin(connection, robinhood_service)

    if not session_info["pickle_valid"]:
        logger.warning(
            f"Robinhood pickle file is invalid: {session_info['error']}. "
            "Removing corrupt file so a fresh login can proceed."
        )
        from app.services.brokers.robinhood_service import _remove_corrupt_pickle
        _remove_corrupt_pickle()
        # Try auto re-login with stored credentials
        return _auto_relogin(connection, robinhood_service)

    # Step 2: Attempt session restore via lightweight API call
    logger.info("Attempting to restore Robinhood session from pickle file...")
    try:
        import robin_stocks.robinhood as rh
        profile = rh.profiles.load_account_profile()
        if profile and isinstance(profile, dict) and profile.get("account_number"):
            logger.info("Robinhood session restored from pickle file")
            robinhood_service._logged_in = True
            if connection:
                robinhood_service._username = connection.username
            return True
        else:
            logger.warning("Robinhood session restore returned empty profile - session may be expired")
            # Try auto re-login with stored credentials
            return _auto_relogin(connection, robinhood_service)
    except Exception as e:
        error_msg = str(e).lower()
        if "401" in error_msg or "unauthorized" in error_msg or "token" in error_msg:
            logger.warning(f"Robinhood session expired (auth error): {e}")
        else:
            logger.warning(f"Could not restore Robinhood session: {e}")
        # Try auto re-login with stored credentials
        return _auto_relogin(connection, robinhood_service)


def _auto_relogin(connection, robinhood_service) -> bool:
    """
    Attempt automatic re-login to Robinhood using stored encrypted credentials.

    This is called when the pickle session is expired, missing, or corrupt.
    If the connection has an encrypted_password, we decrypt it and attempt
    to re-authenticate silently.

    Returns True if re-login succeeds, False otherwise.
    """
    if not connection:
        logger.info("No connection object — cannot auto re-login")
        return False

    if not connection.encrypted_password:
        logger.info("No encrypted password stored — manual re-login required")
        return False

    if not connection.username:
        logger.warning("No username stored — cannot auto re-login")
        return False

    logger.info(f"🔄 Attempting auto re-login for Robinhood ({connection.username})...")

    try:
        password = decrypt_value(connection.encrypted_password)
    except (ValueError, Exception) as e:
        logger.error(f"❌ Failed to decrypt stored password: {e}")
        return False

    try:
        login_result = robinhood_service.login(
            username=connection.username,
            password=password,
            device_token=connection.device_token,
        )

        if login_result.get("success"):
            logger.info("✅ Auto re-login successful! Session restored.")
            # Update connection status back to connected
            connection.status = "connected"
            connection.last_error = None
            return True

        if login_result.get("requires_mfa"):
            logger.warning("⚠️ Auto re-login requires MFA — manual intervention needed")
            return False

        error = login_result.get("error", "Unknown error")
        logger.warning(f"⚠️ Auto re-login failed: {error}")
        return False

    except Exception as e:
        logger.error(f"❌ Auto re-login exception: {e}")
        return False


async def _sync_robinhood_positions(connection_id: int, db: Session) -> int:
    """
    Sync Robinhood positions to database.

    Non-destructive per asset type: only deletes + re-inserts rows for asset
    types that were fetched successfully.  If crypto fetch fails but stocks
    succeed, existing crypto rows are preserved.
    """
    robinhood_service = get_robinhood_service()

    # Always try to restore the session before syncing
    connection = db.query(BrokerConnection).filter(BrokerConnection.id == connection_id).first()
    _ensure_robinhood_session(connection)

    logger.info(f"🔄 Syncing Robinhood positions for connection {connection_id}")
    logger.info(f"   is_logged_in: {robinhood_service.is_logged_in}")
    logger.info(f"   is_available: {robinhood_service.is_available}")

    if not robinhood_service.is_logged_in:
        logger.warning("⚠️ Robinhood service not logged in - cannot sync positions")
        return 0

    # Fetch each asset type separately so we can tell success from failure
    logger.info("📊 Fetching positions from Robinhood...")
    result = robinhood_service.get_all_positions()

    # result = {stock: list|None, option: list|None, crypto: list|None, combined: list}
    synced_count = 0

    for asset_type in ("stock", "option", "crypto"):
        fetched = result.get(asset_type)

        if fetched is None:
            # Fetch failed for this type — preserve existing DB rows
            logger.warning(f"⚠️ {asset_type} fetch failed — preserving existing {asset_type} rows")
            continue

        # Delete only rows of this asset type for this connection
        db.query(PortfolioPosition).filter(
            PortfolioPosition.broker_connection_id == connection_id,
            PortfolioPosition.asset_type == asset_type,
        ).delete()

        # Insert fresh rows
        for pos in fetched:
            db_position = PortfolioPosition(
                broker_connection_id=connection_id,
                symbol=pos.get("symbol", ""),
                name=pos.get("name", ""),
                quantity=pos.get("quantity", 0),
                average_cost=pos.get("average_cost"),
                current_price=pos.get("current_price"),
                market_value=pos.get("market_value"),
                unrealized_pl=pos.get("unrealized_pl"),
                unrealized_pl_percent=pos.get("unrealized_pl_percent"),
                day_change=pos.get("day_change"),
                day_change_percent=pos.get("day_change_percent"),
                asset_type=pos.get("asset_type", asset_type),
                option_type=pos.get("option_type"),
                strike_price=pos.get("strike_price"),
                expiration_date=datetime.fromisoformat(pos["expiration_date"]) if pos.get("expiration_date") else None,
                last_synced_at=datetime.now(timezone.utc),
            )
            db.add(db_position)

        synced_count += len(fetched)
        logger.info(f"   ✅ {asset_type}: synced {len(fetched)} positions")

    # Flush pending inserts so subsequent queries can see the new positions
    db.flush()

    # Update connection sync time and portfolio value
    connection = db.query(BrokerConnection).filter(BrokerConnection.id == connection_id).first()
    if connection:
        account_info = robinhood_service.get_account_info()
        connection.last_sync_at = datetime.now(timezone.utc)
        if account_info:
            connection.buying_power = account_info.get("buying_power")
            connection.cash_balance = account_info.get("cash")

        # Compute portfolio_value from freshly-synced positions + cash.
        # Robinhood's `extended_hours_equity` only covers stocks; it
        # excludes options and crypto.  Since we just synced ALL position
        # types with current prices from Robinhood, summing them gives
        # the most accurate total.
        all_positions = db.query(PortfolioPosition).filter(
            PortfolioPosition.broker_connection_id == connection_id
        ).all()
        total_mv = sum(p.market_value or 0 for p in all_positions)
        cash = connection.cash_balance or 0
        connection.portfolio_value = total_mv + cash
        logger.info(
            f"💰 Portfolio value: ${connection.portfolio_value:,.2f} "
            f"(positions: ${total_mv:,.2f} + cash: ${cash:,.2f})"
        )

    db.commit()

    return synced_count


# =============================================================================
# Portfolio Data Endpoints
# =============================================================================

async def _auto_sync_if_stale(connections, db: Session):
    """Auto-sync connected brokers if data is older than threshold."""
    now = datetime.now(timezone.utc)
    stale_threshold = timedelta(minutes=AUTO_SYNC_STALE_MINUTES)

    for conn in connections:
        if conn.broker_type != "robinhood":
            continue

        # Skip connections that aren't actively connected or recently expired
        # (session_expired can be recovered via auto re-login)
        if conn.status not in ("connected", "session_expired"):
            continue

        # Respect the auto_sync preference on the connection
        if not conn.auto_sync:
            continue

        last_sync = conn.last_sync_at
        if last_sync and last_sync.tzinfo is None:
            last_sync = last_sync.replace(tzinfo=timezone.utc)

        if not last_sync or (now - last_sync) > stale_threshold:
            try:
                logger.info(f"Auto-syncing stale Robinhood connection {conn.id} (last sync: {last_sync})")
                # Check session before attempting sync
                robinhood_service = get_robinhood_service()
                session_ok = _ensure_robinhood_session(conn)
                if not session_ok or not robinhood_service.is_logged_in:
                    logger.warning(f"⚠️ Robinhood session expired for connection {conn.id} - skipping auto-sync")
                    conn.status = "session_expired"
                    conn.last_error = "Session expired. Please re-login."
                    db.commit()
                    continue
                await _sync_robinhood_positions(conn.id, db)
                # Refresh the connection object after sync
                db.refresh(conn)
            except Exception as e:
                logger.warning(f"Auto-sync failed for connection {conn.id}: {e}")


@router.get("/summary")
async def get_portfolio_summary(db: Session = Depends(get_db)):
    """Get aggregated portfolio summary across all connected brokers"""
    connections = db.query(BrokerConnection).filter(
        BrokerConnection.status.in_(["connected", "session_expired"])
    ).all()

    # Auto-sync if data is stale
    if connections:
        await _auto_sync_if_stale(connections, db)

    if not connections:
        return {
            "connected": False,
            "message": "No broker accounts connected",
            "total_portfolio_value": 0,
            "total_cash": 0,
            "total_buying_power": 0,
            "total_positions": 0,
            "total_unrealized_pl": 0,
            "brokers": [],
        }

    # Aggregate values
    total_value = sum(c.portfolio_value or 0 for c in connections)
    total_cash = sum(c.cash_balance or 0 for c in connections)
    total_buying_power = sum(c.buying_power or 0 for c in connections)

    # Get all positions
    positions = db.query(PortfolioPosition).filter(
        PortfolioPosition.broker_connection_id.in_([c.id for c in connections])
    ).all()

    total_unrealized_pl = sum(p.unrealized_pl or 0 for p in positions)

    # Cost basis = market_value - unrealized_pl for each position
    total_cost_basis = sum((p.market_value or 0) - (p.unrealized_pl or 0) for p in positions)

    return {
        "connected": True,
        "total_portfolio_value": total_value,
        "total_cash": total_cash,
        "total_buying_power": total_buying_power,
        "total_invested": total_value - total_cash,
        "total_cost_basis": total_cost_basis,
        "total_positions": len(positions),
        "total_unrealized_pl": total_unrealized_pl,
        "total_unrealized_pl_percent": (total_unrealized_pl / total_cost_basis * 100) if total_cost_basis > 0 else 0,
        "brokers": [c.to_dict() for c in connections],
        "last_sync": max([c.last_sync_at for c in connections if c.last_sync_at], default=None),
    }


@router.get("/positions")
async def get_all_positions(
    broker_id: Optional[int] = None,
    asset_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all positions across connected brokers"""
    # Auto-sync if stale
    connections = db.query(BrokerConnection).filter(
        BrokerConnection.status.in_(["connected", "session_expired"])
    ).all()
    if connections:
        await _auto_sync_if_stale(connections, db)

    query = db.query(PortfolioPosition)

    if broker_id:
        query = query.filter(PortfolioPosition.broker_connection_id == broker_id)

    if asset_type:
        query = query.filter(PortfolioPosition.asset_type == asset_type)

    positions = query.all()

    # Calculate totals
    total_value = sum(p.market_value or 0 for p in positions)
    total_pl = sum(p.unrealized_pl or 0 for p in positions)

    return {
        "positions": [p.to_dict() for p in positions],
        "count": len(positions),
        "total_market_value": total_value,
        "total_unrealized_pl": total_pl,
    }


@router.post("/positions/refresh-prices")
async def refresh_position_prices(db: Session = Depends(get_db)):
    """
    Refresh portfolio position prices using Alpaca live market data.

    Updates stocks via Alpaca Stock snapshots and crypto via Alpaca Crypto
    snapshots.  No Robinhood API call required.
    """
    updated = 0
    all_refreshed_positions = []

    # --- Stock positions ---
    stock_positions = db.query(PortfolioPosition).filter(
        PortfolioPosition.asset_type == "stock"
    ).all()

    if stock_positions:
        stock_symbols = list({p.symbol for p in stock_positions if p.symbol})
        if stock_symbols:
            snapshots = alpaca_service.get_multi_snapshots(stock_symbols)
            for pos in stock_positions:
                snap = snapshots.get(pos.symbol)
                if not snap or "current_price" not in snap:
                    continue
                updated += _apply_price_update(pos, snap)
            all_refreshed_positions.extend(stock_positions)

    # --- Crypto positions ---
    crypto_positions = db.query(PortfolioPosition).filter(
        PortfolioPosition.asset_type == "crypto"
    ).all()

    if crypto_positions:
        crypto_symbols = list({p.symbol for p in crypto_positions if p.symbol})
        if crypto_symbols:
            crypto_snaps = alpaca_service.get_crypto_snapshots(crypto_symbols)
            for pos in crypto_positions:
                snap = crypto_snaps.get(pos.symbol)
                if not snap or "current_price" not in snap:
                    continue
                updated += _apply_price_update(pos, snap)
            all_refreshed_positions.extend(crypto_positions)

    # Commit position-level price updates only.
    # DO NOT recalculate connection-level portfolio_value here — that value
    # comes from Robinhood's authoritative `extended_hours_equity` during a
    # full sync and includes real-time option pricing that Alpaca cannot
    # provide.  Recalculating from position rows would mix fresh stock/crypto
    # prices with stale option prices, producing an inaccurate total.
    if updated:
        db.commit()

    return {
        "updated": updated,
        "stock_positions": len(stock_positions),
        "crypto_positions": len(crypto_positions),
    }


def _apply_price_update(pos: PortfolioPosition, snap: dict) -> int:
    """Apply a live price snapshot to a position row. Returns 1 if updated."""
    live_price = snap["current_price"]
    qty = pos.quantity or 0
    avg_cost = pos.average_cost or 0

    pos.current_price = live_price
    pos.market_value = live_price * qty
    if avg_cost > 0:
        cost_basis = avg_cost * qty
        pos.unrealized_pl = pos.market_value - cost_basis
        pos.unrealized_pl_percent = ((pos.market_value - cost_basis) / cost_basis) * 100 if cost_basis else 0

    change_pct = snap.get("change_percent")
    if change_pct is not None:
        pos.day_change_percent = change_pct
        pos.day_change = live_price - (live_price / (1 + change_pct / 100)) if change_pct != 0 else 0

    return 1


@router.get("/positions/{symbol}")
async def get_position_by_symbol(symbol: str, db: Session = Depends(get_db)):
    """Get position details for a specific symbol across all brokers"""
    positions = db.query(PortfolioPosition).filter(
        PortfolioPosition.symbol == symbol.upper()
    ).all()

    if not positions:
        return {
            "symbol": symbol.upper(),
            "has_position": False,
            "positions": [],
        }

    total_qty = sum(p.quantity for p in positions)
    total_value = sum(p.market_value or 0 for p in positions)
    total_pl = sum(p.unrealized_pl or 0 for p in positions)

    return {
        "symbol": symbol.upper(),
        "has_position": True,
        "total_quantity": total_qty,
        "total_market_value": total_value,
        "total_unrealized_pl": total_pl,
        "positions": [p.to_dict() for p in positions],
    }


@router.get("/history")
async def get_portfolio_history(
    span: str = "month",
    broker_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get portfolio value history for charts"""
    query = db.query(PortfolioHistory)

    if broker_id:
        query = query.filter(PortfolioHistory.broker_connection_id == broker_id)
    else:
        query = query.filter(PortfolioHistory.broker_connection_id.is_(None))

    history = query.order_by(PortfolioHistory.date.desc()).limit(365).all()

    return {
        "history": [h.to_dict() for h in history],
        "span": span,
    }


@router.get("/dividends")
async def get_dividends(db: Session = Depends(get_db)):
    """Get dividend history from Robinhood"""
    robinhood_service = get_robinhood_service()

    if not robinhood_service.is_logged_in:
        return {
            "dividends": [],
            "message": "Not logged in to Robinhood",
        }

    dividends = robinhood_service.get_dividends()

    return {
        "dividends": dividends,
        "count": len(dividends),
    }


@router.get("/orders/recent")
async def get_recent_orders(limit: int = 50, db: Session = Depends(get_db)):
    """Get recent orders from Robinhood"""
    robinhood_service = get_robinhood_service()

    if not robinhood_service.is_logged_in:
        return {
            "orders": [],
            "message": "Not logged in to Robinhood",
        }

    orders = robinhood_service.get_recent_orders(limit=limit)

    return {
        "orders": orders,
        "count": len(orders),
    }
