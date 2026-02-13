"""
WebSocket endpoints for real-time data streaming
"""
import asyncio
import json
from typing import Dict, Set, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from app.services.data_fetcher.price_stream_service import (
    get_price_stream_service,
    PriceStreamService,
)

router = APIRouter()


class ConnectionManager:
    """
    Manages WebSocket connections and subscriptions.

    Each client can subscribe to different symbols.
    Price updates are broadcast only to clients subscribed to that symbol.
    """

    def __init__(self):
        # Map of websocket -> set of subscribed symbols
        self._connections: Dict[WebSocket, Set[str]] = {}
        self._lock = asyncio.Lock()
        self._price_service: PriceStreamService = None

    async def _ensure_price_service(self) -> None:
        """Lazy initialize and start price service"""
        if self._price_service is None:
            self._price_service = get_price_stream_service()
            self._price_service.register_callback(self._on_price_update)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection"""
        await websocket.accept()
        async with self._lock:
            self._connections[websocket] = set()
        await self._ensure_price_service()
        logger.info(f"WebSocket connected. Total connections: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Handle WebSocket disconnection"""
        async with self._lock:
            if websocket in self._connections:
                symbols = self._connections.pop(websocket)
                logger.info(f"WebSocket disconnected. Was subscribed to: {symbols}")

                # Check if any symbols are no longer needed
                all_subscribed = set()
                for syms in self._connections.values():
                    all_subscribed.update(syms)

                orphaned = symbols - all_subscribed
                if orphaned and self._price_service:
                    await self._price_service.unsubscribe(orphaned)

        logger.info(f"Total connections: {len(self._connections)}")

    async def subscribe(self, websocket: WebSocket, symbols: Set[str]) -> None:
        """Subscribe a client to symbols"""
        async with self._lock:
            if websocket not in self._connections:
                return

            self._connections[websocket].update(symbols)

        # Subscribe to Alpaca stream
        if self._price_service:
            await self._price_service.subscribe(symbols)

            # Start stream if not running
            if not self._price_service.is_running:
                await self._price_service.start()

        # Send latest cached prices immediately
        if self._price_service:
            for symbol in symbols:
                latest = self._price_service.get_latest_price(symbol)
                if latest:
                    await self._send_to_client(websocket, {
                        "type": "snapshot",
                        "symbol": symbol,
                        **latest,
                    })

        logger.info(f"Client subscribed to: {symbols}")

    async def unsubscribe(self, websocket: WebSocket, symbols: Set[str]) -> None:
        """Unsubscribe a client from symbols"""
        async with self._lock:
            if websocket not in self._connections:
                return

            self._connections[websocket] -= symbols

            # Check if any symbols are no longer needed by anyone
            all_subscribed = set()
            for syms in self._connections.values():
                all_subscribed.update(syms)

            orphaned = symbols - all_subscribed
            if orphaned and self._price_service:
                await self._price_service.unsubscribe(orphaned)

        logger.info(f"Client unsubscribed from: {symbols}")

    async def _send_to_client(self, websocket: WebSocket, data: Dict[str, Any]) -> None:
        """Send data to a specific client"""
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error(f"Error sending to client: {e}")

    async def _on_price_update(self, data: Dict[str, Any]) -> None:
        """Callback for price updates from Alpaca stream"""
        symbol = data.get("symbol")
        if not symbol:
            return

        # Broadcast to all clients subscribed to this symbol
        async with self._lock:
            for ws, symbols in list(self._connections.items()):
                if symbol in symbols:
                    await self._send_to_client(ws, data)

    async def broadcast(self, data: Dict[str, Any]) -> None:
        """Broadcast data to all connected clients"""
        async with self._lock:
            for websocket in list(self._connections.keys()):
                await self._send_to_client(websocket, data)


# Singleton connection manager
manager = ConnectionManager()


@router.websocket("/prices")
async def websocket_prices(websocket: WebSocket):
    """
    WebSocket endpoint for real-time price streaming.

    Protocol:
    - Client connects
    - Client sends: {"action": "subscribe", "symbols": ["AAPL", "MSFT"]}
    - Server sends price updates: {"type": "trade", "symbol": "AAPL", "price": 150.25, ...}
    - Client can send: {"action": "unsubscribe", "symbols": ["AAPL"]}
    - Client can send: {"action": "ping"} to keep alive
    """
    await manager.connect(websocket)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            action = data.get("action")

            if action == "subscribe":
                symbols = set(s.upper() for s in data.get("symbols", []))
                if symbols:
                    await manager.subscribe(websocket, symbols)
                    await websocket.send_json({
                        "type": "subscribed",
                        "symbols": list(symbols),
                    })

            elif action == "unsubscribe":
                symbols = set(s.upper() for s in data.get("symbols", []))
                if symbols:
                    await manager.unsubscribe(websocket, symbols)
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "symbols": list(symbols),
                    })

            elif action == "ping":
                await websocket.send_json({"type": "pong"})

            elif action == "status":
                price_service = get_price_stream_service()
                await websocket.send_json({
                    "type": "status",
                    "stream_running": price_service.is_running,
                    "subscribed_symbols": list(price_service.subscribed_symbols),
                    "available": price_service.is_available,
                })

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(websocket)


@router.get("/prices/status")
async def get_stream_status():
    """Get status of the price stream"""
    service = get_price_stream_service()
    return {
        "available": service.is_available,
        "running": service.is_running,
        "subscribed_symbols": list(service.subscribed_symbols),
        "cached_prices": len(service.get_all_latest_prices()),
    }
