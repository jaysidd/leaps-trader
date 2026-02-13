/**
 * Command Center API client
 * Provides access to market data, prediction markets, news, and AI copilot
 */
import apiClient from './axios';

const BASE_URL = '/api/v1/command-center';

// =============================================================================
// DASHBOARD
// =============================================================================

/**
 * Get full dashboard data in a single request
 * Optimized for initial page load
 */
export const getDashboard = async () => {
  const response = await apiClient.get(`${BASE_URL}/dashboard`);
  return response.data;
};

// =============================================================================
// MARKET DATA
// =============================================================================

/**
 * Get complete market summary
 * Includes indices, volatility, Fear & Greed, and sectors
 */
export const getMarketSummary = async () => {
  const response = await apiClient.get(`${BASE_URL}/market/summary`);
  return response.data;
};

/**
 * Get market indices (SPY, QQQ, DIA, IWM)
 */
export const getMarketIndices = async () => {
  const response = await apiClient.get(`${BASE_URL}/market/indices`);
  return response.data;
};

/**
 * Get volatility metrics (VIX, VIX9D)
 */
export const getVolatility = async () => {
  const response = await apiClient.get(`${BASE_URL}/market/volatility`);
  return response.data;
};

/**
 * Get CNN Fear & Greed Index
 */
export const getFearGreed = async () => {
  const response = await apiClient.get(`${BASE_URL}/market/fear-greed`);
  return response.data;
};

/**
 * Get sector ETF performance
 */
export const getSectorPerformance = async () => {
  const response = await apiClient.get(`${BASE_URL}/market/sectors`);
  return response.data;
};

// =============================================================================
// POLYMARKET
// =============================================================================

/**
 * Get Polymarket dashboard summary
 */
export const getPolymarketDashboard = async () => {
  const response = await apiClient.get(`${BASE_URL}/polymarket/dashboard`);
  return response.data;
};

/**
 * Get trading-relevant prediction markets
 * @param {number} limit - Number of markets to return
 */
export const getTradingMarkets = async (limit = 20) => {
  const response = await apiClient.get(`${BASE_URL}/polymarket/markets`, {
    params: { limit },
  });
  return response.data;
};

/**
 * Get markets with significant odds changes
 * @param {number} threshold - Minimum change percentage
 */
export const getSignificantChanges = async (threshold = 5.0) => {
  const response = await apiClient.get(`${BASE_URL}/polymarket/changes`, {
    params: { threshold },
  });
  return response.data;
};

/**
 * Get curated key markets by category
 */
export const getKeyMarkets = async () => {
  const response = await apiClient.get(`${BASE_URL}/polymarket/key-markets`);
  return response.data;
};

// =============================================================================
// NEWS FEED
// =============================================================================

/**
 * Get general market news
 * @param {number} limit - Number of news items
 */
export const getMarketNews = async (limit = 20) => {
  const response = await apiClient.get(`${BASE_URL}/news/market`, {
    params: { limit },
  });
  return response.data;
};

/**
 * Get news for a specific symbol
 * @param {string} symbol - Stock ticker
 * @param {number} limit - Number of news items
 */
export const getCompanyNews = async (symbol, limit = 10) => {
  const response = await apiClient.get(`${BASE_URL}/news/company/${symbol}`, {
    params: { limit },
  });
  return response.data;
};

/**
 * Get economic calendar
 * @param {number} daysAhead - Days to look ahead
 */
export const getEconomicCalendar = async (daysAhead = 7) => {
  const response = await apiClient.get(`${BASE_URL}/news/economic-calendar`, {
    params: { days_ahead: daysAhead },
  });
  return response.data;
};

/**
 * Get earnings calendar
 * @param {number} daysAhead - Days to look ahead
 */
export const getEarningsCalendar = async (daysAhead = 14) => {
  const response = await apiClient.get(`${BASE_URL}/news/earnings-calendar`, {
    params: { days_ahead: daysAhead },
  });
  return response.data;
};

/**
 * Get combined catalyst feed
 * @param {number} limit - Number of items
 */
export const getCatalystFeed = async (limit = 20) => {
  const response = await apiClient.get(`${BASE_URL}/news/catalyst-feed`, {
    params: { limit },
  });
  return response.data;
};

// =============================================================================
// AI COPILOT
// =============================================================================

/**
 * Get AI-generated morning brief
 */
export const getMorningBrief = async () => {
  const response = await apiClient.get(`${BASE_URL}/copilot/morning-brief`);
  return response.data;
};

