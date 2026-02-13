/**
 * Catalyst Feed - Combined news, events, and earnings feed
 */
import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';

const ImpactBadge = ({ impact }) => {
  const colors = {
    high: 'bg-red-500/20 text-red-400 border-red-500/30',
    medium: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    low: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  };

  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${colors[impact] || colors.low}`}>
      {impact?.toUpperCase()}
    </span>
  );
};

const CategoryFilter = ({ selected, onChange }) => {
  const categories = [
    { value: 'all', label: 'All' },
    { value: 'economic', label: '🏛️ Economic' },
    { value: 'earnings', label: '💼 Earnings' },
    { value: 'news', label: '📰 News' },
    { value: 'fed', label: '🏦 Fed' },
  ];

  return (
    <div className="flex gap-1 overflow-x-auto pb-2">
      {categories.map((cat) => (
        <button
          key={cat.value}
          onClick={() => onChange(cat.value)}
          className={`px-3 py-1 text-xs rounded-full whitespace-nowrap transition-colors ${
            selected === cat.value
              ? 'bg-blue-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          {cat.label}
        </button>
      ))}
    </div>
  );
};

const FeedItem = ({ item, onClick }) => {
  const formatTime = (datetime) => {
    if (!datetime) return '';
    try {
      const date = new Date(datetime);
      return formatDistanceToNow(date, { addSuffix: true });
    } catch {
      return datetime;
    }
  };

  return (
    <div
      className="flex items-start gap-3 py-3 px-3 bg-gray-700/30 rounded-lg hover:bg-gray-700/50 cursor-pointer transition-colors"
      onClick={() => onClick?.(item)}
    >
      <span className="text-xl mt-0.5">{item.icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="text-sm text-white font-medium line-clamp-2">
            {item.title}
          </div>
          <ImpactBadge impact={item.impact} />
        </div>
        <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
          <span>{item.subtitle}</span>
          {item.datetime && (
            <>
              <span>•</span>
              <span>{formatTime(item.datetime)}</span>
            </>
          )}
        </div>
        {item.symbols && item.symbols.length > 0 && (
          <div className="flex gap-1 mt-1">
            {item.symbols.slice(0, 3).map((symbol) => (
              <span
                key={symbol}
                className="text-xs px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded"
              >
                ${symbol}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default function CatalystFeed({ data, loading, onItemClick, onRefresh }) {
  const [filter, setFilter] = useState('all');

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-16 bg-gray-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  const feed = data?.feed || [];
  const summary = data?.summary || {};

  // Filter feed items
  const filteredFeed = filter === 'all'
    ? feed
    : feed.filter((item) => item.type === filter || item.category === filter);

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
          <span>📅</span> Catalyst Feed
        </h3>
        <div className="flex items-center gap-2">
          {summary.high_impact_news > 0 && (
            <span className="text-xs px-2 py-0.5 bg-red-500/20 text-red-400 rounded">
              {summary.high_impact_news} High Impact
            </span>
          )}
          <button
            onClick={onRefresh}
            className="text-gray-400 hover:text-white transition-colors p-1"
            title="Refresh"
          >
            🔄
          </button>
        </div>
      </div>

      {/* Filter */}
      <CategoryFilter selected={filter} onChange={setFilter} />

      {/* Feed Items */}
      <div className="space-y-2 mt-3 max-h-[400px] overflow-y-auto">
        {filteredFeed.length > 0 ? (
          filteredFeed.map((item, idx) => (
            <FeedItem
              key={`${item.type}-${idx}`}
              item={item}
              onClick={onItemClick}
            />
          ))
        ) : (
          <div className="text-gray-500 text-sm text-center py-8">
            No catalysts found for this filter
          </div>
        )}
      </div>

      {/* Summary Footer */}
      {(summary.upcoming_events > 0 || summary.upcoming_earnings > 0) && (
        <div className="mt-4 pt-3 border-t border-gray-700 flex items-center justify-between text-xs text-gray-400">
          <span>
            {summary.upcoming_events} economic events this week
          </span>
          <span>
            {summary.upcoming_earnings} earnings upcoming
          </span>
        </div>
      )}
    </div>
  );
}
