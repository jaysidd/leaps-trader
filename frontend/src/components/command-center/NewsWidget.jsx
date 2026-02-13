/**
 * News Widget - Shows aggregated financial news from RSS feeds
 * Sources: CNBC, Yahoo Finance, MarketWatch, Reuters, Investing.com
 */
import { useState } from 'react';

// Format time ago
const formatTimeAgo = (dateString) => {
  if (!dateString) return '';

  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return '';
  }
};

// Get category badge color
const getCategoryColor = (category) => {
  const colors = {
    markets: 'bg-blue-500/20 text-blue-400',
    investing: 'bg-green-500/20 text-green-400',
    stocks: 'bg-purple-500/20 text-purple-400',
    business: 'bg-yellow-500/20 text-yellow-400',
    general: 'bg-gray-500/20 text-gray-400',
  };
  return colors[category] || colors.general;
};

// News item component
const NewsItem = ({ item, onClick }) => {
  return (
    <div
      className="group p-3 rounded-lg hover:bg-gray-700/50 cursor-pointer transition-colors border-b border-gray-700/50 last:border-b-0"
      onClick={() => onClick?.(item)}
    >
      <div className="flex items-start gap-3">
        {/* Source icon */}
        <div className="flex-shrink-0 mt-0.5">
          <span className="text-lg">{item.source_icon || '📰'}</span>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Title */}
          <h4 className="text-sm text-white font-medium line-clamp-2 group-hover:text-blue-400 transition-colors">
            {item.title}
          </h4>

          {/* Meta info */}
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-gray-500">{item.source}</span>
            <span className="text-gray-600">•</span>
            <span className="text-xs text-gray-500">{formatTimeAgo(item.published_at)}</span>
            {item.category && (
              <>
                <span className="text-gray-600">•</span>
                <span className={`text-xs px-1.5 py-0.5 rounded ${getCategoryColor(item.category)}`}>
                  {item.category}
                </span>
              </>
            )}
          </div>

          {/* Summary preview on hover */}
          {item.summary && (
            <p className="text-xs text-gray-400 mt-1 line-clamp-2 opacity-0 group-hover:opacity-100 transition-opacity">
              {item.summary}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default function NewsWidget({ data, loading, onNewsClick }) {
  const [showAll, setShowAll] = useState(false);
  const [filter, setFilter] = useState('all');

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex gap-3">
              <div className="w-6 h-6 bg-gray-700 rounded"></div>
              <div className="flex-1 space-y-2">
                <div className="h-4 bg-gray-700 rounded w-full"></div>
                <div className="h-3 bg-gray-700 rounded w-2/3"></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const newsItems = data || [];

  // Filter news
  const filteredNews = filter === 'all'
    ? newsItems
    : newsItems.filter((item) => item.category === filter);

  // Handle news click - open in new tab
  const handleNewsClick = (item) => {
    if (item.url) {
      window.open(item.url, '_blank', 'noopener,noreferrer');
    }
    onNewsClick?.(item);
  };

  // Get unique categories
  const categories = [...new Set(newsItems.map((item) => item.category).filter(Boolean))];

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
          <span>📰</span> Financial News
        </h3>
        <span className="text-xs text-gray-500">
          {newsItems.length} articles
        </span>
      </div>

      {/* Filter tabs */}
      {categories.length > 1 && (
        <div className="flex gap-1 mb-3 overflow-x-auto pb-1">
          <button
            onClick={() => setFilter('all')}
            className={`px-2 py-1 text-xs rounded-md whitespace-nowrap transition-colors ${
              filter === 'all'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-400 hover:text-white'
            }`}
          >
            All
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              className={`px-2 py-1 text-xs rounded-md whitespace-nowrap capitalize transition-colors ${
                filter === cat
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:text-white'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      )}

      {/* News list */}
      <div className="space-y-0 max-h-[400px] overflow-y-auto">
        {filteredNews.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <span className="text-2xl mb-2 block">📭</span>
            <p className="text-sm">No news available</p>
          </div>
        ) : (
          <>
            {(showAll ? filteredNews : filteredNews.slice(0, 6)).map((item, idx) => (
              <NewsItem
                key={`${item.url}-${idx}`}
                item={item}
                onClick={handleNewsClick}
              />
            ))}
          </>
        )}
      </div>

      {/* Show more/less */}
      {filteredNews.length > 6 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="mt-3 w-full text-center text-xs text-gray-400 hover:text-gray-300 py-2 border-t border-gray-700"
        >
          {showAll ? 'Show Less' : `Show ${filteredNews.length - 6} More`}
        </button>
      )}

      {/* Source attribution */}
      <div className="mt-3 pt-3 border-t border-gray-700 text-center">
        <span className="text-xs text-gray-500">
          Sources: CNBC, Yahoo Finance, MarketWatch, Reuters
        </span>
      </div>
    </div>
  );
}
