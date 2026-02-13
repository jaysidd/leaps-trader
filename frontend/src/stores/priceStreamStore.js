/**
 * Zustand store for Real-time Price Streaming
 *
 * Manages:
 * - WebSocket connection to backend price stream
 * - Symbol subscriptions
 * - Live price data cache
 * - Connection status
 */
import { create } from 'zustand';

const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

// Use module-level variables for WebSocket (not in store state)
let ws = null;
let reconnectTimeout = null;
let heartbeatInterval = null;

const usePriceStreamStore = create((set, get) => ({
  // Connection state
  isConnected: false,
  error: null,
  reconnectAttempts: 0,
  maxRetries: 5,
  reconnectDelay: 3000,

  // Subscription state (use array instead of Set for Zustand reactivity)
  subscribedSymbols: [],
  prices: {},

  /**
   * Connect to WebSocket server
   */
  connect: () => {
    if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    try {
      console.log('[PriceStream] Connecting to', `${WS_BASE_URL}/ws/prices`);
      const socket = new WebSocket(`${WS_BASE_URL}/ws/prices`);
      ws = socket;

      socket.onopen = () => {
        // Guard: if this socket was replaced or closed before onopen fired, bail out
        if (ws !== socket || socket.readyState !== WebSocket.OPEN) {
          return;
        }

        console.log('[PriceStream] Connected');
        set({
          isConnected: true,
          error: null,
          reconnectAttempts: 0,
        });

        // Re-subscribe to symbols
        const { subscribedSymbols } = get();
        if (subscribedSymbols.length > 0) {
          console.log('[PriceStream] Re-subscribing to:', subscribedSymbols);
          socket.send(JSON.stringify({
            action: 'subscribe',
            symbols: subscribedSymbols,
          }));
        }

        // Start heartbeat
        if (heartbeatInterval) clearInterval(heartbeatInterval);
        heartbeatInterval = setInterval(() => {
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'ping' }));
          }
        }, 30000);
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'trade' || data.type === 'quote' || data.type === 'snapshot') {
            const symbol = data.symbol;
            if (!symbol) return;

            // Update prices immutably
            set((state) => ({
              prices: {
                ...state.prices,
                [symbol]: {
                  price: data.price ?? state.prices[symbol]?.price,
                  bid: data.bid ?? state.prices[symbol]?.bid,
                  ask: data.ask ?? state.prices[symbol]?.ask,
                  size: data.size ?? state.prices[symbol]?.size,
                  timestamp: data.timestamp,
                  type: data.type,
                },
              },
            }));
          } else if (data.type === 'subscribed') {
            console.log('[PriceStream] Subscribed to:', data.symbols);
          } else if (data.type === 'pong') {
            // Heartbeat response - connection alive
          } else if (data.type === 'status') {
            console.log('[PriceStream] Status:', data);
          }
        } catch (e) {
          console.error('[PriceStream] Parse error:', e);
        }
      };

      socket.onerror = (e) => {
        console.error('[PriceStream] Error:', e);
        set({ error: 'Connection error' });
      };

      socket.onclose = (e) => {
        console.log('[PriceStream] Closed:', e.code, e.reason);
        // Only clear ws if this socket is still the current one
        if (ws === socket) {
          ws = null;
        }

        // Clear heartbeat
        if (heartbeatInterval) {
          clearInterval(heartbeatInterval);
          heartbeatInterval = null;
        }

        set({ isConnected: false });

        // Attempt reconnection
        const { reconnectAttempts, maxRetries, reconnectDelay } = get();
        if (reconnectAttempts < maxRetries) {
          set({ reconnectAttempts: reconnectAttempts + 1 });
          console.log(`[PriceStream] Reconnecting (${reconnectAttempts + 1}/${maxRetries})...`);
          reconnectTimeout = setTimeout(() => get().connect(), reconnectDelay);
        } else {
          set({ error: 'Max reconnection attempts reached' });
        }
      };
    } catch (e) {
      console.error('[PriceStream] Connection failed:', e);
      set({ error: 'Failed to connect' });
    }
  },

  /**
   * Disconnect from WebSocket server
   */
  disconnect: () => {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval);
      heartbeatInterval = null;
    }
    if (ws) {
      ws.close();
      ws = null;
    }

    set({
      isConnected: false,
      reconnectAttempts: 0,
    });
  },

  /**
   * Subscribe to symbols
   * @param {string|string[]} symbols - Symbol(s) to subscribe to
   */
  subscribe: (symbols) => {
    const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
    const upperSymbols = symbolsArray.map((s) => s.toUpperCase());

    // Update subscribed symbols (avoid duplicates)
    set((state) => {
      const existing = new Set(state.subscribedSymbols);
      upperSymbols.forEach((s) => existing.add(s));
      return { subscribedSymbols: Array.from(existing) };
    });

    // Send to WebSocket if connected
    if (ws?.readyState === WebSocket.OPEN) {
      console.log('[PriceStream] Subscribing to:', upperSymbols);
      ws.send(JSON.stringify({
        action: 'subscribe',
        symbols: upperSymbols,
      }));
    }
  },

  /**
   * Unsubscribe from symbols
   * @param {string|string[]} symbols - Symbol(s) to unsubscribe from
   */
  unsubscribe: (symbols) => {
    const symbolsArray = Array.isArray(symbols) ? symbols : [symbols];
    const upperSymbols = symbolsArray.map((s) => s.toUpperCase());

    set((state) => {
      const newSubscribed = state.subscribedSymbols.filter((s) => !upperSymbols.includes(s));
      const newPrices = { ...state.prices };
      upperSymbols.forEach((s) => delete newPrices[s]);
      return {
        subscribedSymbols: newSubscribed,
        prices: newPrices,
      };
    });

    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        action: 'unsubscribe',
        symbols: upperSymbols,
      }));
    }
  },

  /**
   * Get price for a specific symbol
   * @param {string} symbol
   * @returns {Object|null}
   */
  getPrice: (symbol) => {
    const { prices } = get();
    return prices[symbol.toUpperCase()] || null;
  },

  /**
   * Clear all subscriptions and prices
   */
  clear: () => {
    const { subscribedSymbols } = get();

    if (ws?.readyState === WebSocket.OPEN && subscribedSymbols.length > 0) {
      ws.send(JSON.stringify({
        action: 'unsubscribe',
        symbols: subscribedSymbols,
      }));
    }

    set({
      subscribedSymbols: [],
      prices: {},
    });
  },
}));

export default usePriceStreamStore;
