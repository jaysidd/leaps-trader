/**
 * SentimentCard Component
 *
 * Full sentiment display card combining:
 * - Overall sentiment score
 * - Component breakdown
 * - News headlines
 * - Insider activity
 * - Catalyst timing
 */
import React, { useState, useEffect } from 'react';
import { sentimentAPI } from '../../api/sentiment';
import { SentimentBadge, SentimentBreakdown } from './SentimentBadge';
import { CatalystPanel } from './CatalystPanel';

export const SentimentCard = ({
  symbol,
  companyName = null,
  showNews = true,
  showInsiders = true,
  showCatalysts = true,
  className = ''
}) => {
  const [sentiment, setSentiment] = useState(null);
  const [news, setNews] = useState(null);
  const [insiders, setInsiders] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    if (symbol) {
      loadData();
    }
  }, [symbol]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Load sentiment data
      const sentimentData = await sentimentAPI.getSentiment(symbol, companyName);
      setSentiment(sentimentData);

      // Load news if enabled
      if (showNews) {
        try {
          const newsData = await sentimentAPI.getNews(symbol, 5);
          setNews(newsData);
        } catch (e) {
          console.error('Failed to load news:', e);
        }
      }

      // Load insider trades if enabled
      if (showInsiders) {
        try {
          const insiderData = await sentimentAPI.getInsiderTrades(symbol);
          setInsiders(insiderData);
        } catch (e) {
          console.error('Failed to load insiders:', e);
        }
      }

    } catch (err) {
      setError('Failed to load sentiment data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className={`animate-pulse bg-white rounded-lg border p-6 ${className}`}>
        <div className="h-8 bg-gray-200 rounded w-1/2 mb-4"></div>
        <div className="space-y-3">
          <div className="h-4 bg-gray-200 rounded w-full"></div>
          <div className="h-4 bg-gray-200 rounded w-3/4"></div>
          <div className="h-4 bg-gray-200 rounded w-5/6"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`bg-red-50 text-red-600 rounded-lg border border-red-200 p-4 ${className}`}>
        <p>{error}</p>
        <button
          onClick={loadData}
          className="mt-2 text-sm underline hover:no-underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!sentiment) return null;

  const tabs = [
    { id: 'overview', label: 'Overview' },
    ...(showNews && news?.news?.length ? [{ id: 'news', label: 'News' }] : []),
    ...(showInsiders && insiders?.trades?.length ? [{ id: 'insiders', label: 'Insiders' }] : []),
    ...(showCatalysts ? [{ id: 'catalysts', label: 'Catalysts' }] : [])
  ];

  return (
    <div className={`bg-white rounded-lg border shadow-sm overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="font-semibold text-lg text-gray-900">{symbol}</h3>
          <SentimentBadge
            score={sentiment.overall_score}
            label={sentiment.sentiment_label}
          />
        </div>
        <button
          onClick={loadData}
          className="text-gray-400 hover:text-gray-600 p-1"
          title="Refresh"
        >
          🔄
        </button>
      </div>

      {/* Tabs */}
      {tabs.length > 1 && (
        <div className="flex border-b">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'text-blue-600 border-b-2 border-blue-600'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      <div className="p-4">
        {activeTab === 'overview' && (
          <div className="space-y-4">
            {/* Sentiment Breakdown */}
            <SentimentBreakdown
              scores={sentiment.scores}
              flags={sentiment.flags}
            />

            {/* Signals */}
            <div className="grid grid-cols-2 gap-4">
              {sentiment.signals?.bullish?.length > 0 && (
                <div className="p-3 bg-green-50 rounded-lg">
                  <div className="text-xs text-green-600 uppercase tracking-wide mb-2">
                    Bullish Signals
                  </div>
                  <ul className="space-y-1">
                    {sentiment.signals.bullish.map((signal, i) => (
                      <li key={i} className="text-sm text-green-800 flex items-start gap-2">
                        <span>✓</span>
                        <span>{signal}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {sentiment.signals?.bearish?.length > 0 && (
                <div className="p-3 bg-red-50 rounded-lg">
                  <div className="text-xs text-red-600 uppercase tracking-wide mb-2">
                    Bearish Signals
                  </div>
                  <ul className="space-y-1">
                    {sentiment.signals.bearish.map((signal, i) => (
                      <li key={i} className="text-sm text-red-800 flex items-start gap-2">
                        <span>✗</span>
                        <span>{signal}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Recommendation */}
            {sentiment.recommendation && (
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <div className="text-sm text-blue-800">
                  💡 {sentiment.recommendation}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'news' && news && (
          <div className="space-y-3">
            {news.news.map((item, i) => (
              <a
                key={i}
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <span className={
                    item.sentiment_label === 'bullish' ? 'text-green-500' :
                    item.sentiment_label === 'bearish' ? 'text-red-500' : 'text-gray-400'
                  }>
                    {item.sentiment_label === 'bullish' ? '📈' :
                     item.sentiment_label === 'bearish' ? '📉' : '📰'}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 line-clamp-2">
                      {item.title}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      {item.source} • {new Date(item.published).toLocaleDateString()}
                    </div>
                  </div>
                </div>
              </a>
            ))}
          </div>
        )}

        {activeTab === 'insiders' && insiders && (
          <div className="space-y-4">
            {/* Summary */}
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="p-2 bg-green-50 rounded">
                <div className="text-lg font-bold text-green-600">
                  {insiders.summary.total_buys}
                </div>
                <div className="text-xs text-green-700">Buys</div>
              </div>
              <div className="p-2 bg-red-50 rounded">
                <div className="text-lg font-bold text-red-600">
                  {insiders.summary.total_sells}
                </div>
                <div className="text-xs text-red-700">Sells</div>
              </div>
              <div className={`p-2 rounded ${
                insiders.summary.signal === 'bullish' ? 'bg-green-100' :
                insiders.summary.signal === 'bearish' ? 'bg-red-100' : 'bg-gray-100'
              }`}>
                <div className="text-lg font-bold capitalize">
                  {insiders.summary.net_activity}
                </div>
                <div className="text-xs">Net Activity</div>
              </div>
            </div>

            {/* Recent Trades */}
            <div className="space-y-2">
              {insiders.trades.slice(0, 5).map((trade, i) => (
                <div key={i} className="flex items-center gap-3 p-2 bg-gray-50 rounded">
                  <span className={trade.trade_type === 'buy' ? 'text-green-500' : 'text-red-500'}>
                    {trade.trade_type === 'buy' ? '⬆️' : '⬇️'}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{trade.insider_name}</div>
                    <div className="text-xs text-gray-500">{trade.title}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium">
                      ${(trade.value / 1000).toFixed(0)}K
                    </div>
                    <div className="text-xs text-gray-500">
                      {trade.shares.toLocaleString()} shares
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'catalysts' && (
          <CatalystPanel symbol={symbol} showRecommendation />
        )}
      </div>
    </div>
  );
};

export default SentimentCard;
