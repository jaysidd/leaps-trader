/**
 * Backtest Store — Zustand store for backtesting state
 * Handles: run backtest, poll results, list history
 */
import { create } from 'zustand';
import backtestAPI from '../api/backtesting';

const useBacktestStore = create((set, get) => ({
  // State
  backtests: [],
  currentResult: null,
  running: false,
  error: null,
  _pollInterval: null,

  // ─── Run Backtest ──────────────────────────────────────────────
  runBacktest: async (config) => {
    set({ running: true, error: null, currentResult: null });
    try {
      const data = await backtestAPI.runBacktest(config);
      // Set initial pending result
      set({ currentResult: { id: data.id, status: 'pending' } });
      // Start polling for results
      get().startPolling(data.id);
      return data.id;
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message;
      set({ running: false, error: errorMsg });
      throw err;
    }
  },

  // ─── Polling ───────────────────────────────────────────────────
  startPolling: (backtestId) => {
    const { _pollInterval } = get();
    if (_pollInterval) clearInterval(_pollInterval);

    const poll = async () => {
      if (document.hidden) return; // Skip polling when tab is hidden
      try {
        const result = await backtestAPI.getResults(backtestId);
        set({ currentResult: result });
        if (result.status === 'completed' || result.status === 'failed') {
          get().stopPolling();
          set({ running: false });
          if (result.status === 'failed') {
            set({ error: result.error_message || 'Backtest failed' });
          }
          // Refresh history
          get().fetchBacktests();
        }
      } catch (err) {
        // Keep polling on transient errors
      }
    };

    poll(); // Immediate first poll
    const interval = setInterval(poll, 2000); // Poll every 2s
    set({ _pollInterval: interval });
  },

  stopPolling: () => {
    const { _pollInterval } = get();
    if (_pollInterval) {
      clearInterval(_pollInterval);
      set({ _pollInterval: null });
    }
  },

  // ─── History ───────────────────────────────────────────────────
  fetchBacktests: async (params = {}) => {
    try {
      const data = await backtestAPI.listBacktests(params);
      set({ backtests: data.backtests || [] });
      return data;
    } catch (err) {
      return { backtests: [] };
    }
  },

  // ─── Load Specific Result ──────────────────────────────────────
  loadResult: async (id) => {
    try {
      const result = await backtestAPI.getResults(id);
      set({ currentResult: result, error: null });
      return result;
    } catch (err) {
      set({ error: err.response?.data?.detail || err.message });
      return null;
    }
  },

  // ─── Delete ────────────────────────────────────────────────────
  deleteBacktest: async (id) => {
    try {
      await backtestAPI.deleteBacktest(id);
      // Remove from list
      set(state => ({
        backtests: state.backtests.filter(b => b.id !== id),
        currentResult: state.currentResult?.id === id ? null : state.currentResult,
      }));
    } catch (err) {
      set({ error: err.response?.data?.detail || err.message });
      throw err;
    }
  },

  // ─── Clear ─────────────────────────────────────────────────────
  clearError: () => set({ error: null }),
  clearResult: () => set({ currentResult: null }),
}));

export default useBacktestStore;
