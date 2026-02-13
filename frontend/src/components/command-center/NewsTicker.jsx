/**
 * News Ticker Banner
 * Scrolling banner displaying real-time financial news headlines
 * Uses CSS animation instead of requestAnimationFrame for better performance
 */
import { useState, useEffect, useRef, useMemo } from 'react';
import { API_BASE_URL } from '../../api/axios';

// Category icons for visual distinction
const CATEGORY_ICONS = {
  markets: '📈',
  investing: '💰',
  stocks: '📊',
  general: '📰',
  economy: '🏛️',
  crypto: '₿',
  default: '📌',
};

// Source colors for visual distinction
const SOURCE_COLORS = {
  'CNBC': 'text-yellow-400',
  'Yahoo Finance': 'text-purple-400',
  'MarketWatch': 'text-green-400',
  'Reuters': 'text-orange-400',
  'Investing.com': 'text-blue-400',
  'default': 'text-gray-400',
};

export default function NewsTicker({
  speed = 50,  // pixels per second
  pauseOnHover = true,
  showSource = true,
  maxItems = 20,
}) {
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const [error, setError] = useState(null);
  const [contentWidth, setContentWidth] = useState(0);
  const tickerRef = useRef(null);

  // Fetch news from API
  const fetchNews = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/command-center/news/rss/market?limit=${maxItems}`);
      if (!response.ok) throw new Error('Failed to fetch news');

      const data = await response.json();
      if (data.news && data.news.length > 0) {
        setNews(data.news);
        setError(null);
      }
    } catch (err) {
      console.error('Error fetching ticker news:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Initial fetch and refresh interval
  useEffect(() => {
    fetchNews();

    // Refresh news every 5 minutes
    const interval = setInterval(fetchNews, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [maxItems]);

  // Measure content width for CSS animation duration
  useEffect(() => {
    if (!tickerRef.current || news.length === 0) return;
    // Measure half the scrollWidth (since content is duplicated)
    const width = tickerRef.current.scrollWidth / 2;
    setContentWidth(width);
  }, [news]);

  // Calculate animation duration based on content width and speed
  const animationDuration = useMemo(() => {
    if (contentWidth === 0) return 30; // default fallback
    return contentWidth / speed;
  }, [contentWidth, speed]);

  const handleMouseEnter = () => {
    if (pauseOnHover) setIsPaused(true);
  };

  const handleMouseLeave = () => {
    if (pauseOnHover) setIsPaused(false);
  };

  const getTimeAgo = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${Math.floor(diffHours / 24)}d ago`;
  };

  const getCategoryIcon = (category) => {
    return CATEGORY_ICONS[category?.toLowerCase()] || CATEGORY_ICONS.default;
  };

  const getSourceColor = (source) => {
    return SOURCE_COLORS[source] || SOURCE_COLORS.default;
  };

  const handleNewsClick = (item) => {
    if (item.link) {
      window.open(item.link, '_blank', 'noopener,noreferrer');
    }
  };

  if (loading) {
    return (
      <div className="bg-gray-900 border-b border-gray-700 py-2 px-4">
        <div className="flex items-center gap-2">
          <span className="text-yellow-500 font-bold text-xs uppercase tracking-wider">LIVE</span>
          <div className="h-2 w-2 bg-red-500 rounded-full animate-pulse"></div>
          <span className="text-gray-400 text-sm">Loading market news...</span>
        </div>
      </div>
    );
  }

  if (error || news.length === 0) {
    return (
      <div className="bg-gray-900 border-b border-gray-700 py-2 px-4">
        <div className="flex items-center gap-2">
          <span className="text-yellow-500 font-bold text-xs uppercase tracking-wider">NEWS</span>
          <span className="text-gray-500 text-sm">
            {error ? 'Unable to load news feed' : 'No news available'}
          </span>
        </div>
      </div>
    );
  }

  // Duplicate news for seamless infinite scroll
  const duplicatedNews = [...news, ...news];

  return (
    <div
      className="bg-gradient-to-r from-gray-900 via-gray-800 to-gray-900 border-b border-gray-700 overflow-hidden"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* CSS keyframes for marquee animation */}
      <style>{`
        @keyframes ticker-scroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>

      <div className="flex items-center">
        {/* Fixed label */}
        <div className="flex-shrink-0 bg-red-600 px-3 py-2 flex items-center gap-2 z-10">
          <div className="h-2 w-2 bg-white rounded-full animate-pulse"></div>
          <span className="text-white font-bold text-xs uppercase tracking-wider">BREAKING</span>
        </div>

        {/* Scrolling content — CSS animation */}
        <div className="overflow-hidden flex-1">
          <div
            ref={tickerRef}
            className="flex items-center whitespace-nowrap py-2"
            style={{
              animation: `ticker-scroll ${animationDuration}s linear infinite`,
              animationPlayState: isPaused ? 'paused' : 'running',
              willChange: 'transform',
            }}
          >
            {duplicatedNews.map((item, index) => (
              <div
                key={`${item.title}-${index}`}
                className="inline-flex items-center gap-3 px-6 cursor-pointer hover:bg-gray-700/30 transition-colors"
                onClick={() => handleNewsClick(item)}
              >
                {/* Category icon */}
                <span className="text-lg">{getCategoryIcon(item.category)}</span>

                {/* Headline */}
                <span className="text-gray-100 text-sm font-medium">
                  {item.title}
                </span>

                {/* Source and time */}
                {showSource && (
                  <span className={`text-xs ${getSourceColor(item.source)}`}>
                    {item.source}
                  </span>
                )}
                <span className="text-gray-500 text-xs">
                  {getTimeAgo(item.published)}
                </span>

                {/* Separator */}
                <span className="text-gray-600 mx-2">|</span>
              </div>
            ))}
          </div>
        </div>

        {/* Pause indicator */}
        {isPaused && (
          <div className="flex-shrink-0 px-3 py-2 bg-gray-800/80">
            <span className="text-yellow-400 text-xs">Paused</span>
          </div>
        )}
      </div>
    </div>
  );
}
