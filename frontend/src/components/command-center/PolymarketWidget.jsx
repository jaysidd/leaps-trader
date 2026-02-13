/**
 * Polymarket Widget - Shows prediction market odds
 */
import { useState } from 'react';

const getCategoryIcon = (category) => {
  const icons = {
    fed_policy: '🏛️',
    elections: '🗳️',
    economic: '📉',
    crypto: '₿',
    trade: '🌐',
    markets: '📈',
    other: '📊',
  };
  return icons[category] || '📊';
};

const ChangeIndicator = ({ change }) => {
  if (change === null || change === undefined) return null;

  const isPositive = change > 0;
  const color = isPositive ? 'text-green-400' : 'text-red-400';
  const arrow = isPositive ? '▲' : '▼';

  return (
    <span className={`text-xs ${color}`}>
      {arrow} {Math.abs(change).toFixed(1)}%
    </span>
  );
};

const MarketItem = ({ item, onClick }) => {
  return (
    <div
      className="flex items-center justify-between py-2 px-3 bg-gray-700/50 rounded-lg hover:bg-gray-700 cursor-pointer transition-colors"
      onClick={onClick}
    >
      <div className="flex items-center gap-2">
        <span className="text-lg">{item.icon}</span>
        <div>
          <div className="text-sm text-white font-medium">{item.label}</div>
        </div>
      </div>
      <div className="text-right">
        <div className="text-white font-bold">{item.value}</div>
        <ChangeIndicator change={item.change} />
      </div>
    </div>
  );
};

const SignificantChange = ({ change }) => {
  const color = change.direction === 'up' ? 'text-green-400' : 'text-red-400';
  const bgColor = change.direction === 'up' ? 'bg-green-500/10' : 'bg-red-500/10';

  return (
    <div className={`${bgColor} rounded-lg p-2 border border-gray-700`}>
      <div className="flex items-center gap-2">
        <span>{change.emoji}</span>
        <div className="flex-1 min-w-0">
          <div className="text-xs text-white truncate">{change.title}</div>
          <div className={`text-xs ${color}`}>
            {change.current_odds}% ({change.change_24h > 0 ? '+' : ''}{change.change_24h}%)
          </div>
        </div>
      </div>
    </div>
  );
};

export default function PolymarketWidget({ data, loading, onMarketClick }) {
  const [showAll, setShowAll] = useState(false);

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/2 mb-4"></div>
        <div className="space-y-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-12 bg-gray-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  const items = data?.items || [];
  const significantChanges = data?.significant_changes || [];

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
          <span>🎰</span> Prediction Markets
        </h3>
        <a
          href="https://polymarket.com"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-400 hover:text-blue-300"
        >
          Polymarket →
        </a>
      </div>

      {/* Key Markets */}
      <div className="space-y-2 mb-4">
        {items.map((item, idx) => (
          <MarketItem
            key={idx}
            item={item}
            onClick={() => onMarketClick?.(item)}
          />
        ))}
      </div>

      {/* Significant Changes Alert */}
      {significantChanges.length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-gray-400 uppercase">
              24h Movers
            </h4>
            <span className="text-xs text-orange-400">
              {significantChanges.length} significant
            </span>
          </div>
          <div className="space-y-2">
            {significantChanges.slice(0, showAll ? undefined : 3).map((change, idx) => (
              <SignificantChange key={idx} change={change} />
            ))}
          </div>
          {significantChanges.length > 3 && (
            <button
              onClick={() => setShowAll(!showAll)}
              className="mt-2 text-xs text-gray-400 hover:text-gray-300 w-full text-center"
            >
              {showAll ? 'Show Less' : `Show ${significantChanges.length - 3} More`}
            </button>
          )}
        </div>
      )}

      {items.length === 0 && (
        <div className="text-gray-500 text-sm text-center py-4">
          No prediction market data available
        </div>
      )}
    </div>
  );
}
