/**
 * Liquidity Widget
 * Displays liquidity regime score with key metrics and drivers
 */
import { useState } from 'react';

const formatLargeNumber = (num) => {
  if (num === null || num === undefined) return '-';
  if (num >= 1e12) return `$${(num / 1e12).toFixed(2)}T`;
  if (num >= 1e9) return `$${(num / 1e9).toFixed(2)}B`;
  if (num >= 1e6) return `$${(num / 1e6).toFixed(2)}M`;
  return num.toFixed(2);
};

const formatChange = (value, isPercent = true) => {
  if (value === null || value === undefined) return '-';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}${isPercent ? '%' : ''}`;
};

const getRegimeConfig = (regime) => {
  switch (regime) {
    case 'risk_on':
      return { label: 'Expanding', color: '#22c55e', emoji: '📈', description: 'Liquidity expanding - supportive for risk assets' };
    case 'risk_off':
      return { label: 'Contracting', color: '#dc2626', emoji: '📉', description: 'Liquidity contracting - caution advised' };
    default:
      return { label: 'Transition', color: '#eab308', emoji: '➡️', description: 'Liquidity conditions mixed' };
  }
};

const metricLabels = {
  fed_balance_sheet: { label: 'Fed Balance Sheet', tooltip: 'Federal Reserve Total Assets' },
  rrp: { label: 'Reverse Repo', tooltip: 'Overnight Reverse Repurchase Agreements' },
  tga: { label: 'Treasury Account', tooltip: 'Treasury General Account' },
  fci: { label: 'Financial Conditions', tooltip: 'Chicago Fed National Financial Conditions Index' },
  real_yield_10y: { label: 'Real Yield (10Y)', tooltip: '10-Year Real Yield (Nominal - Inflation)' },
};

export default function LiquidityWidget({ data, loading, onExplain }) {
  const [showMetrics, setShowMetrics] = useState(false);

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/2 mb-4"></div>
        <div className="h-20 bg-gray-700 rounded"></div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Liquidity Regime
        </h3>
        <div className="text-gray-500 text-sm">Data unavailable</div>
      </div>
    );
  }

  const score = data.score || 50;
  const regime = data.regime || 'transition';
  const regimeConfig = getRegimeConfig(regime);
  const confidence = data.confidence_score || 50;
  const metrics = data.metrics || {};

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3
            className="text-sm font-semibold text-gray-400 uppercase tracking-wider cursor-help"
            onClick={() => onExplain?.('liquidity', score)}
            title="Click to learn more"
          >
            Liquidity Regime
          </h3>
          {data.data_stale && (
            <span className="text-orange-400" title={data.stale_reason || 'Data may be stale'}>⚠️</span>
          )}
        </div>
        <button
          onClick={() => setShowMetrics(!showMetrics)}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          {showMetrics ? 'Hide Metrics' : 'Show Metrics'}
        </button>
      </div>

      {/* Main Display */}
      <div className="flex items-center gap-4 mb-3">
        {/* Score Badge */}
        <div
          className="px-3 py-2 rounded-lg text-center"
          style={{ backgroundColor: `${regimeConfig.color}20`, borderColor: regimeConfig.color, borderWidth: 1 }}
        >
          <div className="text-2xl font-bold text-white">{score.toFixed(0)}</div>
          <div className="text-xs" style={{ color: regimeConfig.color }}>
            {regimeConfig.emoji} {regimeConfig.label}
          </div>
        </div>

        {/* Description */}
        <div className="flex-1">
          <p className="text-sm text-gray-300">{regimeConfig.description}</p>
          <div className="text-xs text-gray-500 mt-1">
            Confidence: {confidence.toFixed(0)}%
            {data.completeness && data.completeness < 1 && (
              <span className="ml-2 text-yellow-500">
                ({(data.completeness * 100).toFixed(0)}% data available)
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Score Bar */}
      <div className="relative h-2 bg-gray-700 rounded-full overflow-hidden mb-2">
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
          style={{
            width: `${score}%`,
            background: `linear-gradient(to right, #22c55e 0%, #eab308 50%, #dc2626 100%)`,
          }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-1 h-4 bg-white rounded shadow"
          style={{ left: `${score}%`, transform: 'translate(-50%, -50%)' }}
        />
      </div>
      <div className="flex justify-between text-xs text-gray-500">
        <span>Expanding</span>
        <span>Contracting</span>
      </div>

      {/* Top Drivers */}
      {data.drivers && data.drivers.length > 0 && (
        <div className="mt-4 pt-3 border-t border-gray-700">
          <div className="text-xs text-gray-500 mb-2">Key Drivers</div>
          <div className="space-y-1">
            {data.drivers.slice(0, 3).map((driver, idx) => (
              <div key={idx} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <span className={driver.direction === 'bearish' ? 'text-red-400' : 'text-green-400'}>
                    {driver.direction === 'bearish' ? '↑' : '↓'}
                  </span>
                  <span className="text-gray-300">
                    {metricLabels[driver.name]?.label || driver.name}
                  </span>
                </div>
                <span className="text-gray-400 text-xs font-mono">
                  {driver.contribution > 0 ? '+' : ''}{driver.contribution?.toFixed(1)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Metrics Detail */}
      {showMetrics && metrics && Object.keys(metrics).length > 0 && (
        <div className="mt-4 pt-3 border-t border-gray-700">
          <div className="text-xs text-gray-500 mb-2">Metrics</div>
          <div className="space-y-2">
            {Object.entries(metrics).map(([key, metric]) => {
              const meta = metricLabels[key] || { label: key, tooltip: '' };
              const isMonetary = ['fed_balance_sheet', 'rrp', 'tga'].includes(key);

              return (
                <div key={key} className="flex items-center justify-between text-sm" title={meta.tooltip}>
                  <span className="text-gray-400">{meta.label}</span>
                  <div className="text-right">
                    {metric.available !== false ? (
                      <>
                        <span className="text-white font-mono">
                          {isMonetary ? formatLargeNumber(metric.value) : metric.value?.toFixed(2)}
                        </span>
                        {metric.change_1w !== null && (
                          <span className={`ml-2 text-xs ${
                            metric.change_1w >= 0 ? 'text-green-400' : 'text-red-400'
                          }`}>
                            {formatChange(metric.change_1w, isMonetary)}
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-gray-600">N/A</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {data.as_of && (
        <div className="mt-2 text-xs text-gray-500 text-right">
          Data as of: {new Date(data.as_of).toLocaleDateString()}
        </div>
      )}
    </div>
  );
}
