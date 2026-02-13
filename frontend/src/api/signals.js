/**
 * Signals API client
 * Signal queue and trading signals management
 */
import apiClient from './axios';

const API_PREFIX = '/api/v1/signals';

// =============================================================================
// Signal Queue Endpoints
// =============================================================================

/**
 * Add stocks to signal processing queue
 * @param {Object} data - { symbols: string[], timeframe: string, strategy?: string, cap_size?: string }
 */
export const addToQueue = async (data) => {
  const response = await apiClient.post(`${API_PREFIX}/queue/add`, data);
  return response.data;
};

/**
 * Add a single stock to queue with name
 * @param {Object} data - { symbol: string, name?: string, timeframe: string, strategy?: string }
 */
export const addSingleToQueue = async (data) => {
  const response = await apiClient.post(`${API_PREFIX}/queue/add-single`, data);
  return response.data;
};

/**
 * List signal queue items
 * @param {Object} params - { status?: string, timeframe?: string, page?: number, page_size?: number }
 */
export const listQueue = async (params = {}) => {
  const response = await apiClient.get(`${API_PREFIX}/queue`, { params });
  return response.data;
};

/**
 * Get a single queue item
 */
export const getQueueItem = async (itemId) => {
  const response = await apiClient.get(`${API_PREFIX}/queue/${itemId}`);
  return response.data;
};

/**
 * Update a queue item
 */
export const updateQueueItem = async (itemId, updates) => {
  const response = await apiClient.patch(`${API_PREFIX}/queue/${itemId}`, updates);
  return response.data;
};

/**
 * Remove from queue
 */
export const removeFromQueue = async (itemId) => {
  const response = await apiClient.delete(`${API_PREFIX}/queue/${itemId}`);
  return response.data;
};

/**
 * Pause monitoring for a queue item
 */
export const pauseQueueItem = async (itemId) => {
  const response = await apiClient.post(`${API_PREFIX}/queue/${itemId}/pause`);
  return response.data;
};

/**
 * Resume monitoring for a queue item
 */
export const resumeQueueItem = async (itemId) => {
  const response = await apiClient.post(`${API_PREFIX}/queue/${itemId}/resume`);
  return response.data;
};

/**
 * Clear queue items
 */
export const clearQueue = async (params = {}) => {
  const response = await apiClient.delete(`${API_PREFIX}/queue/clear`, { params });
  return response.data;
};

// =============================================================================
// Trading Signals Endpoints
// =============================================================================

/**
 * List trading signals
 * @param {Object} params - { status?: string, direction?: string, timeframe?: string, symbol?: string, is_read?: boolean }
 */
export const listSignals = async (params = {}) => {
  const response = await apiClient.get(`${API_PREFIX}/`, { params });
  return response.data;
};

/**
 * Get unread signal count (for bell icon badge)
 */
export const getUnreadCount = async () => {
  const response = await apiClient.get(`${API_PREFIX}/unread-count`);
  return response.data;
};

/**
 * Get full signal details
 */
export const getSignal = async (signalId) => {
  const response = await apiClient.get(`${API_PREFIX}/${signalId}`);
  return response.data;
};

/**
 * Mark signal as read
 */
export const markSignalRead = async (signalId) => {
  const response = await apiClient.post(`${API_PREFIX}/${signalId}/read`);
  return response.data;
};

/**
 * Mark all signals as read
 */
export const markAllSignalsRead = async () => {
  const response = await apiClient.post(`${API_PREFIX}/mark-all-read`);
  return response.data;
};

/**
 * Invalidate a signal
 */
export const invalidateSignal = async (signalId) => {
  const response = await apiClient.post(`${API_PREFIX}/${signalId}/invalidate`);
  return response.data;
};

/**
 * Delete a signal
 */
export const deleteSignal = async (signalId) => {
  const response = await apiClient.delete(`${API_PREFIX}/${signalId}`);
  return response.data;
};

/**
 * Clear signals
 */
export const clearSignals = async (params = {}) => {
  const response = await apiClient.delete(`${API_PREFIX}/clear`, { params });
  return response.data;
};

/**
 * Get signal processing statistics
 */
export const getStats = async () => {
  const response = await apiClient.get(`${API_PREFIX}/stats/summary`);
  return response.data;
};

export default {
  // Queue
  addToQueue,
  addSingleToQueue,
  listQueue,
  getQueueItem,
  updateQueueItem,
  removeFromQueue,
  pauseQueueItem,
  resumeQueueItem,
  clearQueue,
  // Signals
  listSignals,
  getUnreadCount,
  getSignal,
  markSignalRead,
  markAllSignalsRead,
  invalidateSignal,
  deleteSignal,
  clearSignals,
  getStats,
};
