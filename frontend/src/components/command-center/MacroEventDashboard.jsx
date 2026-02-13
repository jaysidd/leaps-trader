/**
 * Macro Event Dashboard
 * Displays prediction markets by category with quality scores and aggregates
 */
import { useState, useEffect } from 'react';
import { getMacroEvents, getMacroEventsByCategory } from '../../api/commandCenter';

const CATEGORIES = [
  { id: 'all', label: 'All', emoji: '📊' },
  { id: 'fed_policy', label: 'Fed Policy', emoji: '🏛️' },
  { id: 'recession', label: 'Recession', emoji: '📉' },
  { id: 'elections', label: 'Elections', emoji: '🗳️' },
  { id: 'trade', label: 'Trade', emoji: '🌐' },
  { id: 'crypto', label: 'Crypto', emoji: '₿' },
];

const getQualityColor = (score) => {
  if (score >= 0.8) return 'text-green-400';
  if (score >= 0.5) return 'text-yellow-400';
  return 'text-red-400';
};

const getConfidenceIcon = (label) => {
  if (label === 'high') return '✓';
  if (label === 'medium') return '~';
  return '?';
};

function MarketCard({ market, expanded, onToggle }) {
  const qualityScore = market.quality_score || 0;
  const probability = market.primary_odds || market.implied_probability || 0;

  return (
    <div className="bg-gray-700/50 rounded-lg p-3 hover:bg-gray-700 transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs font-mono ${getQualityColor(qualityScore)}`}>
              Q:{(qualityScore * 100).toFixed(0)}
            </span>
            <span className="text-xs text-gray-500">
              {market.category?.replace(/_/g, ' ')}
            </span>
          </div>
          <h4
            className="text-sm text-white cursor-pointer hover:text-blue-400"
            onClick={onToggle}
            title={market.title}
          >
            {market.title?.slice(0, 60)}{market.title?.length > 60 ? '...' : ''}
          </h4>
        </div>
        <div className="text-right ml-3">
          <div className="text-lg font-bold text-white">
            {probability.toFixed(1)}%
          </div>
          {market.change_24h !== null && market.change_24h !== undefined && (
            <div className={`text-xs ${market.change_24h > 0 ? 'text-green-400' : market.change_24h < 0 ? 'text-red-400' : 'text-gray-400'}`}>
              {market.change_24h > 0 ? '+' : ''}{market.change_24h.toFixed(1)}%
            </div>
          )}
        </div>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-600 text-xs space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <span className="text-gray-400">Liquidity:</span>
              <span className="text-white ml-1">
                ${market.liquidity ? (market.liquidity / 1000).toFixed(0) + 'K' : 'N/A'}
              </span>
            </div>
            <div>
              <span className="text-gray-400">Volume:</span>
              <span className="text-white ml-1">
                ${market.volume ? (market.volume / 1000000).toFixed(1) + 'M' : 'N/A'}
              </span>
            </div>
          </div>
          {market.end_date && (
            <div>
              <span className="text-gray-400">Resolves:</span>
              <span className="text-white ml-1">
                {new Date(market.end_date).toLocaleDateString()}
              </span>
            </div>
          )}
          {market.url && (
            <a
              href={market.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300"
            >
              View on Polymarket →
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function CategoryAggregate({ aggregate }) {
  if (!aggregate || aggregate.aggregate_probability === null) {
    return null;
  }

  return (
    <div className="bg-gray-700/30 rounded-lg p-3 mb-4">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm text-gray-400">Category Aggregate</div>
        <div className="flex items-center gap-2">
          <span className={`text-xs ${
            aggregate.confidence_label === 'high' ? 'text-green-400' :
            aggregate.confidence_label === 'medium' ? 'text-yellow-400' : 'text-red-400'
          }`}>
            {getConfidenceIcon(aggregate.confidence_label)} {aggregate.confidence_score}% conf
          </span>
        </div>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold text-white">
          {aggregate.aggregate_probability.toFixed(1)}%
        </span>
        <span className="text-sm text-gray-400">
          ({aggregate.markets_used} markets)
        </span>
      </div>
      {aggregate.dispersion && (
        <div className="mt-2 text-xs text-gray-500">
          Range: {aggregate.dispersion.min}% - {aggregate.dispersion.max}%
          (σ {aggregate.dispersion.stddev})
        </div>
      )}
      {aggregate.key_market && (
        <div className="mt-2 text-xs">
          <span className="text-gray-400">Key Market:</span>
          <span className="text-gray-300 ml-1">
            {aggregate.key_market.title?.slice(0, 50)}...
          </span>
        </div>
      )}
    </div>
  );
}

export default function MacroEventDashboard({ initialData, loading: externalLoading }) {
  const [activeCategory, setActiveCategory] = useState('all');
  const [markets, setMarkets] = useState(initialData?.markets || []);
  const [aggregate, setAggregate] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expandedMarket, setExpandedMarket] = useState(null);
  const [sortBy, setSortBy] = useState('quality');

  useEffect(() => {
    if (initialData?.markets) {
      setMarkets(initialData.markets);
    }
  }, [initialData]);

  const fetchCategoryData = async (category) => {
    if (category === 'all') {
      setAggregate(null);
      if (initialData?.markets) {
        setMarkets(initialData.markets);
      }
      return;
    }

    setLoading(true);
    try {
      const response = await getMacroEventsByCategory(category);
      setMarkets(response.markets || []);
      setAggregate(response.aggregate || null);
    } catch (error) {
      console.error('Error fetching category data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCategoryChange = (category) => {
    setActiveCategory(category);
    setExpandedMarket(null);
    fetchCategoryData(category);
  };

  // Sort markets
  const sortedMarkets = [...markets].sort((a, b) => {
    if (sortBy === 'quality') {
      return (b.quality_score || 0) - (a.quality_score || 0);
    } else if (sortBy === 'volume') {
      return (b.volume || 0) - (a.volume || 0);
    } else if (sortBy === 'change') {
      return Math.abs(b.change_24h || 0) - Math.abs(a.change_24h || 0);
    }
    return 0;
  });

  const isLoading = loading || externalLoading;

  if (isLoading && markets.length === 0) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="h-8 bg-gray-700 rounded mb-4"></div>
        <div className="space-y-3">
          <div className="h-20 bg-gray-700 rounded"></div>
          <div className="h-20 bg-gray-700 rounded"></div>
          <div className="h-20 bg-gray-700 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          Prediction Markets
        </h3>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="text-xs bg-gray-700 text-gray-300 rounded px-2 py-1 border-none"
        >
          <option value="quality">Sort: Quality</option>
          <option value="volume">Sort: Volume</option>
          <option value="change">Sort: Change</option>
        </select>
      </div>

      {/* Category Tabs */}
      <div className="flex gap-1 mb-4 overflow-x-auto pb-2">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.id}
            onClick={() => handleCategoryChange(cat.id)}
            className={`px-3 py-1.5 rounded-lg text-xs whitespace-nowrap transition-colors ${
              activeCategory === cat.id
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
            }`}
          >
            {cat.emoji} {cat.label}
          </button>
        ))}
      </div>

      {/* Category Aggregate */}
      {aggregate && <CategoryAggregate aggregate={aggregate} />}

      {/* Markets List */}
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {sortedMarkets.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            No markets found for this category
          </div>
        ) : (
          sortedMarkets.slice(0, 15).map((market, idx) => (
            <MarketCard
              key={market.id || idx}
              market={market}
              expanded={expandedMarket === (market.id || idx)}
              onToggle={() => setExpandedMarket(
                expandedMarket === (market.id || idx) ? null : (market.id || idx)
              )}
            />
          ))
        )}
      </div>

      {sortedMarkets.length > 15 && (
        <div className="mt-3 text-center text-xs text-gray-500">
          Showing 15 of {sortedMarkets.length} markets
        </div>
      )}
    </div>
  );
}
