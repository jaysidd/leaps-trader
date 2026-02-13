/**
 * AI Analysis API client
 */
import apiClient from './axios';

export const aiAPI = {
  /**
   * Check AI service status
   */
  getStatus: async () => {
    const response = await apiClient.get('/api/v1/ai/status');
    return response.data;
  },

  /**
   * Get current market regime
   * @param {boolean} useAI - Use AI for enhanced analysis (slower)
   */
  getMarketRegime: async (useAI = false) => {
    const response = await apiClient.get('/api/v1/ai/regime', {
      params: { use_ai: useAI }
    });
    return response.data;
  },

  /**
   * Get AI insights for a single stock
   * @param {string} symbol - Stock ticker
   * @param {boolean} includeStrategy - Include strategy recommendation
   */
  getStockInsights: async (symbol, includeStrategy = true) => {
    const response = await apiClient.post(`/api/v1/ai/insights/${symbol}`, {
      include_strategy: includeStrategy
    }, {
      timeout: 60000 // 60 seconds for AI analysis
    });
    return response.data;
  },

  /**
   * Get AI summary for multiple stocks
   * @param {string[]} symbols - Array of stock tickers
   */
  getBatchInsights: async (symbols) => {
    const response = await apiClient.post('/api/v1/ai/batch-insights', {
      symbols
    }, {
      timeout: 120000 // 2 minutes for batch analysis
    });
    return response.data;
  },

  /**
   * Get explanation for a stock's score
   * @param {string} symbol - Stock ticker
   */
  explainScore: async (symbol) => {
    const response = await apiClient.get(`/api/v1/ai/explain/${symbol}`, {
      timeout: 30000
    });
    return response.data;
  },

  /**
   * Get strategy recommendation for a stock
   * @param {string} symbol - Stock ticker
   */
  getStrategyRecommendation: async (symbol) => {
    const response = await apiClient.post(`/api/v1/ai/strategy/${symbol}`, {}, {
      timeout: 60000
    });
    return response.data;
  },

  // =========================================================================
  // SIGNAL DEEP ANALYSIS (Trading Prompt Library)
  // =========================================================================

  /**
   * 🧠 AI Deep Analysis for a single trading signal
   * Uses 2-step regime classification + template matching
   * @param {number} signalId - TradingSignal ID
   * @returns {Promise<Object>} Full analysis with conviction, action, checklist, etc.
   */
  analyzeSignal: async (signalId) => {
    const response = await apiClient.post(`/api/v1/ai/signal-analysis/${signalId}`, {}, {
      timeout: 60000 // 60 seconds — regime classification + full analysis
    });
    return response.data;
  },

  /**
   * 🧠 AI Batch Analysis — rank multiple signals and find the best setup
   * @param {number[]} signalIds - Array of TradingSignal IDs (max 5)
   * @returns {Promise<Object>} Ranked signals with best setup and quality assessment
   */
  analyzeSignalBatch: async (signalIds) => {
    const response = await apiClient.post('/api/v1/ai/signal-batch-analysis', {
      signal_ids: signalIds
    }, {
      timeout: 90000 // 90 seconds for batch analysis
    });
    return response.data;
  }
};

export default aiAPI;
