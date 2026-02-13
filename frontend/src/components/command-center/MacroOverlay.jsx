/**
 * Macro Overlay Component
 * Shows macro context for a specific ticker
 *
 * IMPORTANT: This overlay provides CONTEXT, not a gatekeeper.
 * - Trade compatibility is an INFO flag, NOT a gate
 * - Macro informs the trade, it never replaces the trader
 * - If macro is unclear, show uncertainty - do not hide the signal
 */
import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { getTickerMacroOverlay } from '../../api/macroIntelligence';

const getBiasConfig = (bias) => {
  switch (bias) {
    case 'bullish':
      return { label: 'Bullish', color: 'text-green-600 dark:text-green-400', bgColor: 'bg-green-100 dark:bg-green-500/20', icon: '📈' };
    case 'bearish':
      return { label: 'Bearish', color: 'text-red-600 dark:text-red-400', bgColor: 'bg-red-100 dark:bg-red-500/20', icon: '📉' };
    case 'unknown':
      return { label: 'Unknown', color: 'text-gray-500 dark:text-gray-400', bgColor: 'bg-gray-100 dark:bg-gray-500/20', icon: '❓' };
    default:
      return { label: 'Neutral', color: 'text-yellow-600 dark:text-yellow-400', bgColor: 'bg-yellow-100 dark:bg-yellow-500/20', icon: '➖' };
  }
};

const getCompatibilityConfig = (compatibility) => {
  switch (compatibility) {
    case 'favorable':
      return { label: 'Favorable', color: 'text-green-600 dark:text-green-400', bgColor: 'bg-green-50 dark:bg-green-900/30', icon: '✓' };
    case 'unfavorable':
      return { label: 'Unfavorable', color: 'text-red-600 dark:text-red-400', bgColor: 'bg-red-50 dark:bg-red-900/30', icon: '⚠' };
    default:
      return { label: 'Mixed', color: 'text-yellow-600 dark:text-yellow-400', bgColor: 'bg-yellow-50 dark:bg-yellow-900/30', icon: '~' };
  }
};

const getConfidenceConfig = (score) => {
  if (score >= 70) {
    return { label: 'High', color: 'text-green-600 dark:text-green-400' };
  } else if (score >= 40) {
    return { label: 'Medium', color: 'text-yellow-600 dark:text-yellow-400' };
  } else {
    return { label: 'Low', color: 'text-red-600 dark:text-red-400' };
  }
};

