/**
 * Saved Scans API client
 * Handles persisting and retrieving scan results
 */
import apiClient from './axios';

const API_PREFIX = '/api/v1/saved-scans';

export const savedScansAPI = {
  /**
   * Get all saved scan categories with metadata
   */
  getCategories: async () => {
    const response = await apiClient.get(`${API_PREFIX}/categories`);
    return response.data;
  },

  /**
   * Get results for a specific scan type
   * @param {string} scanType - The preset name
   */
  getResults: async (scanType) => {
    const response = await apiClient.get(`${API_PREFIX}/results/${scanType}`);
    return response.data;
  },

  /**
   * Save scan results for a scan type
   * @param {string} scanType - The preset name
   * @param {string} displayName - User-friendly name
   * @param {Array} results - Stock results from screener
   */
  saveResults: async (scanType, displayName, results) => {
    const response = await apiClient.post(`${API_PREFIX}/save`, {
      scan_type: scanType,
      display_name: displayName,
      results: results
    });
    return response.data;
  },

  /**
   * Delete all results for a scan type
   * @param {string} scanType - The preset name
   */
  deleteCategory: async (scanType) => {
    const response = await apiClient.delete(`${API_PREFIX}/category/${scanType}`);
    return response.data;
  },

  /**
   * Delete a specific stock from a scan
   * @param {string} scanType - The preset name
   * @param {string} symbol - Stock symbol
   */
  deleteStock: async (scanType, symbol) => {
    const response = await apiClient.delete(`${API_PREFIX}/stock/${scanType}/${symbol}`);
    return response.data;
  },

  /**
   * Delete multiple stocks from a scan in one operation
   * @param {string} scanType - The preset name
   * @param {string[]} symbols - Stock symbols to delete
   */
  deleteSelectedStocks: async (scanType, symbols) => {
    const response = await apiClient.post(`${API_PREFIX}/delete-stocks`, {
      scan_type: scanType,
      symbols,
    });
    return response.data;
  },

  /**
   * Clear all saved scans
   */
  clearAll: async () => {
    const response = await apiClient.delete(`${API_PREFIX}/all`);
    return response.data;
  },

  /**
   * Check if a scan type has saved results
   * @param {string} scanType - The preset name
   */
  checkScan: async (scanType) => {
    const response = await apiClient.get(`${API_PREFIX}/check/${scanType}`);
    return response.data;
  },

  /**
   * Check all scans for saved status
   * Returns map of scan types to their saved status
   */
  checkAllScans: async () => {
    const response = await apiClient.get(`${API_PREFIX}/check-all`);
    return response.data;
  }
};

export default savedScansAPI;
