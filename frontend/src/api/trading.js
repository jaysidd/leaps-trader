/**
 * Trading API client
 * Order execution and position management via Alpaca
 */
import apiClient from './axios';

const API_PREFIX = '/api/v1/trading';

// =============================================================================
// Account & Mode
// =============================================================================

/**
 * Get Alpaca account information
 */
export const getAccount = async () => {
  const response = await apiClient.get(`${API_PREFIX}/account`);
  return response.data;
};

/**
 * Get current trading mode (paper vs live)
 */
export const getTradingMode = async () => {
  const response = await apiClient.get(`${API_PREFIX}/mode`);
  return response.data;
};

/**
 * Set trading mode
 * @param {boolean} paperMode - true for paper trading, false for live
 */
export const setTradingMode = async (paperMode) => {
  const response = await apiClient.put(`${API_PREFIX}/mode`, { paper_mode: paperMode });
  return response.data;
};

// =============================================================================
// Orders
// =============================================================================

/**
 * Place an order
 * @param {Object} orderData - { symbol, qty, side, order_type, limit_price?, time_in_force, signal_id? }
 */
export const placeOrder = async (orderData) => {
  const response = await apiClient.post(`${API_PREFIX}/order`, orderData);
  return response.data;
};

/**
 * Place a market buy order (quick action)
 */
export const quickBuy = async (symbol, qty, signalId = null) => {
  const params = signalId ? { signal_id: signalId } : {};
  const response = await apiClient.post(`${API_PREFIX}/quick-buy/${symbol}`, null, {
    params: { qty, ...params }
  });
  return response.data;
};

/**
 * Place a market sell order (quick action)
 * If qty not specified, sells entire position
 */
export const quickSell = async (symbol, qty = null) => {
  const params = qty ? { qty } : {};
  const response = await apiClient.post(`${API_PREFIX}/quick-sell/${symbol}`, null, { params });
  return response.data;
};

/**
 * List orders
 * @param {Object} params - { status?: 'open'|'closed'|'all', limit?: number, symbol?: string }
 */
export const listOrders = async (params = {}) => {
  const response = await apiClient.get(`${API_PREFIX}/orders`, { params });
  return response.data;
};

/**
 * Get order details
 */
export const getOrder = async (orderId) => {
  const response = await apiClient.get(`${API_PREFIX}/orders/${orderId}`);
  return response.data;
};

/**
 * Cancel an order
 */
export const cancelOrder = async (orderId) => {
  const response = await apiClient.delete(`${API_PREFIX}/orders/${orderId}`);
  return response.data;
};

// =============================================================================
// Positions
// =============================================================================

/**
 * Get all open positions
 */
export const getAllPositions = async () => {
  const response = await apiClient.get(`${API_PREFIX}/positions`);
  return response.data;
};

/**
 * Get position for a specific symbol
 */
export const getPosition = async (symbol) => {
  const response = await apiClient.get(`${API_PREFIX}/positions/${symbol}`);
  return response.data;
};

/**
 * Close a position
 * @param {string} symbol - Stock ticker
 * @param {Object} options - { qty?: number, percentage?: number }
 */
export const closePosition = async (symbol, options = {}) => {
  const response = await apiClient.post(`${API_PREFIX}/positions/${symbol}/close`, options);
  return response.data;
};

/**
 * Close entire position (market sell all)
 */
export const closeFullPosition = async (symbol) => {
  return closePosition(symbol, {});
};

/**
 * Close partial position by shares
 */
export const closePartialByShares = async (symbol, qty) => {
  return closePosition(symbol, { qty });
};

/**
 * Close partial position by percentage
 */
export const closePartialByPercent = async (symbol, percentage) => {
  return closePosition(symbol, { percentage });
};

export default {
  // Account
  getAccount,
  getTradingMode,
  setTradingMode,
  // Orders
  placeOrder,
  quickBuy,
  quickSell,
  listOrders,
  getOrder,
  cancelOrder,
  // Positions
  getAllPositions,
  getPosition,
  closePosition,
  closeFullPosition,
  closePartialByShares,
  closePartialByPercent,
};
