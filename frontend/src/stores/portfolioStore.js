/**
 * Zustand store for Portfolio state
 *
 * Manages:
 * - Broker connections (Robinhood, Alpaca, etc.)
 * - Portfolio summary and positions
 * - Portfolio value history
 * - Recent orders and dividends
 */
import { create } from 'zustand';
import portfolioAPI from '../api/portfolio';

const usePortfolioStore = create((set, get) => ({
  // Broker Status
  brokersStatus: [],
  brokersLoading: false,

  // Broker Connections
  connections: [],
  connectionsLoading: false,
  connectionsError: null,

  // Connection flow state
  connectingBroker: null,
  connectionPending: null, // For MFA flow
  connectionError: null,

  // Portfolio Summary
  summary: null,
  summaryLoading: false,
  summaryError: null,

  // Positions
  positions: [],
  positionsLoading: false,
  positionsError: null,

  // Portfolio History (for charts)
  history: [],
  historyLoading: false,

  // Recent Orders
  orders: [],
  ordersLoading: false,

  // Dividends
  dividends: [],
  dividendsLoading: false,

  // Refresh interval
  _refreshInterval: null,

  // ==========================================================================
  // Broker Status Actions
  // ==========================================================================

  /**
   * Fetch status of all supported brokers
   */
  fetchBrokersStatus: async () => {
    set({ brokersLoading: true });
    try {
      const data = await portfolioAPI.getBrokersStatus();
      set({
        brokersStatus: data.brokers || [],
        brokersLoading: false,
      });
      return data.brokers;
    } catch (error) {
      console.error('Error fetching brokers status:', error);
      set({ brokersLoading: false });
      return [];
    }
  },

  // ==========================================================================
  // Connection Actions
  // ==========================================================================

  /**
   * Fetch all broker connections
   */
  fetchConnections: async () => {
    set({ connectionsLoading: true, connectionsError: null });
    try {
      const data = await portfolioAPI.getConnections();
      set({
        connections: data.connections || [],
        connectionsLoading: false,
      });
      return data.connections;
    } catch (error) {
      console.error('Error fetching connections:', error);
      set({
        connectionsLoading: false,
        connectionsError: error.message || 'Failed to fetch connections',
      });
      return [];
    }
  },

  /**
   * Connect to a broker
   */
  connectBroker: async (brokerType, username, password, mfaCode = null, accountName = null) => {
    set({
      connectingBroker: brokerType,
      connectionError: null,
      connectionPending: null,
    });
    try {
      const result = await portfolioAPI.connectBroker(
        brokerType,
        username,
        password,
        mfaCode,
        null, // deviceToken
        accountName
      );

      if (result.requires_mfa) {
        set({
          connectionPending: result.connection,
          connectingBroker: null,
        });
        return { success: false, requires_mfa: true, connection: result.connection };
      }

      if (result.success) {
        // Refresh connections and summary
        await get().fetchConnections();
        await get().fetchSummary();
        await get().fetchPositions();

        set({
          connectingBroker: null,
          connectionPending: null,
        });
        return { success: true, connection: result.connection };
      }

      set({
        connectionError: result.message || 'Connection failed',
        connectingBroker: null,
      });
      return { success: false, error: result.message };

    } catch (error) {
      const errorMsg = error.response?.data?.detail || error.message || 'Connection failed';
      set({
        connectionError: errorMsg,
        connectingBroker: null,
      });
      return { success: false, error: errorMsg };
    }
  },

  /**
   * Submit MFA code
   */
  submitMFA: async (connectionId, mfaCode) => {
    set({ connectingBroker: 'mfa' });
    try {
      const result = await portfolioAPI.submitMFA(connectionId, mfaCode);

      if (result.success) {
        await get().fetchConnections();
        await get().fetchSummary();
        await get().fetchPositions();

        set({
          connectingBroker: null,
          connectionPending: null,
        });
        return { success: true };
      }

      set({
        connectionError: result.message || 'MFA verification failed',
        connectingBroker: null,
      });
      return { success: false, error: result.message };

    } catch (error) {
      const errorMsg = error.response?.data?.detail || error.message || 'MFA verification failed';
      set({
        connectionError: errorMsg,
        connectingBroker: null,
      });
      return { success: false, error: errorMsg };
    }
  },

  /**
   * Disconnect a broker
   */
  disconnectBroker: async (connectionId) => {
    try {
      await portfolioAPI.disconnectBroker(connectionId);

      // Update local state
      set((state) => ({
        connections: state.connections.filter((c) => c.id !== connectionId),
      }));

      // Refresh summary
      await get().fetchSummary();
      await get().fetchPositions();

      return { success: true };
    } catch (error) {
      console.error('Error disconnecting broker:', error);
      return { success: false, error: error.message };
    }
  },

  /**
   * Sync a broker connection
   */
  syncConnection: async (connectionId) => {
    try {
      const result = await portfolioAPI.syncConnection(connectionId);

      // Refresh data
      await get().fetchConnections();
      await get().fetchSummary();
      await get().fetchPositions();

      return result;
    } catch (error) {
      console.error('Error syncing connection:', error);
      throw error;
    }
  },

  /**
   * Clear connection error
   */
  clearConnectionError: () => {
    set({ connectionError: null });
  },

  /**
   * Cancel pending MFA
   */
  cancelMFA: () => {
    set({
      connectionPending: null,
      connectionError: null,
    });
  },

  // ==========================================================================
  // Portfolio Data Actions
  // ==========================================================================

  /**
   * Fetch portfolio summary
   */
  fetchSummary: async () => {
    set({ summaryLoading: true, summaryError: null });
    try {
      const data = await portfolioAPI.getSummary();
      set({
        summary: data,
        summaryLoading: false,
      });
      return data;
    } catch (error) {
      console.error('Error fetching summary:', error);
      set({
        summaryLoading: false,
        summaryError: error.message || 'Failed to fetch summary',
      });
      return null;
    }
  },

  /**
   * Fetch positions
   */
  fetchPositions: async (brokerId = null, assetType = null) => {
    set({ positionsLoading: true, positionsError: null });
    try {
      const data = await portfolioAPI.getPositions(brokerId, assetType);
      set({
        positions: data.positions || [],
        positionsLoading: false,
      });
      return data;
    } catch (error) {
      console.error('Error fetching positions:', error);
      set({
        positionsLoading: false,
        positionsError: error.message || 'Failed to fetch positions',
      });
      return null;
    }
  },

  /**
   * Fetch portfolio history
   */
  fetchHistory: async (span = 'month', brokerId = null) => {
    set({ historyLoading: true });
    try {
      const data = await portfolioAPI.getHistory(span, brokerId);
      set({
        history: data.history || [],
        historyLoading: false,
      });
      return data;
    } catch (error) {
      console.error('Error fetching history:', error);
      set({ historyLoading: false });
      return null;
    }
  },

  /**
   * Fetch recent orders
   */
  fetchOrders: async (limit = 50) => {
    set({ ordersLoading: true });
    try {
      const data = await portfolioAPI.getRecentOrders(limit);
      set({
        orders: data.orders || [],
        ordersLoading: false,
      });
      return data;
    } catch (error) {
      console.error('Error fetching orders:', error);
      set({ ordersLoading: false });
      return null;
    }
  },

  /**
   * Fetch dividends
   */
  fetchDividends: async () => {
    set({ dividendsLoading: true });
    try {
      const data = await portfolioAPI.getDividends();
      set({
        dividends: data.dividends || [],
        dividendsLoading: false,
      });
      return data;
    } catch (error) {
      console.error('Error fetching dividends:', error);
      set({ dividendsLoading: false });
      return null;
    }
  },

  // ==========================================================================
  // Refresh / Polling
  // ==========================================================================

  /**
   * Refresh all portfolio data
   */
  refreshAll: async () => {
    await Promise.all([
      get().fetchSummary(),
      get().fetchPositions(),
      get().fetchConnections(),
    ]);
  },

  /**
   * Refresh prices via Alpaca live feed, then re-read positions/summary
   */
  refreshPrices: async () => {
    try {
      await portfolioAPI.refreshPrices();
      // Re-read the now-updated DB rows
      await Promise.all([
        get().fetchSummary(),
        get().fetchPositions(),
      ]);
    } catch (error) {
      console.error('Error refreshing live prices:', error);
    }
  },

  /**
   * Start auto-refresh
   */
  startAutoRefresh: (intervalMs = 30000) => {
    const state = get();

    if (state._refreshInterval) {
      return;
    }

    console.log('📊 Starting portfolio auto-refresh (Alpaca live prices)...');

    // Initial fetch
    get().refreshAll();

    // Refresh prices from Alpaca every interval (default 30s)
    const intervalId = setInterval(() => {
      get().refreshPrices();
    }, intervalMs);

    set({ _refreshInterval: intervalId });
  },

  /**
   * Stop auto-refresh
   */
  stopAutoRefresh: () => {
    const state = get();
    if (state._refreshInterval) {
      console.log('🛑 Stopping portfolio auto-refresh');
      clearInterval(state._refreshInterval);
      set({ _refreshInterval: null });
    }
  },

  // ==========================================================================
  // Helpers
  // ==========================================================================

  /**
   * Check if any broker is connected
   */
  hasConnectedBroker: () => {
    return get().connections.some((c) => c.status === 'connected');
  },

  /**
   * Get connected brokers
   */
  getConnectedBrokers: () => {
    return get().connections.filter((c) => c.status === 'connected');
  },

  /**
   * Get total portfolio value
   */
  getTotalValue: () => {
    return get().summary?.total_portfolio_value || 0;
  },

  /**
   * Get position by symbol
   */
  getPositionBySymbol: (symbol) => {
    return get().positions.find((p) => p.symbol === symbol.toUpperCase());
  },

  /**
   * Get positions grouped by asset type
   */
  getPositionsByType: () => {
    const positions = get().positions;
    return {
      stocks: positions.filter((p) => p.asset_type === 'stock'),
      options: positions.filter((p) => p.asset_type === 'option'),
      crypto: positions.filter((p) => p.asset_type === 'crypto'),
    };
  },
}));

export default usePortfolioStore;
