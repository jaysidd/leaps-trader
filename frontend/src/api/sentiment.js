/**
 * Sentiment and Catalyst API client
 * Phase 2: Smart Scoring
 */
import apiClient from './axios';

export const sentimentAPI = {
  /**
   * Get comprehensive sentiment analysis for a stock
   * @param {string} symbol - Stock ticker
   * @param {string} companyName - Optional company name for news search
   */
  getSentiment: async (symbol, companyName = null) => {
    const params = companyName ? { company_name: companyName } : {};
    const response = await apiClient.get(`/api/v1/sentiment/sentiment/${symbol}`, {
      params,
      timeout: 30000
    });
    return response.data;
  },

  /**
   * Get sentiment for multiple stocks
   * @param {string[]} symbols - Array of stock tickers
   */
  getBatchSentiment: async (symbols) => {
    const response = await apiClient.post('/api/v1/sentiment/sentiment/batch', {
      symbols
    }, {
      timeout: 60000
    });
    return response.data;
  },

  /**
   * Get catalyst calendar for a stock
   * @param {string} symbol - Stock ticker
   */
  getCatalysts: async (symbol) => {
    const response = await apiClient.get(`/api/v1/sentiment/catalysts/${symbol}`);
    return response.data;
  },

  /**
   * Get historical earnings move for a stock
   * @param {string} symbol - Stock ticker
   */
  getEarningsMove: async (symbol) => {
    const response = await apiClient.get(`/api/v1/sentiment/catalysts/${symbol}/earnings-move`);
    return response.data;
  },

  /**
   * Get macro economic calendar
   */
  getMacroCalendar: async () => {
    const response = await apiClient.get('/api/v1/sentiment/macro-calendar');
    return response.data;
  },

  /**
   * Get news for a stock with sentiment scores
   * @param {string} symbol - Stock ticker
   * @param {number} limit - Number of news items
   */
  getNews: async (symbol, limit = 10) => {
    const response = await apiClient.get(`/api/v1/sentiment/news/${symbol}`, {
      params: { limit }
    });
    return response.data;
  },

  /**
   * Get insider trading activity for a stock
   * @param {string} symbol - Stock ticker
   */
  getInsiderTrades: async (symbol) => {
    const response = await apiClient.get(`/api/v1/sentiment/insiders/${symbol}`);
    return response.data;
  },

  /**
   * Screen a stock with sentiment analysis
   * @param {string} symbol - Stock ticker
   * @param {boolean} includeSentiment - Include sentiment in scoring
   */
  screenEnhanced: async (symbol, includeSentiment = true) => {
    const response = await apiClient.get(`/api/v1/sentiment/screen-enhanced/${symbol}`, {
      params: { include_sentiment: includeSentiment },
      timeout: 60000
    });
    return response.data;
  },

  /**
   * Screen multiple stocks with sentiment
   * @param {string[]} symbols - Array of stock tickers
   * @param {boolean} includeSentiment - Include sentiment in scoring
   * @param {number} topN - Number of top results
   */
  screenBatchEnhanced: async (symbols, includeSentiment = true, topN = 15) => {
    const response = await apiClient.post('/api/v1/sentiment/screen-enhanced/batch', null, {
      params: {
        symbols: symbols.join(','),
        include_sentiment: includeSentiment,
        top_n: topN
      },
      timeout: 120000
    });
    return response.data;
  }
};

export default sentimentAPI;
