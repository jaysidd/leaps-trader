/**
 * Strategy Recommendation API client
 * Phase 3: Strategy Selector
 */
import apiClient from './axios';

export const strategyAPI = {
  /**
   * Get strategy recommendation for a stock
   * @param {string} symbol - Stock ticker
   * @param {Object} options - Strategy options
   * @param {number} options.conviction - Conviction score (1-10)
   * @param {string} options.riskTolerance - Risk tolerance level
   * @param {number} options.portfolioValue - Portfolio value for sizing
   */
  getRecommendation: async (symbol, options = {}) => {
    const params = {
      conviction_score: options.conviction || 5,
      risk_tolerance: options.riskTolerance || 'moderate',
    };
    if (options.portfolioValue) {
      params.portfolio_value = options.portfolioValue;
    }

    const response = await apiClient.get(`/api/v1/strategy/recommend/${symbol}`, {
      params,
      timeout: 30000
    });
    return response.data;
  },

  /**
   * Get strategy recommendations for multiple stocks
   * @param {string[]} symbols - Array of stock tickers
   * @param {Object} options - Strategy options
   */
  getBatchRecommendations: async (symbols, options = {}) => {
    const response = await apiClient.post('/api/v1/strategy/recommend/batch', {
      symbols,
      conviction_scores: options.convictionScores || {},
      risk_tolerance: options.riskTolerance || 'moderate'
    }, {
      timeout: 60000
    });
    return response.data;
  },

  /**
   * Calculate optimal position size
   * @param {Object} params - Position sizing parameters
   */
  calculatePositionSize: async (params) => {
    const response = await apiClient.post('/api/v1/strategy/position-size', {
      portfolio_value: params.portfolioValue,
      conviction_score: params.conviction || 5,
      win_probability: params.winProbability || 0.55,
      profit_target_pct: params.profitTarget || 100,
      stop_loss_pct: params.stopLoss || 40,
      option_premium: params.optionPremium || null,
      market_regime: params.marketRegime || 'neutral',
      days_to_earnings: params.daysToEarnings || null,
      sector: params.sector || null,
      sizing_method: params.method || 'kelly'
    });
    return response.data;
  },

  /**
   * Quick position size calculation
   * @param {number} portfolioValue - Portfolio value
   * @param {number} conviction - Conviction score
   * @param {string} regime - Market regime
   * @param {number} daysToEarnings - Days to earnings (optional)
   */
  quickPositionSize: async (portfolioValue, conviction = 5, regime = 'neutral', daysToEarnings = null) => {
    const params = {
      portfolio_value: portfolioValue,
      conviction,
      regime
    };
    if (daysToEarnings !== null) {
      params.days_to_earnings = daysToEarnings;
    }

    const response = await apiClient.get('/api/v1/strategy/position-size/quick', {
      params
    });
    return response.data;
  },

  /**
   * Optimize delta and DTE based on conditions
   * @param {Object} params - Optimization parameters
   */
  optimizeDeltaDTE: async (params) => {
    const response = await apiClient.post('/api/v1/strategy/optimize-delta-dte', {
      strategy_type: params.strategyType || 'long_call',
      market_regime: params.marketRegime || 'neutral',
      risk_tolerance: params.riskTolerance || 'moderate',
      iv_rank: params.ivRank || 50,
      conviction: params.conviction || 5,
      days_to_earnings: params.daysToEarnings || null
    });
    return response.data;
  },

  /**
   * Quick delta/DTE optimization
   * @param {string} strategy - Strategy type
   * @param {string} regime - Market regime
   * @param {number} ivRank - IV rank
   */
  quickDeltaDTE: async (strategy = 'long_call', regime = 'neutral', ivRank = 50) => {
    const response = await apiClient.get('/api/v1/strategy/optimize-delta-dte/quick', {
      params: { strategy, regime, iv_rank: ivRank }
    });
    return response.data;
  },

  /**
   * Get current market regime
   */
  getMarketRegime: async () => {
    const response = await apiClient.get('/api/v1/strategy/market-regime', {
      timeout: 30000
    });
    return response.data;
  },

  /**
   * Get list of strategy types with descriptions
   */
  getStrategyTypes: async () => {
    const response = await apiClient.get('/api/v1/strategy/strategy-types');
    return response.data;
  }
};

export default strategyAPI;
