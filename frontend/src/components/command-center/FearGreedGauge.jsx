/**
 * Fear & Greed Index Gauge
 * Visual representation of CNN Fear & Greed Index
 */
import { useState } from 'react';

const getRatingConfig = (value) => {
  if (value <= 25) {
    return { label: 'Extreme Fear', color: '#dc2626', bgColor: 'bg-red-600', emoji: '😱' };
  } else if (value <= 45) {
    return { label: 'Fear', color: '#f97316', bgColor: 'bg-orange-500', emoji: '😰' };
  } else if (value <= 55) {
    return { label: 'Neutral', color: '#eab308', bgColor: 'bg-yellow-500', emoji: '😐' };
  } else if (value <= 75) {
    return { label: 'Greed', color: '#84cc16', bgColor: 'bg-lime-500', emoji: '😊' };
  } else {
    return { label: 'Extreme Greed', color: '#22c55e', bgColor: 'bg-green-500', emoji: '🤑' };
  }
};

export default function FearGreedGauge({ data, loading, onExplain }) {
  const [showDetails, setShowDetails] = useState(false);

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/2 mb-4"></div>
        <div className="h-24 bg-gray-700 rounded"></div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Fear & Greed
        </h3>
        <div className="text-gray-500 text-sm">Data unavailable</div>
      </div>
    );
  }

  const value = data.value || 50;
  const config = getRatingConfig(value);
  const previousClose = data.previous_close || value;
  const change = value - previousClose;

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3
          className="text-sm font-semibold text-gray-400 uppercase tracking-wider cursor-help"
          onClick={() => onExplain?.('fear_greed', value)}
          title="Click to learn more"
        >
          Fear & Greed
        </h3>
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          {showDetails ? 'Hide' : 'Details'}
        </button>
      </div>

      {/* Main Gauge Display */}
      <div className="flex items-center gap-4">
        {/* Score Circle */}
        <div className="relative">
          <div
            className="w-20 h-20 rounded-full flex items-center justify-center border-4"
            style={{ borderColor: config.color }}
          >
            <div className="text-center">
              <div className="text-2xl font-bold text-white">{value}</div>
              <div className="text-xs" style={{ color: config.color }}>
                {change > 0 ? '+' : ''}{change}
              </div>
            </div>
          </div>
        </div>

        {/* Label and Bar */}
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xl">{config.emoji}</span>
            <span className="font-semibold text-white">{config.label}</span>
          </div>

          {/* Progress Bar */}
          <div className="relative h-3 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
              style={{
                width: `${value}%`,
                background: `linear-gradient(to right, #dc2626, #f97316, #eab308, #84cc16, #22c55e)`,
              }}
            />
            {/* Marker */}
            <div
              className="absolute top-1/2 -translate-y-1/2 w-1 h-5 bg-white rounded shadow"
              style={{ left: `${value}%`, transform: 'translate(-50%, -50%)' }}
            />
          </div>

          {/* Labels */}
          <div className="flex justify-between mt-1 text-xs text-gray-500">
            <span>Fear</span>
            <span>Greed</span>
          </div>
        </div>
      </div>

      {/* Detailed Breakdown */}
      {showDetails && data.indicators && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(data.indicators).map(([key, value]) => (
              value !== null && (
                <div key={key} className="flex justify-between">
                  <span className="text-gray-400 capitalize">
                    {key.replace(/_/g, ' ')}
                  </span>
                  <span className="text-white">{value}</span>
                </div>
              )
            ))}
          </div>

          {/* Historical Comparison */}
          <div className="mt-3 pt-3 border-t border-gray-700">
            <div className="text-xs text-gray-500 mb-2">Historical</div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div>
                <div className="text-gray-400">1 Week Ago</div>
                <div className="text-white">{data.one_week_ago}</div>
              </div>
              <div>
                <div className="text-gray-400">1 Month Ago</div>
                <div className="text-white">{data.one_month_ago}</div>
              </div>
              <div>
                <div className="text-gray-400">1 Year Ago</div>
                <div className="text-white">{data.one_year_ago}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {data.is_fallback && (
        <div className="mt-2 text-xs text-gray-500 italic">
          * Estimated based on VIX
        </div>
      )}
    </div>
  );
}
