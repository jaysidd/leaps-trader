/**
 * Screener API client
 */
import apiClient from './axios';

export const screenerAPI = {
  /**
   * Screen multiple stocks
   * @param {string[]} symbols - Array of stock symbols
   * @param {number} topN - Number of top results to return
   * @param {object} criteria - Custom screening criteria
   */
  screenStocks: async (symbols, topN = 15, criteria = null) => {
    const payload = {
      symbols,
      top_n: topN,
    };

    // Add criteria if provided
    if (criteria) {
      payload.criteria = {
        market_cap_min: criteria.marketCapMin,
        market_cap_max: criteria.marketCapMax,
        price_min: criteria.priceMin,
        price_max: criteria.priceMax,
        revenue_growth_min: criteria.revenueGrowthMin,
        earnings_growth_min: criteria.earningsGrowthMin,
        debt_to_equity_max: criteria.debtToEquityMax,
        current_ratio_min: criteria.currentRatioMin || 1.2,
        rsi_min: criteria.rsiMin,
        rsi_max: criteria.rsiMax,
        iv_max: criteria.ivMax,
        dte_min: criteria.minDTE,
        dte_max: criteria.maxDTE,
      };
    }

    const response = await apiClient.post('/api/v1/screener/screen', payload);
    return response.data;
  },

  /**
   * Screen a single stock
   * @param {string} symbol - Stock symbol
   */
  screenSingleStock: async (symbol) => {
    const response = await apiClient.get(`/api/v1/screener/single/${symbol}`);
    return response.data;
  },

  /**
   * Get top candidates
   * @param {string[]} symbols - Array of stock symbols
   * @param {number} topN - Number of top results
   */
  getTopCandidates: async (symbols, topN = 15) => {
    const params = new URLSearchParams();
    symbols.forEach(symbol => params.append('symbols', symbol));
    params.append('top_n', topN);

    const response = await apiClient.get(`/api/v1/screener/top?${params.toString()}`);
    return response.data;
  },

  /**
   * Quick market scan with preset - Scans 400+ stocks automatically
   * @param {string} preset - Preset name (conservative, moderate, aggressive)
   * @param {number} maxResults - Maximum results to return
   */
  quickScan: async (preset = 'moderate', maxResults = 25) => {
    const response = await apiClient.post('/api/v1/screener/scan/quick', {
      preset,
      max_results: maxResults
    }, {
      timeout: 600000 // 10 minutes for market scans
    });
    return response.data;
  },

  /**
   * Full market scan with custom criteria - Scans 400+ stocks
   * @param {object} criteria - Custom screening criteria (optional)
   */
  marketScan: async (criteria = null) => {
    const payload = criteria ? {
      market_cap_min: criteria.marketCapMin,
      market_cap_max: criteria.marketCapMax,
      price_min: criteria.priceMin,
      price_max: criteria.priceMax,
      revenue_growth_min: criteria.revenueGrowthMin,
      earnings_growth_min: criteria.earningsGrowthMin,
      debt_to_equity_max: criteria.debtToEquityMax,
      rsi_min: criteria.rsiMin,
      rsi_max: criteria.rsiMax,
      iv_max: criteria.ivMax
    } : null;

    const response = await apiClient.post('/api/v1/screener/scan/market', payload, {
      timeout: 600000 // 10 minutes for market scans
    });
    return response.data;
  },

  /**
   * Streaming market scan - Returns incremental results via SSE
   * @param {string} preset - Preset name (conservative, moderate, aggressive)
   * @param {function} onProgress - Callback for progress updates
   * @param {function} onComplete - Callback when scan completes
   * @param {function} onError - Callback for errors
   * @returns {function} - Abort function to cancel the stream
   */
  streamScan: (preset = 'moderate', onProgress, onComplete, onError) => {
    const eventSource = new EventSource(
      `http://localhost:8000/api/v1/screener/scan/stream/${preset}`
    );

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'start') {
          onProgress({
            status: 'starting',
            total: data.total,
            preset: data.preset,
            processed: 0,
            passed: 0,
            candidates: []
          });
        } else if (data.type === 'progress') {
          onProgress({
            status: 'scanning',
            processed: data.processed,
            total: data.total,
            passed: data.passed,
            candidates: data.top_candidates || []
          });
        } else if (data.type === 'complete') {
          eventSource.close();
          onComplete({
            processed: data.processed,
            total: data.total,
            passed: data.passed,
            results: data.results || []
          });
        } else if (data.type === 'error') {
          eventSource.close();
          onError(new Error(data.message));
        }
      } catch (err) {
        console.error('Error parsing SSE data:', err);
      }
    };

    eventSource.onerror = (err) => {
      eventSource.close();
      onError(new Error('Connection lost. Please try again.'));
    };

    // Return abort function
    return () => {
      eventSource.close();
    };
  },

  /**
   * Get available scanning presets
   * @returns {Promise} - List of presets with descriptions
   */
  getPresets: async () => {
    const response = await apiClient.get('/api/v1/screener/presets');
    return response.data;
  },

  /**
   * Calculate 5x return analysis for a LEAPS option
   * @param {number} currentPrice - Current stock price
   * @param {number} strike - Option strike price
   * @param {number} premium - Option premium (cost per share)
   * @param {number} dte - Days to expiration
   * @param {number[]} targetMultipliers - Optional return targets (default: [2, 3, 5, 10])
   * @returns {Promise} - Comprehensive return analysis
   */
  calculate5xReturn: async (currentPrice, strike, premium, dte, targetMultipliers = null) => {
    const payload = {
      current_price: currentPrice,
      strike: strike,
      premium: premium,
      dte: dte,
    };
    if (targetMultipliers) {
      payload.target_multipliers = targetMultipliers;
    }
    const response = await apiClient.post('/api/v1/screener/calculator/5x-return', payload);
    return response.data;
  },

  /**
   * Calculate P/L table for options visualization
   * @param {number} strike - Option strike price
   * @param {number} premium - Option premium paid
   * @param {number} currentPrice - Current stock price
   * @param {number} priceRangePercent - Range above/below current price (default: 50%)
   * @param {number} numPoints - Number of price points (default: 15)
   * @returns {Promise} - P/L table data
   */
  calculatePLTable: async (strike, premium, currentPrice, priceRangePercent = 50, numPoints = 15) => {
    const response = await apiClient.post('/api/v1/screener/calculator/pl-table', {
      strike,
      premium,
      current_price: currentPrice,
      price_range_percent: priceRangePercent,
      num_points: numPoints
    });
    return response.data;
  },

  /**
   * Get strike selection recommendation
   * @param {string} symbol - Stock symbol
   * @param {number} currentPrice - Current stock price
   * @param {number} targetReturn - Target return multiplier (default: 5)
   * @param {string} riskTolerance - Risk level: conservative, moderate, aggressive
   * @returns {Promise} - Strike recommendation
   */
  recommendStrike: async (symbol, currentPrice, targetReturn = 5, riskTolerance = 'moderate') => {
    const response = await apiClient.post('/api/v1/screener/calculator/strike-selection', {
      symbol,
      current_price: currentPrice,
      target_return: targetReturn,
      risk_tolerance: riskTolerance
    });
    return response.data;
  },

  /**
   * Get composite scores for multiple stocks (no filter gates)
   * @param {string[]} symbols - Array of stock symbols (max 50)
   * @returns {Promise} - { scores: { AAPL: { score, fundamental_score, ... }, ... }, total, scored }
   */
  getBatchScores: async (symbols) => {
    const response = await apiClient.post('/api/v1/screener/batch-scores', { symbols }, {
      timeout: 300000 // 5 minutes for batch scoring
    });
    return response.data;
  },

  /**
   * Stream scan across ALL presets at once via SSE.
   * The backend screens the full universe once with permissive criteria,
   * then tags each result with the presets it matches.
   *
   * @param {function} onProgress - Progress callback
   * @param {function} onComplete - Completion callback
   * @param {function} onError - Error callback
   * @returns {function} - Abort function
   */
  streamScanAll: (onProgress, onComplete, onError) => {
    const eventSource = new EventSource(
      `http://localhost:8000/api/v1/screener/scan/stream/all`
    );

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'start') {
          onProgress({
            status: 'starting',
            total: data.total,
            preset: 'all',
            processed: 0,
            passed: 0,
            candidates: [],
          });
        } else if (data.type === 'progress') {
          onProgress({
            status: 'scanning',
            processed: data.processed,
            total: data.total,
            passed: data.passed,
            candidates: data.top_candidates || [],
          });
        } else if (data.type === 'complete') {
          eventSource.close();
          onComplete({
            processed: data.processed,
            total: data.total,
            passed: data.passed,
            results: data.results || [],
            presetSummary: data.preset_summary || null,
            durationSeconds: data.duration_seconds || null,
          });
        } else if (data.type === 'error') {
          eventSource.close();
          onError(new Error(data.message));
        }
      } catch (err) {
        console.error('Error parsing SSE data:', err);
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
      onError(new Error('Connection lost. Please try again.'));
    };

    return () => {
      eventSource.close();
    };
  },
};

// Export individual functions for convenience
export const screenSingleStock = screenerAPI.screenSingleStock;
export const screenStocks = screenerAPI.screenStocks;
export const quickScan = screenerAPI.quickScan;
export const streamScan = screenerAPI.streamScan;
