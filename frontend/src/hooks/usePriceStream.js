/**
 * Real-time Price Stream Hook
 * Re-exports the Zustand store for convenience
 *
 * Primary usage is via the store directly:
 * import usePriceStreamStore from '../stores/priceStreamStore';
 */
import usePriceStreamStore from '../stores/priceStreamStore';

/**
 * Hook wrapper for the price stream store
 * Provides a simplified interface for components
 *
 * @returns {Object} { prices, isConnected, error, subscribe, unsubscribe, connect, disconnect }
 */
export function usePriceStream() {
  const store = usePriceStreamStore();

  return {
    prices: store.prices,
    isConnected: store.isConnected,
    error: store.error,
    subscribe: store.subscribe,
    unsubscribe: store.unsubscribe,
    connect: store.connect,
    disconnect: store.disconnect,
  };
}

export default usePriceStream;
