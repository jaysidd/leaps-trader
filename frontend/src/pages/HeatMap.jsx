/**
 * Heat Map Page
 * Displays market heat maps similar to Finviz/TradingView
 * - Market Heat Map (S&P 500 sectors) - Real data from Alpaca
 * - Screener Results Heat Map (categorized by screen type)
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import useScreenerStore from '../stores/screenerStore';
import useSavedScansStore from '../stores/savedScansStore';
import Card from '../components/common/Card';
import StockDetail from '../components/screener/StockDetail';
import { stocksAPI } from '../api/stocks';
import { screenerAPI } from '../api/screener';
import { savedScansAPI } from '../api/savedScans';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Color scale for performance
const getPerformanceColor = (change, darkMode = false) => {
  if (change === null || change === undefined) {
    return darkMode ? 'bg-gray-700' : 'bg-gray-200';
  }

  if (change >= 5) return 'bg-green-600';
  if (change >= 3) return 'bg-green-500';
  if (change >= 1) return 'bg-green-400';
  if (change >= 0) return 'bg-green-300';
  if (change >= -1) return 'bg-red-300';
  if (change >= -3) return 'bg-red-400';
  if (change >= -5) return 'bg-red-500';
  return 'bg-red-600';
};

// Get text color based on background
const getTextColor = (change) => {
  if (change === null || change === undefined) return 'text-gray-500';
  if (Math.abs(change) >= 3) return 'text-white';
  return 'text-gray-900';
};

// TreeMap Cell Component
const TreeMapCell = ({ symbol, name, change, price, size = 'normal', onClick }) => {
  const bgColor = getPerformanceColor(change);
  const textColor = getTextColor(change);

  const sizeClasses = {
    small: 'p-1 text-xs',
    normal: 'p-2 text-sm',
    large: 'p-3 text-base',
  };

  return (
    <div
      onClick={onClick}
      className={`${bgColor} ${textColor} ${sizeClasses[size]} rounded cursor-pointer
                  hover:opacity-80 transition-opacity flex flex-col justify-center items-center
                  border border-black/10`}
      title={`${name || symbol}: ${change !== null && change !== undefined ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : 'N/A'}${price ? ` | $${price.toFixed(2)}` : ''}`}
    >
      <div className="font-bold truncate w-full text-center">{symbol}</div>
      {change !== null && change !== undefined && (
        <div className="text-xs opacity-90">
          {change >= 0 ? '+' : ''}{change.toFixed(1)}%
        </div>
      )}
    </div>
  );
};

// Sector Block Component
const SectorBlock = ({ name, stocks, onStockClick }) => {
  // Calculate sector average change
  const avgChange = useMemo(() => {
    const validChanges = stocks.filter(s => s.change !== null && s.change !== undefined);
    if (validChanges.length === 0) return null;
    return validChanges.reduce((sum, s) => sum + s.change, 0) / validChanges.length;
  }, [stocks]);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-3 border border-gray-200 dark:border-gray-700">
      <div className="flex justify-between items-center mb-2 border-b border-gray-200 dark:border-gray-600 pb-1">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
          {name}
        </h3>
        {avgChange !== null && (
          <span className={`text-xs font-medium ${avgChange >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
            {avgChange >= 0 ? '+' : ''}{avgChange.toFixed(2)}%
          </span>
        )}
      </div>
      <div className="grid grid-cols-5 gap-1">
        {stocks.map((stock) => (
          <TreeMapCell
            key={stock.symbol}
            symbol={stock.symbol}
            name={stock.name}
            change={stock.change}
            price={stock.price}
            size="small"
            onClick={() => onStockClick?.(stock)}
          />
        ))}
      </div>
    </div>
  );
};

// Screener Result Cell
const ScreenerCell = ({ result, onClick }) => {
  const change = result.price_change_percent || result.change_percent || 0;
  const bgColor = getPerformanceColor(change);
  const textColor = getTextColor(change);
  const displayName = result.name || result.company_name || result.symbol;

  // Size based on score
  const score = result.score || 50;
  const sizeClass = score >= 80 ? 'col-span-2 row-span-2' :
                    score >= 60 ? 'col-span-2' : '';

  return (
    <div
      onClick={() => onClick?.(result)}
      className={`${bgColor} ${textColor} ${sizeClass} p-2 rounded cursor-pointer
                  hover:opacity-80 transition-opacity flex flex-col justify-center items-center
                  border border-black/10 min-h-[60px]`}
      title={`${displayName}\nScore: ${score}\nChange: ${change.toFixed(2)}%`}
    >
      <div className="font-bold text-sm">{result.symbol}</div>
      <div className="text-xs opacity-80">
        {change >= 0 ? '+' : ''}{change.toFixed(1)}%
      </div>
      {score >= 60 && (
        <div className="text-xs mt-1 opacity-70">
          Score: {Math.round(score)}
        </div>
      )}
    </div>
  );
};

// Legend Component
const Legend = () => (
  <div className="flex items-center justify-center gap-1 text-xs">
    <span className="text-gray-600 dark:text-gray-400 mr-2">Performance:</span>
    <div className="flex items-center gap-0.5">
      <div className="w-6 h-4 bg-red-600 rounded-sm" title="-5%+"></div>
      <div className="w-6 h-4 bg-red-500 rounded-sm" title="-3% to -5%"></div>
      <div className="w-6 h-4 bg-red-400 rounded-sm" title="-1% to -3%"></div>
      <div className="w-6 h-4 bg-red-300 rounded-sm" title="0% to -1%"></div>
      <div className="w-6 h-4 bg-green-300 rounded-sm" title="0% to +1%"></div>
      <div className="w-6 h-4 bg-green-400 rounded-sm" title="+1% to +3%"></div>
      <div className="w-6 h-4 bg-green-500 rounded-sm" title="+3% to +5%"></div>
      <div className="w-6 h-4 bg-green-600 rounded-sm" title="+5%+"></div>
    </div>
    <span className="text-gray-500 dark:text-gray-400 ml-1">-5%</span>
    <span className="text-gray-500 dark:text-gray-400 mx-1">to</span>
    <span className="text-gray-500 dark:text-gray-400">+5%</span>
  </div>
);

// Tab Component
const Tab = ({ active, onClick, children, count }) => (
  <button
    onClick={onClick}
    className={`px-4 py-2 font-medium rounded-t-lg border-b-2 transition-colors ${
      active
        ? 'border-blue-600 text-blue-600 dark:text-blue-400 bg-white dark:bg-gray-800'
        : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300'
    }`}
  >
    {children}
    {count > 0 && (
      <span className={`ml-2 px-2 py-0.5 rounded-full text-xs ${
        active ? 'bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
      }`}>
        {count}
      </span>
    )}
  </button>
);

export default function HeatMap() {
  const [activeTab, setActiveTab] = useState('market');
  const [marketData, setMarketData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [stockDetailData, setStockDetailData] = useState(null);
  const [stockDetailLoading, setStockDetailLoading] = useState(false);

  const { results: liveResults, lastScanPreset } = useScreenerStore();
  const { categories } = useSavedScansStore();
  const [savedResults, setSavedResults] = useState({}); // scanType -> stocks[]
  const [savedLoading, setSavedLoading] = useState(false);

  // Load all saved scan results for the heatmap, then enrich with live prices
  const loadSavedResults = useCallback(async () => {
    setSavedLoading(true);
    try {
      // First fetch categories to know what's available
      const catData = await savedScansAPI.getCategories();
      const cats = catData.categories || [];

      if (cats.length === 0) {
        setSavedResults({});
        setSavedLoading(false);
        return;
      }

      // Fetch stocks for all categories in parallel
      const entries = await Promise.all(
        cats.map(async (cat) => {
          try {
            const data = await savedScansAPI.getResults(cat.scan_type);
            return [cat.display_name || cat.scan_type, data.stocks || []];
          } catch {
            return [cat.display_name || cat.scan_type, []];
          }
        })
      );

      const populated = entries.filter(([_, stocks]) => stocks.length > 0);

      // Collect all unique symbols to fetch live quotes
      const allSymbols = [...new Set(populated.flatMap(([_, stocks]) => stocks.map(s => s.symbol)))];

      // Fetch live quotes from Alpaca in one batch call
      let liveQuotes = {};
      if (allSymbols.length > 0) {
        try {
          const quoteData = await stocksAPI.getBatchQuotes(allSymbols);
          liveQuotes = quoteData.quotes || {};
        } catch (err) {
          console.warn('Could not fetch live quotes for saved stocks:', err);
        }
      }

      // Merge live price data into saved stocks
      const enriched = populated.map(([name, stocks]) => [
        name,
        stocks.map(stock => {
          const quote = liveQuotes[stock.symbol];
          if (quote) {
            return {
              ...stock,
              price_change_percent: quote.change_percent ?? stock.price_change_percent ?? 0,
              current_price: quote.current_price ?? stock.current_price,
            };
          }
          return stock;
        }),
      ]);

      setSavedResults(Object.fromEntries(enriched));
    } catch (err) {
      console.error('Error loading saved results for heatmap:', err);
    } finally {
      setSavedLoading(false);
    }
  }, []);

  // Load saved results on mount
  useEffect(() => {
    loadSavedResults();
  }, [loadSavedResults]);

  // Combine live + saved results for total count
  const allSavedStocks = useMemo(() => {
    return Object.values(savedResults).flat();
  }, [savedResults]);

  // Fetch real market data from API
  const fetchMarketData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/heatmap/market-overview`);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      const data = await response.json();

      if (data.sectors) {
        setMarketData(data.sectors);
        setLastUpdated(new Date());
      } else {
        throw new Error('Invalid response format');
      }
    } catch (err) {
      console.error('Error fetching market data:', err);
      setError(err.message || 'Failed to fetch market data');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch data on mount and set up auto-refresh
  useEffect(() => {
    fetchMarketData();

    // Auto-refresh every 60 seconds during market hours
    const interval = setInterval(() => {
      const now = new Date();
      const hour = now.getHours();
      const day = now.getDay();

      // Only refresh Mon-Fri, 9:30 AM - 4 PM ET (approximate)
      if (day >= 1 && day <= 5 && hour >= 9 && hour <= 16) {
        fetchMarketData();
      }
    }, 60000);

    return () => clearInterval(interval);
  }, [fetchMarketData]);

  // Use saved results as primary source, fall back to live results
  const screenerGroups = useMemo(() => {
    const hasSaved = Object.keys(savedResults).length > 0;
    const hasLive = liveResults && liveResults.length > 0;

    if (!hasSaved && !hasLive) return {};

    const groups = {};

    // Add saved scan categories (each scan type is its own group)
    if (hasSaved) {
      for (const [name, stocks] of Object.entries(savedResults)) {
        groups[name] = stocks;
      }
    }

    // Add live results if any (grouped by score tier)
    if (hasLive) {
      const topCandidates = liveResults.filter(r => r.passed_all && r.score >= 70);
      const moderate = liveResults.filter(r => r.passed_all && r.score >= 50 && r.score < 70);
      const watchlist = liveResults.filter(r => r.passed_all && r.score < 50);

      if (topCandidates.length > 0) groups['Live Scan — Top Candidates'] = topCandidates;
      if (moderate.length > 0) groups['Live Scan — Moderate'] = moderate;
      if (watchlist.length > 0) groups['Live Scan — Watchlist'] = watchlist;
    }

    return groups;
  }, [savedResults, liveResults]);

  // Handle stock click - fetch full details and show StockDetail modal
  const handleStockClick = async (stock) => {
    if (!stock?.symbol) return;

    setStockDetailLoading(true);
    try {
      // Fetch stock info and scores in parallel
      const [stockInfo, scoresData] = await Promise.all([
        stocksAPI.getStockInfo(stock.symbol).catch(() => null),
        screenerAPI.getBatchScores([stock.symbol]).catch(() => ({ scores: {} })),
      ]);

      const scoreResult = scoresData.scores?.[stock.symbol] || {};

      setStockDetailData({
        symbol: stock.symbol,
        name: stockInfo?.name || stock.name || stock.company_name || stock.symbol,
        current_price: stockInfo?.currentPrice || stock.price || stock.current_price,
        sector: stockInfo?.sector,
        market_cap: stockInfo?.marketCap || stock.market_cap,
        price_change_percent: stock.change || stock.price_change_percent,
        ...stockInfo,
        // Merge scoring data
        score: scoreResult.score ?? stock.score,
        composite_score: scoreResult.composite_score,
        fundamental_score: scoreResult.fundamental_score,
        technical_score: scoreResult.technical_score,
        options_score: scoreResult.options_score,
        momentum_score: scoreResult.momentum_score,
        technical_indicators: scoreResult.technical_indicators,
        leaps_summary: scoreResult.leaps_summary,
        returns: scoreResult.returns,
        iv_rank: scoreResult.iv_rank,
        iv_percentile: scoreResult.iv_percentile,
      });
    } catch (error) {
      console.error('Error fetching stock details:', error);
      // Still show modal with basic data
      setStockDetailData({
        symbol: stock.symbol,
        name: stock.name || stock.company_name || stock.symbol,
        current_price: stock.price || stock.current_price,
        price_change_percent: stock.change || stock.price_change_percent,
        score: stock.score,
        market_cap: stock.market_cap,
      });
    } finally {
      setStockDetailLoading(false);
    }
  };

  const formatLastUpdated = () => {
    if (!lastUpdated) return '';
    return lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 py-6 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-6 flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Heat Map</h1>
            <p className="text-gray-600 dark:text-gray-400">
              Visual market overview and screener results
            </p>
          </div>
          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="text-xs text-gray-500 dark:text-gray-400">
                Updated: {formatLastUpdated()}
              </span>
            )}
            <button
              onClick={fetchMarketData}
              disabled={loading}
              className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              )}
              Refresh
            </button>
          </div>
        </div>

        {/* Legend */}
        <div className="mb-4">
          <Legend />
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-gray-700 mb-6">
          <div className="flex gap-4">
            <Tab
              active={activeTab === 'market'}
              onClick={() => setActiveTab('market')}
            >
              Market Overview
            </Tab>
            <Tab
              active={activeTab === 'screener'}
              onClick={() => setActiveTab('screener')}
              count={allSavedStocks.length + liveResults.filter(r => r.passed_all).length}
            >
              Screener Results
            </Tab>
          </div>
        </div>

        {/* Market Heat Map */}
        {activeTab === 'market' && (
          <div className="space-y-4">
            {/* Error State */}
            {error && (
              <Card className="border-red-200 dark:border-red-800">
                <div className="text-center py-6">
                  <div className="text-red-500 text-4xl mb-3">⚠️</div>
                  <p className="text-red-700 dark:text-red-400 font-medium mb-2">{error}</p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                    Make sure Alpaca API keys are configured in Settings.
                  </p>
                  <button
                    onClick={fetchMarketData}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Try Again
                  </button>
                </div>
              </Card>
            )}

            {/* Loading State */}
            {loading && !error && Object.keys(marketData).length === 0 && (
              <div className="flex justify-center py-12">
                <div className="text-center">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                  <p className="text-gray-600 dark:text-gray-400">Loading market data from Alpaca...</p>
                </div>
              </div>
            )}

            {/* Market Data Grid */}
            {!error && Object.keys(marketData).length > 0 && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {Object.entries(marketData).map(([sector, stocks]) => (
                    <SectorBlock
                      key={sector}
                      name={sector}
                      stocks={stocks}
                      onStockClick={handleStockClick}
                    />
                  ))}
                </div>

                {/* Data source info */}
                <div className="mt-4 text-center text-xs text-gray-500 dark:text-gray-400">
                  <span className="inline-flex items-center gap-1">
                    <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                    Live data from Alpaca (IEX feed)
                  </span>
                  {loading && (
                    <span className="ml-3 inline-flex items-center gap-1">
                      <div className="w-2 h-2 border border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                      Refreshing...
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {/* Screener Results Heat Map */}
        {activeTab === 'screener' && (
          <div className="space-y-6">
            {savedLoading ? (
              <div className="flex justify-center py-12">
                <div className="text-center">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                  <p className="text-gray-600 dark:text-gray-400">Loading saved results...</p>
                </div>
              </div>
            ) : Object.keys(screenerGroups).length === 0 ? (
              <Card>
                <div className="text-center py-12 text-gray-500 dark:text-gray-400">
                  <div className="text-4xl mb-4">🔍</div>
                  <p className="mb-2">No screener results to display</p>
                  <p className="text-sm">
                    Run a scan in the Screener to see results visualized here.
                  </p>
                </div>
              </Card>
            ) : (
              <>
                {/* Summary Info */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-4 border border-gray-200 dark:border-gray-700">
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-gray-600 dark:text-gray-400">
                      {Object.keys(savedResults).length > 0 && (
                        <span>{allSavedStocks.length} saved stocks across {Object.keys(savedResults).length} scans</span>
                      )}
                      {liveResults.length > 0 && Object.keys(savedResults).length > 0 && (
                        <span className="mx-2">•</span>
                      )}
                      {liveResults.length > 0 && (
                        <span>{liveResults.filter(r => r.passed_all).length} from live scan ({lastScanPreset || 'custom'})</span>
                      )}
                    </div>
                    <button
                      onClick={loadSavedResults}
                      className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      Refresh
                    </button>
                  </div>
                </div>

                {/* Results by Category — same compact layout as Market Overview */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {Object.entries(screenerGroups).map(([groupName, stocks]) => (
                    <SectorBlock
                      key={groupName}
                      name={groupName}
                      stocks={stocks.map(s => ({
                        symbol: s.symbol,
                        name: s.name || s.company_name || s.symbol,
                        change: s.price_change_percent ?? s.change_percent ?? 0,
                        price: s.current_price ?? s.price ?? null,
                      }))}
                      onStockClick={handleStockClick}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* Stock Detail Modal */}
        {stockDetailData && (
          <StockDetail
            stock={stockDetailData}
            onClose={() => setStockDetailData(null)}
          />
        )}

        {/* Loading indicator for stock detail */}
        {stockDetailLoading && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 flex items-center gap-3">
              <svg className="animate-spin h-6 w-6 text-blue-500" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="text-gray-700 dark:text-gray-300">Loading stock details...</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
