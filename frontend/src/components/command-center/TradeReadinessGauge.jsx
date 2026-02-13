/**
 * Trade Readiness Gauge
 * Visual representation of Trade Readiness Score with components and drivers
 * Shows partial status when Tier 2/3 catalysts are not yet implemented
 */
import { useState } from 'react';

const getReadinessConfig = (label, score) => {
  if (label === 'green' || score <= 33) {
    return { label: 'Risk-On', color: '#22c55e', bgColor: 'bg-green-500', emoji: '🟢' };
  } else if (label === 'yellow' || (score > 33 && score < 67)) {
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

export default function TradeReadinessGauge({ data, loading, onExplain, onViewDetails }) {
  const [showDetails, setShowDetails] = useState(false);

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/2 mb-4"></div>
        <div className="h-24 bg-gray-700 rounded"></div>
      </div>
    );
  }

  if (!data || !data.trade_readiness) {
    return (
      <div className="bg-gray-800 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Trade Readiness
        </h3>
        <div className="text-gray-500 text-sm">Data unavailable</div>
      </div>
    );
  }

  const readiness = data.trade_readiness;
  const score = readiness.score || 50;
  const label = readiness.label || 'yellow';
  const readinessConfig = getReadinessConfig(label, score);
  const confidence = data.overall_confidence || 50;
  const confidenceConfig = getConfidenceConfig(confidence);
  const isPartial = readiness.is_partial;

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3
            className="text-sm font-semibold text-gray-400 uppercase tracking-wider cursor-help"
            onClick={() => onExplain?.('trade_readiness', score)}
            title="Click to learn more"
          >
            Trade Readiness
          </h3>
          {isPartial && (
            <span
              className="text-blue-400 text-xs"
              title={readiness.partial_reason || 'Score is partial - some components not yet implemented'}
            >
              (Partial)
            </span>
          )}
          {data.data_stale && (
            <span className="text-orange-400" title="Data may be stale">⚠️</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            {showDetails ? 'Hide' : 'Details'}
          </button>
          {onViewDetails && (
            <button
              onClick={onViewDetails}
              className="text-xs text-blue-400 hover:text-blue-300"
            >
              View All →
            </button>
          )}
        </div>
      </div>

      {/* Main Gauge Display */}
      <div className="flex items-center gap-4">
        {/* Score Circle */}
        <div className="relative">
          <div
            className="w-20 h-20 rounded-full flex items-center justify-center border-4"
            style={{ borderColor: readinessConfig.color }}
          >
            <div className="text-center">
              <div className="text-2xl font-bold text-white">{score.toFixed(0)}</div>
              <div className="text-xs text-gray-400">
                {isPartial ? 'partial' : 'full'}
              </div>
            </div>
          </div>
        </div>

        {/* Label and Bar */}
        <div className="flex-1">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-xl">{readinessConfig.emoji}</span>
              <span className="font-semibold text-white">{readinessConfig.label}</span>
            </div>
            <div className={`text-xs ${confidenceConfig.color}`}>
              {confidenceConfig.icon} {confidence.toFixed(0)}% conf
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

      {/* Partial Warning */}
      {isPartial && (
        <div className="mt-3 p-2 bg-blue-900/30 border border-blue-600/50 rounded text-xs text-blue-300">
          📊 <strong>Partial Score:</strong> {readiness.partial_reason || 'Some catalysts pending implementation'}
        </div>
      )}

      {/* Details Section */}
      {showDetails && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          {/* Top Drivers */}
          {data.drivers && data.drivers.length > 0 && (
            <div className="mb-4">
              <div className="text-xs text-gray-500 mb-2">Top Drivers</div>
              <div className="space-y-2">
                {data.drivers.slice(0, 3).map((driver, idx) => (
                  <div key={idx} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <span className={
                        driver.direction === 'risk_off' || driver.direction === 'bearish'
                          ? 'text-red-400'
                          : driver.direction === 'neutral'
                            ? 'text-gray-400'
                            : 'text-green-400'
                      }>
                        {driver.direction === 'risk_off' || driver.direction === 'bearish'
                          ? '↑'
                          : driver.direction === 'neutral'
                            ? '→'
                            : '↓'}
                      </span>
                      <span className="text-gray-300">{driver.name}</span>
                    </div>
                    <span className="text-white font-mono ml-2">
                      {driver.value?.toFixed(1)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Component Scores */}
          {data.components && (
            <div>
              <div className="text-xs text-gray-500 mb-2">Components</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {Object.entries(data.components).map(([name, component]) => {
                  const componentScore = component?.score;
                  const available = component?.available !== false;
                  return (
                    <div key={name} className="flex justify-between items-center">
                      <span className="text-gray-400 capitalize">
                        {name.replace(/_/g, ' ')}
                      </span>
                      {available && componentScore !== null ? (
                        <span className={`font-mono ${
                          componentScore > 66 ? 'text-red-400' :
                          componentScore < 33 ? 'text-green-400' :
                          'text-yellow-400'
                        }`}>
                          {componentScore.toFixed(0)}
                        </span>
                      ) : (
                        <span className="text-gray-600 text-xs">N/A</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Confidence by Component */}
          {data.confidence_by_component && (
            <div className="mt-3 pt-3 border-t border-gray-700">
              <div className="text-xs text-gray-500 mb-2">Component Confidence</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {Object.entries(data.confidence_by_component).map(([name, conf]) => (
                  <div key={name} className="flex justify-between">
                    <span className="text-gray-400 capitalize">{name.replace(/_/g, ' ')}</span>
                    <span className={`font-mono ${
                      conf >= 70 ? 'text-green-400' :
                      conf >= 40 ? 'text-yellow-400' :
                      'text-gray-500'
                    }`}>
                      {conf > 0 ? `${conf.toFixed(0)}%` : '-'}
                    </span>
                  </div>
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
