/**
 * Zustand store for Screener state persistence
 *
 * This store keeps the screener state alive across navigation,
 * allowing scans to continue running in the background and
 * preserving results when the user navigates away and returns.
 *
 * @typedef {Object} ScanProgress
 * @property {number} processed - Number of stocks processed so far
 * @property {number} total - Total number of stocks to scan
 * @property {number} passed - Number of stocks that passed screening
 * @property {string} [current_symbol] - Symbol currently being processed
 *
 * @typedef {Object} ScreeningResult
 * @property {string} symbol - Stock ticker symbol
 * @property {string} name - Company name
 * @property {number} score - Composite screening score (0-100)
 * @property {number} [fundamental_score] - Fundamental sub-score
 * @property {number} [technical_score] - Technical sub-score
 * @property {number} [options_score] - Options sub-score
 * @property {number} [momentum_score] - Momentum sub-score
 * @property {number} current_price - Current stock price
 * @property {boolean} passed_all - Whether stock passed all screening stages
 *
 * @typedef {Object} ScreenerState
 * @property {boolean} loading - Whether a scan is currently running
 * @property {ScreeningResult[]} results - Screening results from last scan
 * @property {string|null} error - Error message from last scan
 * @property {object|null} apiStatus - API health status
 * @property {ScanProgress|null} scanProgress - Progress of current scan
 * @property {'streaming'|'batch'|null} scanType - Type of scan running
 * @property {object|null} activePreset - Currently active screening preset
 * @property {Function|null} _abortFn - Internal abort function for SSE
 * @property {string|null} lastScanTime - ISO timestamp of last completed scan
 * @property {string|null} lastScanPreset - Name of last preset used
 */
import { create } from 'zustand';
import { screenerAPI } from '../api/screener';