export default function MacroOverlay({
  symbol,
  sector = null,
  compact = false,
  overlayData = null, // Pre-fetched data from batch - skips individual fetch
  onExpandClick = null,
}) {
  const [data, setData] = useState(overlayData);
  const [loading, setLoading] = useState(!overlayData);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);

  // Update if overlayData prop changes (from parent batch fetch)
  useEffect(() => {
    if (overlayData) {
      setData(overlayData);
      setLoading(false);
      setError(null);
    }
  }, [overlayData]);

  // Only fetch if no overlayData was provided (standalone usage)
  const fetchData = useCallback(async () => {
    if (!symbol || overlayData) return;

    try {
      setLoading(true);
      setError(null);
      const result = await getTickerMacroOverlay(symbol, sector);
      setData(result);
    } catch (err) {
      console.error('Error fetching macro overlay:', err);
      setError(err.message || 'Failed to load macro data');
    } finally {
      setLoading(false);
    }
  }, [symbol, sector, overlayData]);

  useEffect(() => {
    if (!overlayData) {
      fetchData();
    }
  }, [fetchData, overlayData]);

  if (loading) {
    if (compact) {
      return <span className="text-xs text-gray-500">...</span>;
    }
    return (
      <div className="bg-gray-100 dark:bg-gray-800/50 rounded-lg p-3 animate-pulse">
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-1/3 mb-2"></div>
        <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-2/3"></div>
      </div>
    );
  }

  if (error || !data) {
    if (compact) {
      return <span className="text-xs text-gray-500">--</span>;
    }
    return (
      <div className="bg-gray-100 dark:bg-gray-800/50 rounded-lg p-3">
        <div className="text-xs text-gray-500">Macro data unavailable</div>
      </div>
    );
  }

  const biasConfig = getBiasConfig(data.macro_bias);
  const compatConfig = getCompatibilityConfig(data.trade_compatibility);
  const confidenceConfig = getConfidenceConfig(data.confidence_score || 0);

  // Compact mode - minimal display for tight spaces
  if (compact) {
    return (
      <div className="flex items-center gap-3 text-xs">
        <span className={`flex items-center gap-1 ${biasConfig.color}`} title={`Macro Bias: ${biasConfig.label}`}>
          {biasConfig.icon} {biasConfig.label}
        </span>
        <span className={`flex items-center gap-1 ${compatConfig.color}`} title={`Trade Compatibility: ${compatConfig.label}`}>
          {compatConfig.icon} {compatConfig.label}
        </span>
        {data.data_stale && (
          <span className="text-orange-400" title="Data may be stale">⚠️</span>
        )}
        {data.macro_headwind && (
          <span className="text-red-400" title="Macro headwind detected">🌬️</span>
        )}
      </div>
    );
  }

  return (
    <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3 border border-gray-200 dark:border-gray-700/50">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
            Macro Overlay
          </span>
          {data.data_stale && (
            <span className="text-orange-400 text-xs" title="Data may be stale">⚠️</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs ${data.confidence_score > 0 ? confidenceConfig.color : 'text-gray-500'}`}>
            {data.confidence_score > 0
              ? `${data.confidence_score.toFixed(0)}% conf`
              : 'Pending'}
          </span>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
          >
            {expanded ? '▼' : '▶'}
          </button>
        </div>
      </div>

      {/* Main Display */}
      <div className="flex items-center gap-4 mb-3">
        {/* Macro Bias */}
        <div className={`flex-1 ${biasConfig.bgColor} rounded p-2`}>
          <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Macro Bias</div>
          <div className="flex items-center gap-1">
            <span>{biasConfig.icon}</span>
            <span className={`font-semibold ${biasConfig.color}`}>{biasConfig.label}</span>
            {data.macro_bias_score !== null && (
              <span className="text-xs text-gray-500 dark:text-gray-400 ml-1">
                ({data.macro_bias_score?.toFixed(0)})
              </span>
            )}
          </div>
        </div>

        {/* Trade Compatibility - INFO only, NOT a gate */}
        <div className={`flex-1 ${compatConfig.bgColor} rounded p-2`}>
          <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Trade Compatibility</div>
          <div className="flex items-center gap-1">
            <span className={compatConfig.color}>{compatConfig.icon}</span>
            <span className={`font-semibold ${compatConfig.color}`}>{compatConfig.label}</span>
          </div>
        </div>
      </div>

      {/* Macro Headwind Flag */}
      {data.macro_headwind && (
        <div className="mb-3 p-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-600/30 rounded text-xs text-red-700 dark:text-red-300">
          🌬️ <strong>Macro Headwind:</strong> Current conditions may create resistance
        </div>
      )}

      {/* Key Drivers (Top 3, human-readable) */}
      {data.drivers && data.drivers.length > 0 && (
        <div className="mb-3">
          <div className="text-xs text-gray-500 mb-1">Key Macro Drivers</div>
          <ul className="text-xs text-gray-700 dark:text-gray-300 space-y-1">
            {data.drivers.map((driver, idx) => (
              <li key={idx} className="flex items-center gap-2">
                <span className="text-gray-400 dark:text-gray-500">•</span>
                {driver}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Earnings Callout (if within 10 days) */}
      {data.earnings && (
        <div className="mb-3 p-2 bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-600/30 rounded text-xs">
          <span className="text-orange-700 dark:text-orange-300">
            ⚠ Earnings: {new Date(data.earnings.event_datetime).toLocaleDateString()}
            {data.earnings.session && ` (${data.earnings.session.replace('_', ' ')})`}
          </span>
          {!data.earnings.confirmed && (
            <span className="text-gray-500 dark:text-gray-400 ml-2">(Unconfirmed)</span>
          )}
        </div>
      )}

      {/* Expanded Details */}
      {expanded && data.details && (
        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-500 dark:text-gray-400">Trade Readiness</span>
              <span className="text-gray-900 dark:text-white">
                {data.details.trade_readiness_score?.toFixed(0) || 'N/A'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500 dark:text-gray-400">Liquidity</span>
              <span className={`capitalize ${
                data.details.liquidity_regime === 'risk_on' ? 'text-green-600 dark:text-green-400' :
                data.details.liquidity_regime === 'risk_off' ? 'text-red-600 dark:text-red-400' :
                'text-yellow-600 dark:text-yellow-400'
              }`}>
                {data.details.liquidity_regime?.replace('_', '-') || 'N/A'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500 dark:text-gray-400">MRI</span>
              <span className="text-gray-900 dark:text-white">
                {data.details.mri_score?.toFixed(0) || 'N/A'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500 dark:text-gray-400">Sector</span>
              <span className="text-gray-900 dark:text-white">
                {data.sector || 'Unknown'}
              </span>
            </div>
          </div>

          {/* Compatibility Reasons - dynamic label based on compatibility */}
          {data.compatibility_reasons && data.compatibility_reasons.length > 0 && (
            <div className="mt-3">
              <div className="text-xs text-gray-500 mb-1">
                Why this is {compatConfig.label}
              </div>
              <ul className="text-xs text-gray-600 dark:text-gray-400 space-y-0.5">
                {data.compatibility_reasons.map((reason, idx) => (
                  <li key={idx}>• {reason}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Footer with Link */}
      <div className="flex items-center justify-between mt-3 pt-2 border-t border-gray-200 dark:border-gray-700/50">
        <div className="text-xs text-gray-500">
          {data.calculated_at && `Updated ${new Date(data.calculated_at).toLocaleTimeString()}`}
        </div>
        <Link
          to="/macro-intelligence"
          className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
        >
          Full Macro Intel →
        </Link>
      </div>

      {/* Important Note */}
      <div className="mt-2 text-[10px] text-gray-400 dark:text-gray-500 italic">
        Macro context informs, but never gates, your trading decisions.
      </div>
    </div>
  );
}
