/**
 * Stocks API client
 */
import apiClient from './axios';

export const stocksAPI = {
  /**
   * Get stock information
   * @param {string} symbol - Stock symbol
   */
  getStockInfo: async (symbol) => {
    const response = await apiClient.get(`/api/v1/stocks/info/${symbol}`);
    return response.data;
  },

  /**
   * Get current price
   * @param {string} symbol - Stock symbol
   */
  getCurrentPrice: async (symbol) => {
    const response = await apiClient.get(`/api/v1/stocks/price/${symbol}`);
    return response.data;
  },

  /**
   * Get historical prices
   * @param {string} symbol - Stock symbol
   * @param {string} period - Time period (1y, 6mo, etc.)
   */
  getHistoricalPrices: async (symbol, period = '1y') => {
    const response = await apiClient.get(`/api/v1/stocks/history/${symbol}`, {
      params: { period },
    });
    return response.data;
  },

  /**
   * Get fundamentals
   * @param {string} symbol - Stock symbol
   */
  getFundamentals: async (symbol) => {
    const response = await apiClient.get(`/api/v1/stocks/fundamentals/${symbol}`);
    return response.data;
  },

  /**
   * Get options chain
   * @param {string} symbol - Stock symbol
   */
  getOptionsChain: async (symbol) => {
    const response = await apiClient.get(`/api/v1/stocks/options/${symbol}`);
    return response.data;
  },

  /**
   * Get live quotes for multiple symbols (Alpaca)
   * @param {string[]} symbols - Array of stock symbols
   * @returns {{ quotes: Object, total: number, successful: number }}
   */
  getBatchQuotes: async (symbols) => {
    const response = await apiClient.post('/api/v1/stocks/batch-quotes', { symbols });
    return response.data;
  },
};
