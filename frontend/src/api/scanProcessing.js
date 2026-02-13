/**
 * Scan Processing API client
 * Handles the StrategySelector pipeline: process scans, AI review, queue stocks
 */
import apiClient from './axios';

const API_PREFIX = '/api/v1/scan-processing';

export const scanProcessingAPI = {
  /**
   * Process a saved scan through the StrategySelector pipeline
   * @param {string} scanType - The saved scan preset name
   * @returns {Promise<{auto_queued, review_needed, skipped, stats}>}
   */
  processScan: async (scanType) => {
    const response = await apiClient.post(`${API_PREFIX}/process`, {
      scan_type: scanType,
    });
    return response.data;
  },

  /**
   * Send MEDIUM-confidence stocks to Claude for AI review
   * @param {Array<{symbol, concerns, metrics, suggested_timeframes}>} stocks
   * @returns {Promise<{analysis, model_used, stock_count}>}
   */
  aiReviewBatch: async (stocks) => {
    const response = await apiClient.post(`${API_PREFIX}/ai-review`, {
      stocks,
    });
    return response.data;
  },

  /**
   * Queue AI-reviewed stocks to signal processing
   * @param {Array<{symbol, timeframes, strategy, cap_size, name, confidence_level, reasoning}>} stocks
   * @returns {Promise<{added, added_count, skipped, skipped_count}>}
   */
  queueReviewed: async (stocks) => {
    const response = await apiClient.post(`${API_PREFIX}/queue-reviewed`, {
      stocks,
    });
    return response.data;
  },
};

export default scanProcessingAPI;
