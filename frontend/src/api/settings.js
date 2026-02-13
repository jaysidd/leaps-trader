/**
 * Settings API client
 */
import apiClient from './axios';

export const settingsAPI = {
  /**
   * Get all settings grouped by category
   * @returns {Promise} - Settings object grouped by category
   */
  getAllSettings: async () => {
    const response = await apiClient.get('/api/v1/settings');
    return response.data;
  },

  /**
   * Get complete settings summary including API key status
   * @returns {Promise} - Full settings summary
   */
  getSettingsSummary: async () => {
    const response = await apiClient.get('/api/v1/settings/summary');
    return response.data;
  },

  /**
   * Get settings for a specific category
   * @param {string} category - Category name (screening, rate_limit, cache, feature, ui)
   * @returns {Promise} - Settings for the category
   */
  getSettingsByCategory: async (category) => {
    const response = await apiClient.get(`/api/v1/settings/category/${category}`);
    return response.data;
  },

  /**
   * Get a single setting value
   * @param {string} key - Setting key (e.g., "screening.market_cap_min")
   * @returns {Promise} - Setting value
   */
  getSetting: async (key) => {
    const response = await apiClient.get(`/api/v1/settings/key/${key}`);
    return response.data;
  },

  /**
   * Update a single setting
   * @param {string} key - Setting key
   * @param {any} value - New value
   * @returns {Promise} - Update result
   */
  updateSetting: async (key, value) => {
    const response = await apiClient.put(`/api/v1/settings/key/${key}`, value, {
      headers: { 'Content-Type': 'application/json' }
    });
    return response.data;
  },

  /**
   * Update multiple settings at once
   * @param {Object} updates - Object with key-value pairs to update
   * @returns {Promise} - Update results
   */
  updateSettingsBatch: async (updates) => {
    const response = await apiClient.put('/api/v1/settings', { updates });
    return response.data;
  },

  /**
   * Get API key configuration status (not the actual keys)
   * @returns {Promise} - API key status for all services
   */
  getApiKeyStatus: async () => {
    const response = await apiClient.get('/api/v1/settings/api-keys');
    return response.data;
  },

  /**
   * Update an API key
   * @param {string} serviceName - Service name (e.g., "finviz", "anthropic")
   * @param {string} apiKey - The new API key value
   * @returns {Promise} - Update result
   */
  updateApiKey: async (serviceName, apiKey) => {
    const response = await apiClient.put('/api/v1/settings/api-keys', {
      service_name: serviceName,
      api_key: apiKey
    });
    return response.data;
  },

  /**
   * Validate an API key
   * @param {string} serviceName - Service name to validate
   * @returns {Promise} - Validation result
   */
  validateApiKey: async (serviceName) => {
    const response = await apiClient.post(`/api/v1/settings/api-keys/${serviceName}/validate`);
    return response.data;
  },

  /**
   * Seed default settings (reset to defaults)
   * @returns {Promise} - Seed result
   */
  seedSettings: async () => {
    const response = await apiClient.post('/api/v1/settings/seed');
    return response.data;
  },
};
