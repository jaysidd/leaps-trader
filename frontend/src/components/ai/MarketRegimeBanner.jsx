/**
 * Market Regime Banner - Displays current market conditions
 */
import { useState, useEffect, useCallback } from 'react';
import { aiAPI } from '../../api/ai';
import { getMarketStatus, shouldAutoRefresh } from '../../utils/marketHours';

export default function MarketRegimeBanner({ onRegimeChange }) {
  const [regime, setRegime] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [marketStatus, setMarketStatus] = useState(() => getMarketStatus());

  const fetchRegime = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await aiAPI.getMarketRegime(false); // Use rules-based for speed
      setRegime(data);
      setLastUpdated(new Date());
      setMarketStatus(getMarketStatus());
      if (onRegimeChange) {
        onRegimeChange(data);
      }
    } catch (err) {
      console.error('Failed to fetch market regime:', err);
      setError(err.message || 'Failed to load market data');
    } finally {
      setLoading(false);
    }
  }, [onRegimeChange]);

  useEffect(() => {
    // Initial fetch
    fetchRegime();

    // Set up smart refresh based on market hours
    let refreshIntervalId = null;

    const setupAutoRefresh = () => {
      // Clear existing interval
      if (refreshIntervalId) {
        clearInterval(refreshIntervalId);
        refreshIntervalId = null;
      }

      // Only auto-refresh when market is open or about to open
      if (shouldAutoRefresh()) {
        console.log('Market open - auto-refresh enabled (5 min)');
        refreshIntervalId = setInterval(fetchRegime, 5 * 60 * 1000);
      } else {
        console.log('Market closed - auto-refresh disabled');
      }
    };

    setupAutoRefresh();

    // Check market status every minute to catch open/close transitions
    const statusCheckId = setInterval(() => {
      const newStatus = getMarketStatus();
      setMarketStatus(newStatus);

      // Re-evaluate auto-refresh when status changes
      const wasRefreshing = refreshIntervalId !== null;
      const shouldRefresh = shouldAutoRefresh();

      if (shouldRefresh && !wasRefreshing) {
        console.log('Market just opened - starting auto-refresh');
        setupAutoRefresh();
      } else if (!shouldRefresh && wasRefreshing) {
        console.log('Market just closed - stopping auto-refresh');
        if (refreshIntervalId) {
          clearInterval(refreshIntervalId);
          refreshIntervalId = null;
        }
      }
    }, 60 * 1000);

    return () => {
      if (refreshIntervalId) clearInterval(refreshIntervalId);
      clearInterval(statusCheckId);
    };
  }, [fetchRegime]);

  if (loading && !regime) {
    return (
      <div className="bg-gray-100 rounded-lg p-4 mb-6 animate-pulse">
        <div className="h-6 bg-gray-200 rounded w-1/3 mb-2"></div>
        <div className="h-4 bg-gray-200 rounded w-2/3"></div>
      </div>
    );
  }

  if (error && !regime) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
        <div className="flex items-center justify-between">
          <span className="text-yellow-800">Market data unavailable</span>
          <button
            onClick={fetchRegime}
            className="text-yellow-600 hover:text-yellow-800 text-sm font-medium"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!regime) return null;

  // Determine colors based on regime
  const getRegimeColors = () => {
    switch (regime.regime) {
      case 'bullish':
        return {
          bg: 'bg-green-50',
          border: 'border-green-200',
          badge: 'bg-green-500',
          text: 'text-green-800'
        };
      case 'bearish':
        return {
          bg: 'bg-red-50',
          border: 'border-red-200',
          badge: 'bg-red-500',
          text: 'text-red-800'
        };
      default:
        return {
          bg: 'bg-yellow-50',
          border: 'border-yellow-200',
          badge: 'bg-yellow-500',
          text: 'text-yellow-800'
        };
    }
  };

  const getVixColor = () => {
    if (regime.vix < 15) return 'text-green-600';
    if (regime.vix < 20) return 'text-green-500';
    if (regime.vix < 25) return 'text-yellow-600';
    if (regime.vix < 30) return 'text-orange-500';
    return 'text-red-600';
  };

  const getRiskModeIcon = () => {
    switch (regime.risk_mode) {
      case 'risk_on':
        return '🚀';
      case 'risk_off':
        return '🛡️';
      default:
        return '⚖️';
    }
  };

  const colors = getRegimeColors();

  return (
    <div className={`${colors.bg} ${colors.border} border rounded-lg p-4 mb-6`}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Regime Badge */}
        <div className="flex items-center gap-3">
          <span className={`${colors.badge} text-white text-sm font-bold px-3 py-1 rounded-full uppercase`}>
            {regime.regime}
          </span>
          <span className="text-lg">
            {getRiskModeIcon()} {regime.risk_mode.replace('_', '-').toUpperCase()}
          </span>
        </div>

        {/* Key Metrics */}
        <div className="flex flex-wrap items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-gray-500">VIX:</span>
            <span className={`font-bold ${getVixColor()}`}>
              {regime.vix.toFixed(1)}
            </span>
            <span className="text-gray-400 text-xs">
              ({regime.vix_trend})
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-gray-500">SPY RSI:</span>
            <span className="font-medium">{regime.spy_rsi.toFixed(0)}</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-gray-500">vs 200 SMA:</span>
            <span className="font-medium">{regime.spy_vs_200sma}</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-gray-500">Delta:</span>
            <span className="font-medium">
              {regime.delta_range[0].toFixed(2)}-{regime.delta_range[1].toFixed(2)}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-gray-500">DTE:</span>
            <span className="font-medium">
              {regime.dte_range[0]}-{regime.dte_range[1]}
            </span>
          </div>
        </div>

        {/* Refresh Button */}
        <button
          onClick={fetchRegime}
          disabled={loading}
          className="text-gray-500 hover:text-gray-700 p-1"
          title="Refresh market data"
        >
          <svg
            className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>

      {/* Summary */}
      <p className={`mt-3 text-sm ${colors.text}`}>
        {regime.summary}
      </p>

      {/* Sectors */}
      <div className="mt-3 flex flex-wrap gap-4 text-xs">
        {regime.sectors_favor?.length > 0 && (
          <div>
            <span className="text-gray-500">Favor:</span>{' '}
            <span className="text-green-600 font-medium">
              {regime.sectors_favor.join(', ')}
            </span>
          </div>
        )}
        {regime.sectors_avoid?.length > 0 && (
          <div>
            <span className="text-gray-500">Avoid:</span>{' '}
            <span className="text-red-600 font-medium">
              {regime.sectors_avoid.join(', ')}
            </span>
          </div>
        )}
      </div>

      {/* Last Updated & Market Status */}
      <div className="mt-2 flex items-center justify-between text-xs text-gray-400">
        {lastUpdated && (
          <span>Updated: {lastUpdated.toLocaleTimeString()}</span>
        )}
        {marketStatus && (
          <span className={`flex items-center gap-1 ${marketStatus.isOpen ? 'text-green-600' : 'text-gray-500'}`}>
            <span className={`w-2 h-2 rounded-full ${marketStatus.isOpen ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`}></span>
            {marketStatus.message}
            {!marketStatus.isOpen && <span className="text-gray-400">(Auto-refresh paused)</span>}
          </span>
        )}
      </div>
    </div>
  );
}
