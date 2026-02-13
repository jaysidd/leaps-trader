/**
 * Autopilot API client
 * Status, activity feed, market state, and position calculator
 */
import apiClient from './axios';

const AUTOPILOT_PREFIX = '/api/v1/autopilot';

export const autopilotApi = {
  /**
   * Get current autopilot status (mode, scan state, market condition)
   * @returns {Promise} - Autopilot status object
   */
  getStatus: async () => {
    const response = await apiClient.get(`${AUTOPILOT_PREFIX}/status`);
    return response.data;
  },

  /**
   * Get recent autopilot activity feed
   * @param {number} hours - Number of hours to look back (default 24)
   * @param {number} limit - Max events to return (default 50)
   * @returns {Promise} - Array of activity events
   */
  getActivity: async (hours = 24, limit = 50) => {
    const response = await apiClient.get(`${AUTOPILOT_PREFIX}/activity`, {
      params: { hours, limit },
    });
    return response.data;
  },

  /**
   * Get current market state (MRI, regime, fear & greed)
   * @returns {Promise} - Market state object
   */
  getMarketState: async () => {
    const response = await apiClient.get(`${AUTOPILOT_PREFIX}/market-state`);
    return response.data;
  },

  /**
   * Calculate position size based on risk parameters
   * @param {Object} data - Position sizing inputs
   * @returns {Promise} - Calculated position details
   */
  calculatePosition: async (data) => {
    const response = await apiClient.post(`${AUTOPILOT_PREFIX}/calculate-position`, data);
    return response.data;
  },
};

export default autopilotApi;