/** @type {import('zustand').UseBoundStore<import('zustand').StoreApi<ScreenerState>>} */
const useScreenerStore = create((set, get) => ({
  /** @type {boolean} */
  loading: false,
  /** @type {ScreeningResult[]} */
  results: [],
  /** @type {string|null} */
  error: null,
  /** @type {object|null} */
  apiStatus: null,

  /** @type {ScanProgress|null} */
  scanProgress: null,
  /** @type {'streaming'|'batch'|null} */
  scanType: null,
  /** @type {object|null} */
  activePreset: null,

  // SSE connection reference (stored outside Zustand for cleanup)
  /** @type {Function|null} */
  _abortFn: null,

  /** @type {string|null} */
  lastScanTime: null,
  /** @type {string|null} */
  lastScanPreset: null,
  /** @type {object|null} - Per-preset breakdown after scan-all completes */
  scanAllSummary: null,

  // Actions
  setLoading: (loading) => set({ loading }),
  setResults: (results) => set({ results }),
  setError: (error) => set({ error }),
  setApiStatus: (apiStatus) => set({ apiStatus }),
  setScanProgress: (scanProgress) => set({ scanProgress }),
  setScanType: (scanType) => set({ scanType }),
  setActivePreset: (activePreset) => set({ activePreset }),

  // Clear all scan state
  clearScan: () => set({
    loading: false,
    results: [],
    error: null,
    apiStatus: null,
    scanProgress: null,
    scanType: null,
    activePreset: null,
    lastScanTime: null,
    lastScanPreset: null,
    scanAllSummary: null,
  }),

  // Start a streaming scan (preset-based)
  startStreamingScan: (preset) => {
    const state = get();

    // Cancel any existing scan
    if (state._abortFn) {
      state._abortFn();
    }

    console.log(`🚀 [Store] Starting streaming market scan with ${preset} preset...`);

    set({
      loading: true,
      error: null,
      results: [],
      apiStatus: null,
      scanProgress: null,
      scanType: 'streaming',
      activePreset: preset,
      lastScanPreset: preset,
    });

    // Start the streaming scan
    const abortFn = screenerAPI.streamScan(
      preset,
      // onProgress callback
      (progress) => {
        console.log('📊 [Store] Scan progress:', progress);
        set({ scanProgress: progress });
        // Show intermediate candidates as they're found
        if (progress.candidates && progress.candidates.length > 0) {
          set({ results: progress.candidates });
        }
      },
      // onComplete callback
      (result) => {
        console.log('✅ [Store] Scan complete:', result);
        set({
          loading: false,
          scanProgress: null,
          activePreset: null,
          results: result.results || [],
          lastScanTime: new Date().toISOString(),
          apiStatus: result.passed === 0
            ? `Market scan complete: Screened ${result.total} stocks, but none passed all filters.`
            : `✅ Market scan: Found ${result.passed} candidates from ${result.total} stocks`,
          error: result.passed === 0
            ? `Market scan complete: Screened ${result.total} stocks, but none passed all filters. Try a different preset or adjust criteria.`
            : null,
        });
        // Clear the abort function reference
        set({ _abortFn: null });
      },
      // onError callback
      (err) => {
        console.error('[Store] Market scan error:', err);
        set({
          loading: false,
          scanProgress: null,
          activePreset: null,
          error: `Error: ${err.message || 'Market scan failed. Please try again.'}`,
          _abortFn: null,
        });
      }
    );

    // Store the abort function
    set({ _abortFn: abortFn });
  },

  // Start a scan-all-presets streaming scan
  startScanAllPresets: () => {
    const state = get();

    // Cancel any existing scan
    if (state._abortFn) {
      state._abortFn();
    }

    console.log('[Store] Starting Scan All Presets...');
    const scanStartTime = Date.now();

    set({
      loading: true,
      error: null,
      results: [],
      apiStatus: null,
      scanProgress: null,
      scanType: 'streaming',
      activePreset: 'all',
      lastScanPreset: 'All Presets',
      scanAllSummary: null,
    });

    const abortFn = screenerAPI.streamScanAll(
      (progress) => {
        set({ scanProgress: progress });
        if (progress.candidates && progress.candidates.length > 0) {
          set({ results: progress.candidates });
        }
      },
      (result) => {
        console.log('[Store] Scan-all complete:', result);
        const durationSeconds = result.durationSeconds ?? Number(((Date.now() - scanStartTime) / 1000).toFixed(1));
        set({
          loading: false,
          scanProgress: null,
          activePreset: null,
          results: result.results || [],
          lastScanTime: new Date().toISOString(),
          lastScanPreset: 'All Presets',
          apiStatus: result.passed === 0
            ? `Full scan complete: Screened ${result.total} stocks, no matches found.`
            : null,
          error: result.passed === 0
            ? `Full scan complete: Screened ${result.total} stocks, but none matched any preset.`
            : null,
          scanAllSummary: {
            presetSummary: result.presetSummary,
            durationSeconds,
            totalScanned: result.total,
            totalPassed: result.passed,
          },
        });
        set({ _abortFn: null });
      },
      (err) => {
        console.error('[Store] Scan-all error:', err);
        set({
          loading: false,
          scanProgress: null,
          activePreset: null,
          scanAllSummary: null,
          error: `Error: ${err.message || 'Scan all presets failed. Please try again.'}`,
          _abortFn: null,
        });
      }
    );

    set({ _abortFn: abortFn });
  },

  // Start a batch scan (custom criteria)
  startBatchScan: async (criteria) => {
    const state = get();

    // Cancel any existing streaming scan
    if (state._abortFn) {
      state._abortFn();
      set({ _abortFn: null });
    }

    console.log('🌐 [Store] Starting market scan with custom criteria...', criteria);

    set({
      loading: true,
      error: null,
      results: [],
      apiStatus: null,
      scanType: 'batch',
      scanProgress: null,
      activePreset: null,
      lastScanPreset: 'custom',
    });

    try {
      const data = await screenerAPI.marketScan(criteria);
      console.log('✅ [Store] Received data:', data);

      set({
        loading: false,
        results: data.results || [],
        lastScanTime: new Date().toISOString(),
        apiStatus: data.total_passed === 0
          ? `Market scan complete: Screened ${data.total_screened} stocks, but none passed all filters.`
          : `✅ Market scan: Found ${data.total_passed} candidates from ${data.total_screened} stocks`,
        error: data.total_passed === 0
          ? `Market scan complete: Screened ${data.total_screened} stocks, but none passed all filters. Try adjusting your criteria.`
          : null,
      });
    } catch (err) {
      console.error('[Store] Market scan error:', err);
      const errorMessage = err.response?.data?.detail
        || err.message
        || 'Market scan failed. Please try again.';
      set({
        loading: false,
        error: `Error: ${errorMessage}`,
      });
    }
  },

  // Start a manual stock screening
  startManualScreening: async (symbols, topN, criteria) => {
    const state = get();

    // Cancel any existing streaming scan
    if (state._abortFn) {
      state._abortFn();
      set({ _abortFn: null });
    }

    console.log('🔍 [Store] Starting screening with:', { symbols, topN, criteria });

    set({
      loading: true,
      error: null,
      results: [],
      apiStatus: null,
      scanType: 'manual',
      scanProgress: null,
      activePreset: null,
      lastScanPreset: 'manual',
    });

    try {
      const data = await screenerAPI.screenStocks(symbols, topN, criteria);
      console.log('✅ [Store] Received data:', data);

      set({
        loading: false,
        results: data.results || [],
        lastScanTime: new Date().toISOString(),
        error: data.total_passed === 0
          ? 'No stocks passed all screening filters. Try adjusting your criteria or selecting different stocks.'
          : null,
      });
    } catch (err) {
      console.error('[Store] Screening error:', err);
      const errorMessage = err.response?.data?.detail
        || err.message
        || 'Failed to screen stocks. Please try again.';
      set({
        loading: false,
        error: `Error: ${errorMessage}. Check browser console for details.`,
      });
    }
  },

  // Cancel current scan
  cancelScan: () => {
    const state = get();
    if (state._abortFn) {
      state._abortFn();
      set({
        _abortFn: null,
        loading: false,
        scanProgress: null,
        activePreset: null,
        apiStatus: '⏹️ Scan cancelled',
      });
    }
  },

  // Check if there's an active scan
  hasActiveScan: () => {
    const state = get();
    return state.loading && state.scanProgress !== null;
  },

  // Check if there are results to display
  hasResults: () => {
    const state = get();
    return state.results.length > 0;
  },
}));

export default useScreenerStore;
