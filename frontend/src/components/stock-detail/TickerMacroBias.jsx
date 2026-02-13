/**
 * Ticker Macro Bias Component
 * Shows macro bias overlay for a specific ticker based on sector weights
 */
import { useState, useEffect } from 'react';
import { getTickerMacroBias } from '../../api/commandCenter';

const getBiasConfig = (bias, score) => {
  if (bias === 'bullish' || score < 40) {
    return { label: 'Bullish', color: '#22c55e', bgClass: 'bg-green-500', textClass: 'text-green-400' };
  } else if (bias === 'bearish' || score > 60) {
    return { label: 'Bearish', color: '#dc2626', bgClass: 'bg-red-500', textClass: 'text-red-400' };
  }
  return { label: 'Neutral', color: '#eab308', bgClass: 'bg-yellow-500', textClass: 'text-yellow-400' };
};

const CATEGORY_LABELS = {
  fed_policy: 'Fed Policy',
  recession: 'Recession',
  elections: 'Elections',
  trade: 'Trade',
  crypto: 'Crypto',
  markets: 'Markets',
};

export default function TickerMacroBias({ symbol, compact = false }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    const fetchBias = async () => {
      if (!symbol) return;

      setLoading(true);
      setError(null);

      try {
        const response = await getTickerMacroBias(symbol);
        setData(response);
      } catch (err) {
        console.error('Error fetching ticker bias:', err);
        setError('Unable to load macro bias');
      } finally {
        setLoading(false);
      }
    };

    fetchBias();
  }, [symbol]);

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-3 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/2 mb-2"></div>
        <div className="h-8 bg-gray-700 rounded"></div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-gray-800 rounded-lg p-3">
        <div className="text-xs text-gray-500">Macro bias unavailable</div>
      </div>
    );
  }

  const biasConfig = getBiasConfig(data.bias_label, data.bias_score);
  const score = data.bias_score || 50;

  // Compact mode for inline display
  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-400">Macro:</span>
        <span className={`text-xs font-semibold ${biasConfig.textClass}`}>
          {biasConfig.label}
        </span>
        <span className="text-xs text-gray-500">({score.toFixed(0)})</span>
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          Macro Bias
        </h3>
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="text-xs text-gray-500 hover:text-gray-300"
        >
          {showDetails ? 'Hide' : 'Why?'}
        </button>
      </div>

      {/* Main Display */}
      <div className="flex items-center gap-4">
        {/* Score Badge */}
        <div
          className="w-16 h-16 rounded-full flex items-center justify-center border-3"
          style={{ borderColor: biasConfig.color, borderWidth: '3px' }}
        >
          <div className="text-center">
            <div className="text-xl font-bold text-white">{score.toFixed(0)}</div>
          </div>
        </div>

        {/* Label and Info */}
        <div className="flex-1">
          <div className={`font-semibold text-lg ${biasConfig.textClass}`}>
            {biasConfig.label}
          </div>
          <div className="text-xs text-gray-400">
            {data.sector || 'Unknown Sector'}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Based on {data.sector} sector weights
          </div>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mt-3">
        <div className="relative h-2 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
            style={{
              width: `${score}%`,
              background: `linear-gradient(to right, #22c55e, #eab308, #dc2626)`,
            }}
          />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-0.5 h-3 bg-white rounded"
            style={{ left: `${score}%`, transform: 'translate(-50%, -50%)' }}
          />
        </div>
        <div className="flex justify-between mt-1 text-xs text-gray-500">
          <span>Bullish</span>
          <span>Bearish</span>
        </div>
      </div>

      {/* Details Section */}
      {showDetails && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          {/* Category Weights */}
          {data.weights && (
            <div className="mb-4">
              <div className="text-xs text-gray-500 mb-2">Sector Weights</div>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(data.weights).map(([category, weight]) => (
                  weight > 0 && (
                    <div key={category} className="flex justify-between text-xs">
                      <span className="text-gray-400">{CATEGORY_LABELS[category] || category}</span>
                      <span className="text-white">{(weight * 100).toFixed(0)}%</span>
                    </div>
                  )
                ))}
              </div>
            </div>
          )}

          {/* Category Contributions */}
          {data.category_contributions && data.category_contributions.length > 0 && (
            <div>
              <div className="text-xs text-gray-500 mb-2">Score Breakdown</div>
              <div className="space-y-2">
                {data.category_contributions.map((contrib, idx) => (
                  <div key={idx} className="text-xs">
                    <div className="flex justify-between mb-1">
                      <span className="text-gray-400">
                        {CATEGORY_LABELS[contrib.category] || contrib.category}
                      </span>
                      <span className={`font-mono ${
                        contrib.risk_score > 66 ? 'text-red-400' :
                        contrib.risk_score < 33 ? 'text-green-400' : 'text-yellow-400'
                      }`}>
                        {contrib.risk_score?.toFixed(0)} × {(contrib.weight * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="h-1 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${contrib.risk_score || 0}%`,
                          background: contrib.risk_score > 66 ? '#dc2626' :
                                     contrib.risk_score < 33 ? '#22c55e' : '#eab308'
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Top Driver */}
          {data.top_driver && (
            <div className="mt-3 p-2 bg-gray-700/50 rounded text-xs">
              <span className="text-gray-400">Top Driver: </span>
              <span className="text-white">
                {CATEGORY_LABELS[data.top_driver.category] || data.top_driver.category}
              </span>
              <span className="text-gray-400">
                {' '}contributing {data.top_driver.contribution?.toFixed(1)} points
              </span>
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
