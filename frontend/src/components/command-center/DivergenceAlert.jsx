/**
 * Divergence Alert Component
 * Displays divergences between prediction markets and price proxies
 */
import { useState } from 'react';

const getSeverityConfig = (severity) => {
  if (severity === 'high') {
    return { bg: 'bg-red-900/30', border: 'border-red-600/50', text: 'text-red-300', icon: '🔴' };
  } else if (severity === 'medium') {
    return { bg: 'bg-yellow-900/30', border: 'border-yellow-600/50', text: 'text-yellow-300', icon: '🟡' };
  }
  return { bg: 'bg-blue-900/30', border: 'border-blue-600/50', text: 'text-blue-300', icon: '🔵' };
};

function DivergenceCard({ divergence }) {
  const [expanded, setExpanded] = useState(false);
  const isBullish = divergence.type === 'bullish_divergence';
  const severityConfig = getSeverityConfig(divergence.severity);

  return (
    <div className={`${severityConfig.bg} border ${severityConfig.border} rounded-lg p-3`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl">
            {isBullish ? '📈' : '📉'}
          </span>
          <div>
            <div className={`font-semibold ${severityConfig.text}`}>
              {isBullish ? 'Bullish' : 'Bearish'} Divergence
            </div>
            <div className="text-xs text-gray-400">
              {divergence.prediction_category?.replace(/_/g, ' ')} vs {divergence.proxy_symbol}
            </div>
          </div>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          {expanded ? 'Less' : 'More'}
        </button>
      </div>

      {/* Quick Summary */}
      <div className="mt-2 text-sm text-gray-300">
        {divergence.interpretation || (
          isBullish
            ? `${divergence.prediction_category} odds improving while ${divergence.proxy_symbol} lags`
            : `${divergence.prediction_category} odds worsening while ${divergence.proxy_symbol} stable`
        )}
      </div>

      {/* Persistence Badge */}
      {divergence.persistence_checks && divergence.persistence_checks >= 2 && (
        <div className="mt-2 inline-flex items-center gap-1 text-xs bg-gray-700/50 px-2 py-1 rounded">
          <span>✓</span>
          <span>Persisted {divergence.persistence_checks}+ checks</span>
        </div>
      )}

      {/* Expanded Details */}
      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-600/50 space-y-2 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-gray-400 mb-1">Prediction Change (24h)</div>
              <div className={`font-mono ${divergence.prediction_change > 0 ? 'text-green-400' : 'text-red-400'}`}>
                {divergence.prediction_change > 0 ? '+' : ''}{divergence.prediction_change?.toFixed(1)}%
              </div>
            </div>
            <div>
              <div className="text-gray-400 mb-1">{divergence.proxy_symbol} Change</div>
              <div className={`font-mono ${divergence.proxy_change > 0 ? 'text-green-400' : 'text-red-400'}`}>
                {divergence.proxy_change > 0 ? '+' : ''}{divergence.proxy_change?.toFixed(2)}%
              </div>
            </div>
          </div>

          {/* ATR Context */}
          {divergence.proxy_atr && (
            <div className="text-gray-400">
              {divergence.proxy_symbol} ATR: {divergence.proxy_atr?.toFixed(2)}%
              <span className="ml-2 text-gray-500">
                (price within normal range)
              </span>
            </div>
          )}

          {/* What This Means */}
          <div className="mt-2 p-2 bg-gray-700/30 rounded text-gray-300">
            <strong>What this means:</strong> Prediction markets are signaling a shift in{' '}
            {divergence.prediction_category?.replace(/_/g, ' ')} expectations, but the market proxy
            ({divergence.proxy_symbol}) hasn't reacted yet. This could indicate an{' '}
            {isBullish ? 'upcoming rally' : 'upcoming decline'} if the divergence resolves.
          </div>
        </div>
      )}
    </div>
  );
}

export default function DivergenceAlert({ divergences, loading }) {
  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="h-20 bg-gray-700 rounded"></div>
      </div>
    );
  }

  // No divergences is good - show a positive state
  if (!divergences || divergences.length === 0) {
    return (
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Divergence Monitor
        </h3>
        <div className="flex items-center gap-3 text-gray-400 text-sm">
          <span className="text-green-400 text-xl">✓</span>
          <span>No significant divergences detected. Markets are aligned.</span>
        </div>
      </div>
    );
  }

  // Count by type
  const bullishCount = divergences.filter(d => d.type === 'bullish_divergence').length;
  const bearishCount = divergences.filter(d => d.type === 'bearish_divergence').length;

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          Divergence Monitor
        </h3>
        <div className="flex items-center gap-2 text-xs">
          {bullishCount > 0 && (
            <span className="text-green-400">📈 {bullishCount}</span>
          )}
          {bearishCount > 0 && (
            <span className="text-red-400">📉 {bearishCount}</span>
          )}
        </div>
      </div>

      <div className="space-y-3">
        {divergences.map((divergence, idx) => (
          <DivergenceCard key={idx} divergence={divergence} />
        ))}
      </div>

      <div className="mt-3 text-xs text-gray-500">
        Divergences must persist across 2+ checks to appear here
      </div>
    </div>
  );
}
