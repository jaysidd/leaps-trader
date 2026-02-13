/**
 * Macro Risk Index (MRI) Gauge
 * Visual representation of MRI with regime, confidence, and drivers
 */
import { useState } from 'react';

const getRegimeConfig = (regime, score) => {
  if (regime === 'risk_on' || score <= 33) {
    return { label: 'Risk-On', color: '#22c55e', bgColor: 'bg-green-500', emoji: '🟢' };
  } else if (regime === 'transition' || (score > 33 && score < 67)) {
    return { label: 'Transition', color: '#eab308', bgColor: 'bg-yellow-500', emoji: '🟡' };
  } else {
    return { label: 'Risk-Off', color: '#dc2626', bgColor: 'bg-red-500', emoji: '🔴' };
  }
};

const getConfidenceConfig = (score) => {
  if (score >= 70) {
    return { label: 'High', color: 'text-green-400', icon: '✓' };
  } else if (score >= 40) {
    return { label: 'Medium', color: 'text-yellow-400', icon: '~' };
  } else {
    return { label: 'Low', color: 'text-red-400', icon: '⚠' };
  }
};

export default function MRIGauge({ data, loading, onExplain }) {
  const [showDetails, setShowDetails] = useState(false);

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/2 mb-4"></div>
        <div className="h-24 bg-gray-700 rounded"></div>
      </div>
    );
  }

  if (!data || data.mri_score === null) {
    return (
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Macro Risk Index
        </h3>
        <div className="text-gray-500 text-sm">Data unavailable</div>
      </div>
    );
  }

  const score = data.mri_score || 50;
  const regime = data.regime || 'transition';
  const regimeConfig = getRegimeConfig(regime, score);
  const confidenceScore = data.confidence_score || 50;
  const confidenceConfig = getConfidenceConfig(confidenceScore);
  const change24h = data.change_24h || 0;

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3
            className="text-sm font-semibold text-gray-400 uppercase tracking-wider cursor-help"
            onClick={() => onExplain?.('mri', score)}
            title="Click to learn more"
          >
            Macro Risk Index
          </h3>
          {data.shock_flag && (
            <span className="text-yellow-400 animate-pulse" title="Shock Detected">⚡</span>
          )}
          {data.data_stale && (
            <span className="text-orange-400" title="Data may be stale">⚠️</span>
          )}
        </div>
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          {showDetails ? 'Hide' : 'Why?'}
        </button>
      </div>

      {/* Main Gauge Display */}
      <div className="flex items-center gap-4">
        {/* Score Circle */}
        <div className="relative">
          <div
            className="w-20 h-20 rounded-full flex items-center justify-center border-4"
            style={{ borderColor: regimeConfig.color }}
          >
            <div className="text-center">
              <div className="text-2xl font-bold text-white">{score.toFixed(0)}</div>
              <div className="text-xs" style={{ color: regimeConfig.color }}>
                {change24h !== 0 && (change24h > 0 ? '+' : '')}{change24h.toFixed(1)}
              </div>
            </div>
          </div>
        </div>

        {/* Label and Bar */}
        <div className="flex-1">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-xl">{regimeConfig.emoji}</span>
              <span className="font-semibold text-white">{regimeConfig.label}</span>
            </div>
            <div className={`text-xs ${confidenceConfig.color}`}>
              {confidenceConfig.icon} {confidenceScore.toFixed(0)}% conf
            </div>
          </div>

          {/* Progress Bar - Risk gradient (green to red) */}
          <div className="relative h-3 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
              style={{
                width: `${score}%`,
                background: `linear-gradient(to right, #22c55e, #84cc16, #eab308, #f97316, #dc2626)`,
              }}
            />
            {/* Marker */}
            <div
              className="absolute top-1/2 -translate-y-1/2 w-1 h-5 bg-white rounded shadow"
              style={{ left: `${score}%`, transform: 'translate(-50%, -50%)' }}
            />
          </div>

          {/* Labels */}
          <div className="flex justify-between mt-1 text-xs text-gray-500">
            <span>Risk-On</span>
            <span>Risk-Off</span>
          </div>
        </div>
      </div>

      {/* Shock Alert */}
      {data.shock_flag && (
        <div className="mt-3 p-2 bg-yellow-900/30 border border-yellow-600/50 rounded text-sm text-yellow-300">
          ⚡ <strong>Shock Detected:</strong> Rapid change in macro conditions
        </div>
      )}

      {/* Top Drivers - "Why?" Section */}
      {showDetails && data.drivers && data.drivers.length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          <div className="text-xs text-gray-500 mb-2">Top Drivers</div>
          <div className="space-y-2">
            {data.drivers.slice(0, 3).map((driver, idx) => (
              <div key={idx} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <span className={driver.direction === 'risk_off' ? 'text-red-400' : 'text-green-400'}>
                    {driver.direction === 'risk_off' ? '↑' : '↓'}
                  </span>
                  <span className="text-gray-300 truncate" title={driver.title}>
                    {driver.title?.slice(0, 40)}{driver.title?.length > 40 ? '...' : ''}
                  </span>
                </div>
                <span className="text-white font-mono ml-2">
                  +{driver.contribution_points?.toFixed(1)}
                </span>
              </div>
            ))}
          </div>

          {/* Component Scores */}
          {data.components && (
            <div className="mt-3 pt-3 border-t border-gray-700">
              <div className="text-xs text-gray-500 mb-2">Category Scores</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {Object.entries(data.components).map(([category, score]) => (
                  score !== null && (
                    <div key={category} className="flex justify-between">
                      <span className="text-gray-400 capitalize">
                        {category.replace(/_/g, ' ')}
                      </span>
                      <span className={`font-mono ${
                        score > 66 ? 'text-red-400' : score < 33 ? 'text-green-400' : 'text-yellow-400'
                      }`}>
                        {score.toFixed(0)}
                      </span>
                    </div>
                  )
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {data.calculated_at && (
        <div className="mt-2 text-xs text-gray-500 text-right">
          Updated: {new Date(data.calculated_at).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
