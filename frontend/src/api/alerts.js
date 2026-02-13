/**
 * Alerts API client for webhook alerts
 */
import apiClient from './axios';

const API_PREFIX = '/api/v1/webhooks';

/**
 * Get list of alerts with optional filters
 * @param {Object} params - Query parameters
 * @param {string} params.provider - Filter by provider
 * @param {string} params.status - Filter by status (active, triggered, expired, dismissed)
 * @param {string} params.event_type - Filter by event type (new_setup, trigger)
 * @param {string} params.symbol - Filter by symbol
 * @param {number} params.page - Page number (default: 1)
 * @param {number} params.page_size - Items per page (default: 50)
 * @returns {Promise<Object>} - { alerts, total, page, page_size }
 */
export const getAlerts = async (params = {}) => {
  const response = await apiClient.get(`${API_PREFIX}/alerts`, { params });
  return response.data;
};

/**
 * Get a single alert by ID
 * @param {number} alertId - Alert ID
 * @returns {Promise<Object>} - Alert details
 */
export const getAlert = async (alertId) => {
  const response = await apiClient.get(`${API_PREFIX}/alerts/${alertId}`);
  return response.data;
};

/**
 * Update alert status
 * @param {number} alertId - Alert ID
 * @param {string} status - New status (active, triggered, expired, dismissed)
 * @returns {Promise<Object>} - Update confirmation
 */
export const updateAlertStatus = async (alertId, status) => {
  const response = await apiClient.patch(
    `${API_PREFIX}/alerts/${alertId}/status`,
    null,
    { params: { status } }
  );
  return response.data;
};

/**
 * Delete a single alert
 * @param {number} alertId - Alert ID
 * @returns {Promise<Object>} - Delete confirmation
 */
export const deleteAlert = async (alertId) => {
  const response = await apiClient.delete(`${API_PREFIX}/alerts/${alertId}`);
  return response.data;
};

/**
 * Clear multiple alerts
 * @param {Object} params - Query parameters
 * @param {string} params.provider - Clear only alerts from specific provider
 * @param {string} params.status - Clear only alerts with specific status
 * @returns {Promise<Object>} - { deleted_count, message }
 */
export const clearAlerts = async (params = {}) => {
  const response = await apiClient.delete(`${API_PREFIX}/alerts`, { params });
  return response.data;
};

/**
 * Get list of unique webhook providers
 * @returns {Promise<Object>} - { providers: string[] }
 */
export const getProviders = async () => {
  const response = await apiClient.get(`${API_PREFIX}/providers`);
  return response.data;
};

/**
 * Get webhook statistics
 * @param {string} provider - Optional provider filter
 * @returns {Promise<Object>} - Stats by status and event type
 */
export const getWebhookStats = async (provider = null) => {
  const params = provider ? { provider } : {};
  const response = await apiClient.get(`${API_PREFIX}/stats`, { params });
  return response.data;
};

export default {
  getAlerts,
  getAlert,
  updateAlertStatus,
  deleteAlert,
  clearAlerts,
  getProviders,
  getWebhookStats,
};
