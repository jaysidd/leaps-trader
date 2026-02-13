/**
 * Bot Store — Zustand store for trading bot state
 * Handles: config, status, active trades, performance, polling
 */
import { create } from 'zustand';
import botAPI from '../api/bot';

const useBotStore = create((set, get) => ({
  // State
  config: null,
  status: null,
  activeTrades: [],
  pendingApprovals: [],
  todayPerformance: null,
  loading: false,
  error: null,

  // Polling (managed by startPolling/stopPolling)
  _pollTimer: null,
  _consecutiveErrors: 0,

  // ─── Config ─────────────────────────────────────────────────
  fetchConfig: async () => {
    try {
      const config = await botAPI.getConfig();
      set({ config });
      return config;
    } catch (err) {
      set({ error: err.message });
      return null;
    }
  },

  updateConfig: async (updates) => {
    try {
      const config = await botAPI.updateConfig(updates);
      set({ config, error: null });
      return config;
    } catch (err) {
      set({ error: err.response?.data?.detail || err.message });
      throw err;
    }
  },

  // ─── Status ─────────────────────────────────────────────────
  fetchStatus: async () => {
    try {
      const status = await botAPI.getStatus();
      set({ status, error: null });
      return status;
    } catch (err) {
      set({ error: err.message });
      return null;
    }
  },

  // ─── Bot Control ────────────────────────────────────────────
  startBot: async () => {
    set({ loading: true });
    try {
      const result = await botAPI.startBot();
      await get().fetchStatus();
      set({ loading: false, error: null });
      return result;
    } catch (err) {
      set({ loading: false, error: err.response?.data?.detail || err.message });
      throw err;
    }
  },

  stopBot: async () => {
    set({ loading: true });
    try {
      const result = await botAPI.stopBot();
      await get().fetchStatus();
      set({ loading: false, error: null });
      return result;
    } catch (err) {
      set({ loading: false, error: err.response?.data?.detail || err.message });
      throw err;
    }
  },

  pauseBot: async () => {
    try {
      const result = await botAPI.pauseBot();
      await get().fetchStatus();
      return result;
    } catch (err) {
      set({ error: err.response?.data?.detail || err.message });
      throw err;
    }
  },

  resumeBot: async () => {
    try {
      const result = await botAPI.resumeBot();
      await get().fetchStatus();
      return result;
    } catch (err) {
      set({ error: err.response?.data?.detail || err.message });
      throw err;
    }
  },

  emergencyStop: async (closePositions = true) => {
    set({ loading: true });
    try {
      const result = await botAPI.emergencyStop(closePositions);
      await get().fetchStatus();
      set({ loading: false, error: null });
      return result;
    } catch (err) {
      set({ loading: false, error: err.response?.data?.detail || err.message });
      throw err;
    }
  },

  // ─── Active Trades ──────────────────────────────────────────
  fetchActiveTrades: async () => {
    try {
      const trades = await botAPI.getActiveTrades();
      set({ activeTrades: trades });
      return trades;
    } catch (err) {
      return [];
    }
  },

  // ─── Pending Approvals ──────────────────────────────────────
  fetchPendingApprovals: async () => {
    try {
      const approvals = await botAPI.getPendingApprovals();
      set({ pendingApprovals: approvals });
      return approvals;
    } catch (err) {
      return [];
    }
  },

  approveSignal: async (signalId) => {
    try {
      const result = await botAPI.approveSignal(signalId);
      await get().fetchPendingApprovals();
      await get().fetchActiveTrades();
      return result;
    } catch (err) {
      set({ error: err.response?.data?.detail || err.message });
      throw err;
    }
  },

  rejectSignal: async (signalId) => {
    try {
      await botAPI.rejectSignal(signalId);
      await get().fetchPendingApprovals();
    } catch (err) {
      set({ error: err.response?.data?.detail || err.message });
      throw err;
    }
  },

  // ─── Manual Signal Execution ───────────────────────────────
  previewSignal: async (signalId) => {
    try {
      const result = await botAPI.previewSignal(signalId);
      return result;
    } catch (err) {
      return { error: err.response?.data?.detail || err.message };
    }
  },

  executeSignal: async (signalId) => {
    set({ loading: true });
    try {
      const result = await botAPI.executeSignal(signalId);
      if (result.error) {
        set({ loading: false, error: result.error });
        return { error: result.error };
      }
      await get().fetchActiveTrades();
      set({ loading: false, error: null });
      return result;
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message;
      set({ loading: false, error: errorMsg });
      return { error: errorMsg };
    }
  },

  // ─── Today Performance ──────────────────────────────────────
  fetchTodayPerformance: async () => {
    try {
      const perf = await botAPI.getTodayPerformance();
      set({ todayPerformance: perf });
      return perf;
    } catch (err) {
      return null;
    }
  },

  // ─── Polling (with exponential backoff on errors) ───────────
  _pollTimer: null,
  _consecutiveErrors: 0,

  startPolling: (baseIntervalMs = 10000) => {
    const { _pollTimer } = get();
    if (_pollTimer) return;

    const schedulePoll = () => {
      const { _consecutiveErrors } = get();
      // Backoff: base * 2^errors, capped at 60s
      const delay = Math.min(
        baseIntervalMs * Math.pow(2, _consecutiveErrors),
        60000
      );
      const timer = setTimeout(async () => {
        if (document.hidden) {
          // Tab hidden — schedule next poll without fetching
          schedulePoll();
          return;
        }
        try {
          await get().fetchStatus();
          await get().fetchActiveTrades();
          set({ _consecutiveErrors: 0 }); // Reset on success
        } catch {
          set({ _consecutiveErrors: get()._consecutiveErrors + 1 });
        }
        // Schedule next poll
        if (get()._pollTimer) schedulePoll();
      }, delay);
      set({ _pollTimer: timer });
    };

    // Immediate first fetch
    (async () => {
      try {
        await get().fetchStatus();
        await get().fetchActiveTrades();
        set({ _consecutiveErrors: 0 });
      } catch {
        set({ _consecutiveErrors: 1 });
      }
      schedulePoll();
    })();
  },

  stopPolling: () => {
    const { _pollTimer } = get();
    if (_pollTimer) {
      clearTimeout(_pollTimer);
      set({ _pollTimer: null, _consecutiveErrors: 0 });
    }
  },

  // ─── Clear Error ────────────────────────────────────────────
  clearError: () => set({ error: null }),
}));

export default useBotStore;
