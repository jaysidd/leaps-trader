/**
 * Macro Intelligence API client
 * Provides access to catalyst data, Trade Readiness scores, and ticker overlays
 *
 * Performance: Uses in-memory cache (5min TTL) and request deduplication
 * to avoid N individual API calls when rendering tables with MacroOverlay.
 */
import apiClient from './axios';

const BASE_URL = '/api/v1/command-center/macro-intelligence';

// =============================================================================
// CACHE + DEDUPLICATION LAYER
// =============================================================================

const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes - macro data changes slowly

// In-memory cache: symbol -> { data, timestamp }
const overlayCache = new Map();

// In-flight requests: symbol -> Promise (deduplication)
const inFlightRequests = new Map();

// Batch-level deduplication: sorted-symbols-key -> Promise
const inFlightBatches = new Map();

// Debounce state for batch fetches
let batchDebounceTimer = null;
let pendingBatchResolvers = [];
let pendingBatchSymbols = new Set();

/**
 * Get cached overlay data if still valid
 */
const getCached = (symbol) => {
  const entry = overlayCache.get(symbol);
  if (entry && Date.now() - entry.timestamp < CACHE_TTL_MS) {
    return entry.data;
  }
  return null;
};

/**
 * Store overlay data in cache
 */
const setCache = (symbol, data) => {
  overlayCache.set(symbol, { data, timestamp: Date.now() });
};

/**
 * Clear entire cache (useful after settings change or manual refresh)
 */
export const clearMacroCache = () => {
  overlayCache.clear();
  inFlightRequests.clear();
  inFlightBatches.clear();
  pendingBatchSymbols = new Set();
  pendingBatchResolvers = [];
  if (batchDebounceTimer) {
    clearTimeout(batchDebounceTimer);
    batchDebounceTimer = null;
  }
};

// =============================================================================
// CATALYST SUMMARY
// =============================================================================

/**
 * Get full catalyst summary including Trade Readiness score
 * Main endpoint for Macro Intelligence page
 */
export const getCatalystSummary = async () => {
  const response = await apiClient.get(`${BASE_URL}/catalysts/summary`);
  return response.data;
};

// =============================================================================
// LIQUIDITY
// =============================================================================

/**
 * Get liquidity regime score with metrics and drivers
 */
export const getLiquidityCatalyst = async () => {
  const response = await apiClient.get(`${BASE_URL}/catalysts/liquidity`);
  return response.data;
};

/**
 * Get historical liquidity scores for charting
 * @param {number} hours - Hours of history (default 168 = 7 days)
 */
export const getLiquidityHistory = async (hours = 168) => {
  const response = await apiClient.get(`${BASE_URL}/catalysts/liquidity/history`, {
    params: { hours },
  });
  return response.data;
};

// =============================================================================
// HISTORY
// =============================================================================

/**
 * Get full catalyst history including Trade Readiness
 * @param {number} hours - Hours of history (default 168 = 7 days)
 */
export const getCatalystHistory = async (hours = 168) => {
  const response = await apiClient.get(`${BASE_URL}/catalysts/history`, {
    params: { hours },
  });
  return response.data;
};

// =============================================================================
// TICKER CATALYSTS
// =============================================================================

/**
 * Get macro overlay for a specific ticker.
 * Uses cache + request deduplication to avoid redundant fetches.
 *
 * IMPORTANT: This overlay provides CONTEXT, not a gatekeeper.
 * - trade_compatibility is an INFO flag, NOT a gate
 * - Macro informs the trade, it never replaces the trader
 *
 * @param {string} symbol - Stock ticker
 * @param {string} sector - Optional sector (auto-detected if not provided)
 * @returns {Promise<Object>} Macro overlay data
 */
export const getTickerMacroOverlay = async (symbol, sector = null) => {
  if (!symbol) return null;

  const cacheKey = symbol.toUpperCase();

  // 1. Check cache first
  const cached = getCached(cacheKey);
  if (cached) return cached;

  // 2. Check if request already in-flight (deduplication)
  if (inFlightRequests.has(cacheKey)) {
    return inFlightRequests.get(cacheKey);
  }

  // 3. Make the request
  const params = sector ? { sector } : {};
  const promise = apiClient
    .get(`${BASE_URL}/ticker/${symbol}/macro-overlay`, { params })
    .then((response) => {
      const data = response.data;
      setCache(cacheKey, data);
      inFlightRequests.delete(cacheKey);
      return data;
    })
    .catch((err) => {
      inFlightRequests.delete(cacheKey);
      throw err;
    });

  inFlightRequests.set(cacheKey, promise);
  return promise;
};

/**
 * Internal: execute a batch fetch for the given symbols (no debounce/dedup).
 */
const _executeBatchFetch = async (symbols) => {
  const result = {};
  const uncached = [];

  for (const sym of symbols) {
    const cached = getCached(sym);
    if (cached) {
      result[sym] = cached;
    } else {
      uncached.push(sym);
    }
  }

  if (uncached.length === 0) return result;

  try {
    const response = await apiClient.post(`${BASE_URL}/macro-overlay/batch`, {
      symbols: uncached,
    });

    const batchData = response.data.overlays || {};
    for (const [sym, data] of Object.entries(batchData)) {
      setCache(sym, data);
      result[sym] = data;
    }
  } catch {
    // Batch endpoint unavailable - fall back to parallel individual requests
    const promises = uncached.map(async (sym) => {
      try {
        const data = await getTickerMacroOverlay(sym);
        result[sym] = data;
      } catch {
        // Individual failure - skip silently
      }
    });
    await Promise.all(promises);
  }

  return result;
};