/**
 * Get AI explanation for a metric
 * @param {string} metricName - Name of the metric
 * @param {any} metricValue - Current value
 * @param {string} context - Additional context
 */
export const explainMetric = async (metricName, metricValue, context = '') => {
  const response = await apiClient.post(`${BASE_URL}/copilot/explain`, {
    metric_name: metricName,
    metric_value: metricValue,
    context,
  });
  return response.data;
};

/**
 * Chat with the AI copilot
 * @param {string} message - User message
 * @param {Object} context - Current context
 * @param {Array} conversationHistory - Previous messages
 */
export const chatWithCopilot = async (message, context = null, conversationHistory = null) => {
  const response = await apiClient.post(`${BASE_URL}/copilot/chat`, {
    message,
    context,
    conversation_history: conversationHistory,
  });
  return response.data;
};

/**
 * Get AI analysis for a stock
 * @param {Object} stockData - Stock data from detail page
 * @param {Object} marketContext - Current market context
 */
export const analyzeStock = async (stockData, marketContext = null) => {
  const response = await apiClient.post(`${BASE_URL}/copilot/analyze-stock`, {
    stock_data: stockData,
    market_context: marketContext,
  });
  return response.data;
};

/**
 * Get AI copilot status and usage
 */
export const getCopilotStatus = async () => {
  const response = await apiClient.get(`${BASE_URL}/copilot/status`);
  return response.data;
};

// =============================================================================
// MACRO SIGNALS
// =============================================================================

/**
 * Get current Macro Risk Index (MRI)
 */
export const getMRI = async () => {
  const response = await apiClient.get(`${BASE_URL}/macro/mri`);
  return response.data;
};

/**
 * Get MRI history
 * @param {number} hours - Hours of history to retrieve
 */
export const getMRIHistory = async (hours = 24) => {
  const response = await apiClient.get(`${BASE_URL}/macro/mri/history`, {
    params: { hours },
  });
  return response.data;
};

/**
 * Get MRI components breakdown
 */
export const getMRIComponents = async () => {
  const response = await apiClient.get(`${BASE_URL}/macro/mri/components`);
  return response.data;
};

/**
 * Get macro events/prediction markets
 * @param {number} limit - Number of markets to return
 */
export const getMacroEvents = async (limit = 50) => {
  const response = await apiClient.get(`${BASE_URL}/macro/events`, {
    params: { limit },
  });
  return response.data;
};

/**
 * Get macro events by category
 * @param {string} category - Category filter
 */
export const getMacroEventsByCategory = async (category) => {
  const response = await apiClient.get(`${BASE_URL}/macro/events/category/${category}`);
  return response.data;
};

/**
 * Get macro divergences
 */
export const getMacroDivergences = async () => {
  const response = await apiClient.get(`${BASE_URL}/macro/divergences`);
  return response.data;
};

/**
 * Get narrative momentum
 * @param {string} category - Optional category filter
 * @param {number} threshold - Minimum change threshold
 */
export const getMacroMomentum = async (category = null, threshold = 10.0) => {
  const params = { threshold };
  if (category) params.category = category;
  const response = await apiClient.get(`${BASE_URL}/macro/momentum`, { params });
  return response.data;
};

/**
 * Get ticker macro bias
 * @param {string} symbol - Stock ticker
 */
export const getTickerMacroBias = async (symbol) => {
  const response = await apiClient.get(`${BASE_URL}/macro/ticker/${symbol}/bias`);
  return response.data;
};

/**
 * Get macro signal health status
 */
export const getMacroHealth = async () => {
  const response = await apiClient.get(`${BASE_URL}/macro/health`);
  return response.data;
};

export default {
  // Dashboard
  getDashboard,
  // Market Data
  getMarketSummary,
  getMarketIndices,
  getVolatility,
  getFearGreed,
  getSectorPerformance,
  // Polymarket
  getPolymarketDashboard,
  getTradingMarkets,
  getSignificantChanges,
  getKeyMarkets,
  // News
  getMarketNews,
  getCompanyNews,
  getEconomicCalendar,
  getEarningsCalendar,
  getCatalystFeed,
  // Copilot
  getMorningBrief,
  explainMetric,
  chatWithCopilot,
  analyzeStock,
  getCopilotStatus,
  // Macro Signals
  getMRI,
  getMRIHistory,
  getMRIComponents,
  getMacroEvents,
  getMacroEventsByCategory,
  getMacroDivergences,
  getMacroMomentum,
  getTickerMacroBias,
  getMacroHealth,
};
