/**
 * Zustand store for Signal Processing state
 *
 * Manages:
 * - Signal queue (stocks being monitored)
 * - Trading signals (generated buy/sell signals)
 * - Unread count for bell icon
 * - Polling for updates
 */
import { create } from 'zustand';
import signalsAPI from '../api/signals';
import tradingAPI from '../api/trading';

// Notification sound (will be loaded on first play)
let notificationSound = null;

const useSignalsStore = create((set, get) => ({
  // Signal Queue state
  queueItems: [],
  queueLoading: false,
  queueError: null,
  queueStats: { active: 0, paused: 0, total: 0 },

  // Trading Signals state
  signals: [],
  signalsLoading: false,
  signalsError: null,
  unreadCount: 0,

  // Selected signal for detail view
  selectedSignal: null,
  selectedSignalLoading: false,

  // Positions state (for trading)
  positions: [],
  positionsLoading: false,
  tradingMode: { paper_mode: true, mode: 'paper' },

  // Polling state (managed by start/stopPolling with backoff)
  _pollTimer: null,
  _pollErrors: 0,

  // ==========================================================================
  // Signal Queue Actions
  // ==========================================================================

  /**
   * Fetch signal queue items
   */
  fetchQueue: async (params = {}) => {
    set({ queueLoading: true, queueError: null });
    try {
      const data = await signalsAPI.listQueue(params);
      set({
        queueItems: data.items || [],
        queueStats: data.stats || { active: 0, paused: 0, total: 0 },
        queueLoading: false,
      });
      return data;
    } catch (error) {
      console.error('Error fetching queue:', error);
      set({
        queueLoading: false,
        queueError: error.message || 'Failed to fetch queue',
      });
      return null;
    }
  },

  /**
   * Add stocks to signal queue
   */
  addToQueue: async (symbols, timeframe = '5m', strategy = 'auto', capSize = null) => {
    try {
      const result = await signalsAPI.addToQueue({
        symbols,
        timeframe,
        strategy,
        cap_size: capSize,
        source: 'scan',
      });
      // Refresh queue
      await get().fetchQueue();
      return result;
    } catch (error) {
      console.error('Error adding to queue:', error);
      throw error;
    }
  },

  /**
   * Add single stock to queue with name
   */
  addSingleToQueue: async (symbol, name, timeframe = '5m', strategy = 'auto') => {
    try {
      const result = await signalsAPI.addSingleToQueue({
        symbol,
        name,
        timeframe,
        strategy,
      });
      // Refresh queue
      await get().fetchQueue();
      return result;
    } catch (error) {
      console.error('Error adding to queue:', error);
      throw error;
    }
  },

  /**
   * Remove from queue
   */
  removeFromQueue: async (itemId) => {
    try {
      await signalsAPI.removeFromQueue(itemId);
      // Update local state immediately
      set((state) => ({
        queueItems: state.queueItems.filter((item) => item.id !== itemId),
      }));
      return true;
    } catch (error) {
      console.error('Error removing from queue:', error);
      throw error;
    }
  },

  /**
   * Pause queue item
   */
  pauseQueueItem: async (itemId) => {
    try {
      await signalsAPI.pauseQueueItem(itemId);
      // Update local state
      set((state) => ({
        queueItems: state.queueItems.map((item) =>
          item.id === itemId ? { ...item, status: 'paused' } : item
        ),
      }));
      return true;
    } catch (error) {
      console.error('Error pausing queue item:', error);
      throw error;
    }
  },

  /**
   * Resume queue item
   */
  resumeQueueItem: async (itemId) => {
    try {
      await signalsAPI.resumeQueueItem(itemId);
      // Update local state
      set((state) => ({
        queueItems: state.queueItems.map((item) =>
          item.id === itemId ? { ...item, status: 'active' } : item
        ),
      }));
      return true;
    } catch (error) {
      console.error('Error resuming queue item:', error);
      throw error;
    }
  },

  // ==========================================================================
  // Trading Signals Actions
  // ==========================================================================

  /**
   * Fetch trading signals
   */
  fetchSignals: async (params = {}) => {
    set({ signalsLoading: true, signalsError: null });
    try {
      const data = await signalsAPI.listSignals(params);
      set({
        signals: data.signals || [],
        signalsLoading: false,
      });
      return data;
    } catch (error) {
      console.error('Error fetching signals:', error);
      set({
        signalsLoading: false,
        signalsError: error.message || 'Failed to fetch signals',
      });
      return null;
    }
  },

  /**
   * Fetch unread count (for bell icon)
   */
  fetchUnreadCount: async () => {
    try {
      const data = await signalsAPI.getUnreadCount();
      const prevCount = get().unreadCount;
      const newCount = data.unread_count || 0;

      // Play sound if new signals arrived
      if (newCount > prevCount && prevCount >= 0) {
        get().playNotificationSound();
      }

      set({ unreadCount: newCount });
      return newCount;
    } catch (error) {
      console.error('Error fetching unread count:', error);
      return 0;
    }
  },

  /**
   * Get full signal details
   */
  fetchSignalDetails: async (signalId) => {
    set({ selectedSignalLoading: true });
    try {
      const signal = await signalsAPI.getSignal(signalId);
      set({
        selectedSignal: signal,
        selectedSignalLoading: false,
      });
      return signal;
    } catch (error) {
      console.error('Error fetching signal details:', error);
      set({ selectedSignalLoading: false });
      throw error;
    }
  },

  /**
   * Clear selected signal
   */
  clearSelectedSignal: () => {
    set({ selectedSignal: null });
  },

  /**
   * Mark signal as read
   */
  markSignalRead: async (signalId) => {
    try {
      await signalsAPI.markSignalRead(signalId);
      // Update local state
      set((state) => ({
        signals: state.signals.map((s) =>
          s.id === signalId ? { ...s, is_read: true } : s
        ),
        unreadCount: Math.max(0, state.unreadCount - 1),
      }));
      return true;
    } catch (error) {
      console.error('Error marking signal read:', error);
      throw error;
    }
  },

  /**
   * Mark all signals as read
   */
  markAllSignalsRead: async () => {
    try {
      await signalsAPI.markAllSignalsRead();
      set((state) => ({
        signals: state.signals.map((s) => ({ ...s, is_read: true })),
        unreadCount: 0,
      }));
      return true;
    } catch (error) {
      console.error('Error marking all signals read:', error);
      throw error;
    }
  },

  /**
   * Delete a signal
   */
  deleteSignal: async (signalId) => {
    try {
      await signalsAPI.deleteSignal(signalId);
      set((state) => ({
        signals: state.signals.filter((s) => s.id !== signalId),
      }));
      return true;
    } catch (error) {
      console.error('Error deleting signal:', error);
      throw error;
    }
  },

  /**
   * Clear all queue items (bulk delete)
   */
  clearQueue: async () => {
    try {
      const result = await signalsAPI.clearQueue();
      set({ queueItems: [], queueStats: { active: 0, paused: 0, total: 0 } });
      return result;
    } catch (error) {
      console.error('Error clearing queue:', error);
      throw error;
    }
  },

  /**
   * Remove multiple queue items by ID
   */
  removeMultipleFromQueue: async (itemIds) => {
    try {
      await Promise.all(itemIds.map((id) => signalsAPI.removeFromQueue(id)));
      set((state) => ({
        queueItems: state.queueItems.filter((item) => !itemIds.includes(item.id)),
      }));
      // Refresh stats
      await get().fetchQueue();
      return true;
    } catch (error) {
      console.error('Error removing multiple queue items:', error);
      throw error;
    }
  },

  /**
   * Clear all trading signals (bulk delete)
   */
  clearSignals: async () => {
    try {
      const result = await signalsAPI.clearSignals();
      set({ signals: [], unreadCount: 0 });
      return result;
    } catch (error) {
      console.error('Error clearing signals:', error);
      throw error;
    }
  },

  /**
   * Delete multiple signals by ID
   */
  deleteMultipleSignals: async (signalIds) => {
    try {
      await Promise.all(signalIds.map((id) => signalsAPI.deleteSignal(id)));
      set((state) => ({
        signals: state.signals.filter((s) => !signalIds.includes(s.id)),
      }));
      return true;
    } catch (error) {
      console.error('Error deleting multiple signals:', error);
      throw error;
    }
  },

  // ==========================================================================
  // Trading Actions
  // ==========================================================================

  /**
   * Fetch positions
   */
  fetchPositions: async () => {
    set({ positionsLoading: true });
    try {
      const data = await tradingAPI.getAllPositions();
      set({
        positions: data.positions || [],
        positionsLoading: false,
      });
      return data;
    } catch (error) {
      console.error('Error fetching positions:', error);
      set({ positionsLoading: false });
      return null;
    }
  },

  /**
   * Fetch trading mode
   */
  fetchTradingMode: async () => {
    try {
      const data = await tradingAPI.getTradingMode();
      set({ tradingMode: data });
      return data;
    } catch (error) {
      console.error('Error fetching trading mode:', error);
      return null;
    }
  },

  /**
   * Set trading mode
   */
  setTradingMode: async (paperMode) => {
    try {
      const data = await tradingAPI.setTradingMode(paperMode);
      set({ tradingMode: data });
      return data;
    } catch (error) {
      console.error('Error setting trading mode:', error);
      throw error;
    }
  },

  // ==========================================================================
  // Notifications
  // ==========================================================================

  /**
   * Play notification sound
   */
  playNotificationSound: () => {
    try {
      if (!notificationSound) {
        notificationSound = new Audio('/sounds/signal-alert.mp3');
        notificationSound.volume = 0.5;
      }
      notificationSound.currentTime = 0;
      notificationSound.play().catch((e) => {
        console.log('Could not play notification sound:', e.message);
      });
    } catch (error) {
      console.log('Error playing sound:', error);
    }
  },

  // ==========================================================================
  // Polling
  // ==========================================================================

  // Backoff state for resilient polling
  _pollTimer: null,
  _pollErrors: 0,

  /**
   * Start polling for unread count and new signals (with exponential backoff)
   */
  startPolling: (baseIntervalMs = 30000) => {
    const { _pollTimer } = get();
    if (_pollTimer) return;

    console.log('Starting signal polling...');

    const schedulePoll = () => {
      const { _pollErrors } = get();
      // Exponential backoff: base * 2^errors, capped at 2 minutes
      const delay = Math.min(baseIntervalMs * Math.pow(2, _pollErrors), 120000);
      const timer = setTimeout(async () => {
        if (document.hidden) {
          schedulePoll();
          return;
        }
        try {
          await get().fetchUnreadCount();
          set({ _pollErrors: 0 });
        } catch {
          set({ _pollErrors: get()._pollErrors + 1 });
        }
        if (get()._pollTimer) schedulePoll();
      }, delay);
      set({ _pollTimer: timer });
    };

    // Initial fetch
    get().fetchUnreadCount().then(() => {
      set({ _pollErrors: 0 });
    }).catch(() => {
      set({ _pollErrors: 1 });
    }).finally(() => {
      schedulePoll();
    });
  },

  /**
   * Stop polling
   */
  stopPolling: () => {
    const { _pollTimer } = get();
    if (_pollTimer) {
      console.log('Stopping signal polling');
      clearTimeout(_pollTimer);
      set({ _pollTimer: null, _pollErrors: 0 });
    }
  },

  // ==========================================================================
  // Helpers
  // ==========================================================================

  /**
   * Check if there are unread signals
   */
  hasUnreadSignals: () => {
    return get().unreadCount > 0;
  },

  /**
   * Get position for a symbol
   */
  getPositionForSymbol: (symbol) => {
    return get().positions.find((p) => p.symbol === symbol.toUpperCase());
  },
}));

export default useSignalsStore;