/**
 * Batch fetch macro overlays for multiple symbols.
 *
 * Performance features:
 * - Debounce: coalesces rapid successive calls (150ms window)
 * - Batch dedup: identical symbol sets share one in-flight request
 * - Per-symbol cache: skips already-cached symbols
 * - Fallback: degrades to individual requests if batch endpoint fails
 *
 * @param {string[]} symbols - Array of stock tickers
 * @returns {Promise<Object>} Map of symbol -> overlay data
 */
export const getBatchMacroOverlay = (symbols) => {
  if (!symbols || symbols.length === 0) return Promise.resolve({});

  const upperSymbols = symbols.map((s) => s.toUpperCase());

  // Batch-level dedup: normalize symbol set as cache key
  const batchKey = [...upperSymbols].sort().join(',');
  if (inFlightBatches.has(batchKey)) {
    return inFlightBatches.get(batchKey);
  }

  // Debounce: accumulate symbols across rapid calls, flush after 150ms
  return new Promise((resolve, reject) => {
    for (const sym of upperSymbols) {
      pendingBatchSymbols.add(sym);
    }
    pendingBatchResolvers.push({ resolve, reject, requested: new Set(upperSymbols) });

    if (batchDebounceTimer) clearTimeout(batchDebounceTimer);

    batchDebounceTimer = setTimeout(() => {
      const allSymbols = [...pendingBatchSymbols];
      const resolvers = [...pendingBatchResolvers];

      // Reset pending state
      pendingBatchSymbols = new Set();
      pendingBatchResolvers = [];
      batchDebounceTimer = null;

      // Execute single coalesced batch
      const batchPromise = _executeBatchFetch(allSymbols)
        .then((fullResult) => {
          // Each caller gets their requested subset
          for (const { resolve: res, requested } of resolvers) {
            const subset = {};
            for (const sym of requested) {
              if (fullResult[sym]) subset[sym] = fullResult[sym];
            }
            res(subset);
          }
          // Clean up dedup entries for all callers' batch keys
          inFlightBatches.delete(batchKey);
        })
        .catch((err) => {
          for (const { reject: rej } of resolvers) {
            rej(err);
          }
          inFlightBatches.delete(batchKey);
        });

      inFlightBatches.set(batchKey, batchPromise);
    }, 150);
  });
};

/**
 * Get catalyst overlay for a specific ticker
 * Includes earnings risk, options positioning, macro bias
 * @param {string} symbol - Stock ticker
 */
export const getTickerCatalysts = async (symbol) => {
  const response = await apiClient.get(`${BASE_URL}/ticker/${symbol}/catalysts`);
  return response.data;
};

/**
 * Get earnings risk for a ticker
 * @param {string} symbol - Stock ticker
 */
export const getTickerEarningsRisk = async (symbol) => {
  const response = await apiClient.get(`${BASE_URL}/ticker/${symbol}/earnings-risk`);
  return response.data;
};

/**
 * Get upcoming events for a ticker
 * @param {string} symbol - Stock ticker
 */
export const getTickerEvents = async (symbol) => {
  const response = await apiClient.get(`${BASE_URL}/ticker/${symbol}/events`);
  return response.data;
};

/**
 * Get options positioning for a ticker
 * @param {string} symbol - Stock ticker
 */
export const getTickerOptionsPositioning = async (symbol) => {
  const response = await apiClient.get(`${BASE_URL}/ticker/${symbol}/options-positioning`);
  return response.data;
};

// =============================================================================
// PLACEHOLDER CATALYSTS (Tier 2/3 - Future)
// =============================================================================

/**
 * Get credit stress score (Tier 2)
 */
export const getCreditCatalyst = async () => {
  const response = await apiClient.get(`${BASE_URL}/catalysts/credit`);
  return response.data;
};

/**
 * Get volatility structure score (Tier 2)
 */
export const getVolatilityCatalyst = async () => {
  const response = await apiClient.get(`${BASE_URL}/catalysts/volatility`);
  return response.data;
};

/**
 * Get event density score (Tier 2)
 */
export const getEventDensityCatalyst = async () => {
  const response = await apiClient.get(`${BASE_URL}/catalysts/event-density`);
  return response.data;
};

/**
 * Get cross-asset confirmation score (Tier 3)
 */
export const getCrossAssetCatalyst = async () => {
  const response = await apiClient.get(`${BASE_URL}/catalysts/cross-asset`);
  return response.data;
};

/**
 * Get index-level options positioning (Phase 3)
 */
export const getOptionsPositioningCatalyst = async () => {
  const response = await apiClient.get(`${BASE_URL}/catalysts/options-positioning`);
  return response.data;
};

export default {
  // Summary
  getCatalystSummary,
  // Liquidity
  getLiquidityCatalyst,
  getLiquidityHistory,
  // History
  getCatalystHistory,
  // Ticker
  getTickerMacroOverlay,
  getBatchMacroOverlay,
  clearMacroCache,
  getTickerCatalysts,
  getTickerEarningsRisk,
  getTickerEvents,
  getTickerOptionsPositioning,
  // Placeholders (Tier 2/3)
  getCreditCatalyst,
  getVolatilityCatalyst,
  getEventDensityCatalyst,
  getCrossAssetCatalyst,
  getOptionsPositioningCatalyst,
};
