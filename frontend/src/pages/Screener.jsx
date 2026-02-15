/**
 * Screener page with tabbed interface
 * Supports URL parameters: ?preset=xxx&mode=xxx
 *
 * Uses Zustand store for state persistence - results are preserved
 * when navigating away and returning to this page.
 */
import { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import ResultsTable from '../components/screener/ResultsTable';
import StockDetail from '../components/screener/StockDetail';
import CriteriaForm from '../components/screener/CriteriaForm';
import Loading from '../components/common/Loading';
import FullAutoBanner from '../components/common/FullAutoBanner';
import { MarketRegimeBanner } from '../components/ai';
import useScreenerStore from '../stores/screenerStore';
import useSavedScansStore from '../stores/savedScansStore';
import useFullAutoLock from '../hooks/useFullAutoLock';
import { AlertsTab, AlertDetail } from '../components/alerts';

// Tab configuration
const TABS = [
  { id: 'presets', label: '🚀 Quick Presets', description: 'One-click market scans' },
  { id: 'custom', label: '⚙️ Custom Criteria', description: 'Fine-tune your filters' },
  { id: 'manual', label: '📝 Manual Stocks', description: 'Screen specific symbols' },
  { id: 'alerts', label: '🔔 Alerts', description: 'Webhook trading signals' },
];

// Default criteria for custom tab
const DEFAULT_CRITERIA = {
  marketCapMin: 1_000_000_000,
  marketCapMax: 100_000_000_000,
  priceMin: 5,
  priceMax: 500,
  revenueGrowthMin: 10,
  earningsGrowthMin: 5,
  debtToEquityMax: 200,
  rsiMin: 25,
  rsiMax: 75,
  ivMax: 100,
  minDTE: 365,
  maxDTE: 730,
};

// Predefined watchlists for manual tab
const PREDEFINED_LISTS = {
  'Tech Giants': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA'],
  'Semiconductors': ['NVDA', 'AMD', 'INTC', 'TSM', 'AVGO', 'QCOM', 'MU'],
  'Healthcare': ['JNJ', 'UNH', 'PFE', 'ABBV', 'TMO', 'MRK', 'LLY'],
  'Fintech': ['V', 'MA', 'PYPL', 'SQ', 'COIN', 'SOFI', 'AFRM'],
  'EV & Clean Energy': ['TSLA', 'RIVN', 'LCID', 'ENPH', 'SEDG', 'NEE'],
};

// Preset categories for organized display
const PRESET_CATEGORIES = {
  standard: {
    title: 'Standard Risk Levels',
    description: 'Classic risk-based presets for LEAPS trading',
    icon: '⚖️',
    presets: [
      { id: 'conservative', name: 'Conservative', description: 'Large caps ($5B+), stable growth, low risk', color: 'blue' },
      { id: 'moderate', name: 'Moderate', description: 'Mid caps ($1B+), good growth, balanced', color: 'yellow', recommended: true },
      { id: 'aggressive', name: 'Aggressive', description: 'Small/mid caps ($500M+), high growth potential', color: 'purple' },
    ],
  },
  leaps: {
    title: 'LEAPS Strategies',
    description: 'Long-term options plays (365+ DTE)',
    icon: '📈',
    presets: [
      { id: 'low_iv_entry', name: 'Low IV Entry', description: 'Low IV rank — cheap options, ideal entry', color: 'green' },
      { id: 'cheap_leaps', name: 'Cheap LEAPS', description: 'Premium <10% of stock price, high liquidity', color: 'blue' },
      { id: 'momentum', name: 'Momentum LEAPS', description: 'Strong fundamentals + RSI recovering', color: 'orange' },
      { id: 'turnaround', name: 'Turnaround Plays', description: 'Oversold RSI + above SMA200', color: 'purple' },
      { id: 'growth_leaps', name: 'Growth LEAPS', description: 'High growth, PEG<2.5 valuation guard', color: 'teal' },
      { id: 'blue_chip_leaps', name: 'Blue Chip LEAPS', description: 'Mega caps with stable returns', color: 'gray' },
    ],
  },
  swing: {
    title: 'Swing Trading (4-8 weeks)',
    description: 'Short-term momentum plays with 30-60 DTE',
    icon: '⚡',
    presets: [
      { id: 'swing_momentum', name: 'Swing Momentum', description: 'Ride the trend (4-8 weeks)', color: 'yellow' },
      { id: 'swing_breakout', name: 'Swing Breakout', description: 'Technical breakout setups', color: 'orange' },
      { id: 'swing_oversold', name: 'Swing Oversold', description: 'Oversold bounce plays', color: 'red' },
      { id: 'swing_iv_play', name: 'Swing IV Play', description: 'Low IV entry for leverage', color: 'green' },
    ],
  },
  weekly: {
    title: 'Weekly & Earnings Plays',
    description: 'Quick momentum and event-driven trades',
    icon: '🎯',
    presets: [
      { id: 'weekly_momentum', name: 'Weekly Momentum', description: 'Quick weekly profits (7-21 DTE)', color: 'blue' },
      { id: 'pre_earnings_iv', name: 'Pre-Earnings IV', description: 'IV expansion before earnings', color: 'purple' },
    ],
  },
  value: {
    title: 'Value Investing',
    description: 'Find undervalued stocks with margin of safety',
    icon: '💎',
    presets: [
      { id: 'deep_value', name: 'Deep Value', description: 'Graham: P/E<15, P/B<1.5, low debt', color: 'green' },
      { id: 'garp', name: 'GARP', description: 'PEG<1.5, P/E<25, ROE>12%', color: 'teal' },
      { id: 'undervalued_large_cap', name: 'Undervalued Large Cap', description: 'Large cap pullback value', color: 'blue' },
    ],
  },
  dividend: {
    title: 'Dividend & Income',
    description: 'Sustainable yield and growing dividends',
    icon: '💰',
    presets: [
      { id: 'dividend_income', name: 'High Yield Income', description: 'Yield 2.5%+, sustainable margins', color: 'green' },
      { id: 'dividend_growth', name: 'Dividend Growth', description: 'Growing dividends + capital gains', color: 'teal' },
    ],
  },
  small_cap: {
    title: 'Small Cap',
    description: 'High potential small cap stocks ($300M-$3B)',
    icon: '🔬',
    presets: [
      { id: 'small_cap_growth', name: 'Small Cap Growth', description: 'High growth multi-bagger potential', color: 'orange' },
      { id: 'small_cap_value', name: 'Small Cap Value', description: 'Undervalued with solid fundamentals', color: 'green' },
    ],
  },
  sentiment: {
    title: 'Sentiment Plays',
    description: 'Smart money and momentum signals',
    icon: '📊',
    presets: [
      { id: 'insider_buying', name: 'Insider Buying', description: 'Beaten-down, smart money accumulation', color: 'purple' },
      { id: 'short_squeeze', name: 'Short Squeeze', description: 'Squeeze candidates + recovery', color: 'red' },
    ],
  },
  options_income: {
    title: 'Options Income',
    description: 'Premium harvesting strategies',
    icon: '🏦',
    presets: [
      { id: 'covered_call', name: 'Covered Call', description: 'Range-bound, low beta, sell calls', color: 'blue' },
      { id: 'wheel_strategy', name: 'Wheel Strategy', description: 'Sell puts then covered calls', color: 'yellow' },
    ],
  },
  options_directional: {
    title: 'Options Directional',
    description: 'Defined-risk directional plays',
    icon: '🎯',
    presets: [
      { id: 'bull_call_spread', name: 'Bull Call Spread', description: 'Defined risk bullish, 30-90 DTE', color: 'orange' },
      { id: 'leaps_deep_itm', name: 'LEAPS Deep ITM', description: 'Stock replacement, delta 0.70-0.90', color: 'gray' },
    ],
  },
};

const PresetButton = ({ preset, onClick, disabled, isActive, hasSavedResults, stockCount }) => {
  const colorClasses = {
    blue: 'border-blue-200 bg-blue-50 hover:bg-blue-100 hover:border-blue-300 text-blue-800 dark:border-blue-700 dark:bg-blue-900/30 dark:hover:bg-blue-900/50 dark:text-blue-300',
    yellow: 'border-yellow-200 bg-yellow-50 hover:bg-yellow-100 hover:border-yellow-300 text-yellow-800 dark:border-yellow-700 dark:bg-yellow-900/30 dark:hover:bg-yellow-900/50 dark:text-yellow-300',
    purple: 'border-purple-200 bg-purple-50 hover:bg-purple-100 hover:border-purple-300 text-purple-800 dark:border-purple-700 dark:bg-purple-900/30 dark:hover:bg-purple-900/50 dark:text-purple-300',
    green: 'border-green-200 bg-green-50 hover:bg-green-100 hover:border-green-300 text-green-800 dark:border-green-700 dark:bg-green-900/30 dark:hover:bg-green-900/50 dark:text-green-300',
    orange: 'border-orange-200 bg-orange-50 hover:bg-orange-100 hover:border-orange-300 text-orange-800 dark:border-orange-700 dark:bg-orange-900/30 dark:hover:bg-orange-900/50 dark:text-orange-300',
    teal: 'border-teal-200 bg-teal-50 hover:bg-teal-100 hover:border-teal-300 text-teal-800 dark:border-teal-700 dark:bg-teal-900/30 dark:hover:bg-teal-900/50 dark:text-teal-300',
    gray: 'border-gray-300 bg-gray-50 hover:bg-gray-100 hover:border-gray-400 text-gray-800 dark:border-gray-600 dark:bg-gray-700/30 dark:hover:bg-gray-700/50 dark:text-gray-300',
    red: 'border-red-200 bg-red-50 hover:bg-red-100 hover:border-red-300 text-red-800 dark:border-red-700 dark:bg-red-900/30 dark:hover:bg-red-900/50 dark:text-red-300',
  };

  return (
    <button
      onClick={() => onClick(preset.id)}
      disabled={disabled}
      title={preset.description}
      className={`relative inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap ${
        isActive ? 'ring-2 ring-blue-500 ring-offset-1 dark:ring-offset-gray-900' : ''
      } ${colorClasses[preset.color] || colorClasses.gray}`}
    >
      {preset.name}
      {preset.recommended && (
        <span className="text-xs bg-yellow-400 text-yellow-900 px-1.5 py-0.5 rounded-full leading-none">*</span>
      )}
      {hasSavedResults && (
        <span className="inline-flex items-center gap-0.5 text-xs bg-green-500 text-white px-1.5 py-0.5 rounded-full leading-none">
          <span>&#9733;</span>{stockCount}
        </span>
      )}
    </button>
  );
};

// Scan All Presets completion summary with per-preset breakdown
const ScanAllSummaryCard = ({ summary }) => {
  const { presetSummary, durationSeconds, totalScanned, totalPassed } = summary;

  // Convert preset summary object to sorted array
  const presets = Object.entries(presetSummary).map(([id, data]) => ({
    id,
    name: data.name,
    count: data.count,
  }));

  // Sort: presets with matches first (desc by count), then empty ones alphabetically
  presets.sort((a, b) => {
    if (a.count > 0 && b.count === 0) return -1;
    if (a.count === 0 && b.count > 0) return 1;
    if (a.count !== b.count) return b.count - a.count;
    return a.name.localeCompare(b.name);
  });

  const matchedCount = presets.filter(p => p.count > 0).length;
  const emptyCount = presets.filter(p => p.count === 0).length;

  const formatDuration = (seconds) => {
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  };

  return (
    <div className="mb-6 rounded-lg border border-indigo-200 dark:border-indigo-800 bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-indigo-100 dark:border-indigo-800/50">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-indigo-900 dark:text-indigo-200">
              Scan All Presets Complete
            </h3>
            <p className="text-sm text-indigo-700 dark:text-indigo-400 mt-0.5">
              Scanned {totalScanned.toLocaleString()} stocks in {formatDuration(durationSeconds)} — Found {totalPassed} candidate{totalPassed !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 font-medium">
              {matchedCount} matched
            </span>
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400 font-medium">
              {emptyCount} empty
            </span>
          </div>
        </div>
      </div>

      {/* Preset Grid */}
      <div className="px-5 py-4">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {presets.map((preset) => (
            <div
              key={preset.id}
              className={`flex items-center justify-between px-3 py-2 rounded-md text-sm ${
                preset.count > 0
                  ? 'bg-white dark:bg-gray-800 border border-indigo-200 dark:border-indigo-700'
                  : 'bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 opacity-60'
              }`}
            >
              <span className={`font-medium truncate mr-2 ${
                preset.count > 0
                  ? 'text-gray-900 dark:text-gray-100'
                  : 'text-gray-400 dark:text-gray-500'
              }`}>
                {preset.name}
              </span>
              <span className={`flex-shrink-0 inline-flex items-center justify-center min-w-[1.75rem] px-1.5 py-0.5 rounded-full text-xs font-bold ${
                preset.count > 0
                  ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300'
                  : 'bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500'
              }`}>
                {preset.count}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default function Screener() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Get state from Zustand store
  const {
    loading,
    results,
    error,
    apiStatus,
    scanProgress,
    scanType,
    activePreset,
    lastScanTime,
    lastScanPreset,
    scanAllSummary,
    setApiStatus,
    startStreamingScan,
    startScanAllPresets,
    startBatchScan,
    startManualScreening,
    cancelScan,
    clearScan,
  } = useScreenerStore();

  // Full Auto lockdown
  const { isLocked } = useFullAutoLock();

  // Get saved scans store for auto-save and indicators
  const {
    scanStatus,
    fetchScanStatus,
    saveResults,
    hasSavedResults,
    getScanMetadata,
  } = useSavedScansStore();

  // Local UI state (not persisted)
  const [selectedStock, setSelectedStock] = useState(null);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [activeTab, setActiveTab] = useState('presets');
  const [criteria, setCriteria] = useState(DEFAULT_CRITERIA);
  const [symbols, setSymbols] = useState('');
  const [selectedList, setSelectedList] = useState('');
  const [topN, setTopN] = useState(15);

  // Track if we've already auto-scanned from URL params
  const hasAutoScannedRef = useRef(false);
  // Track if we've already saved results for the current scan
  const hasSavedCurrentScanRef = useRef(false);

  // Get URL parameters
  const urlPreset = searchParams.get('preset');
  const urlMode = searchParams.get('mode');

  // Fetch scan status on mount for saved indicators
  useEffect(() => {
    fetchScanStatus();
  }, []);

  // Auto-save results when a scan completes
  useEffect(() => {
    // Only save when we have results, not loading, and have a preset
    if (!loading && results.length > 0 && lastScanPreset && !hasSavedCurrentScanRef.current) {
      // Don't save manual scans or custom scans (only preset-based)
      if (lastScanPreset !== 'manual' && lastScanPreset !== 'custom') {
        hasSavedCurrentScanRef.current = true;

        // Handle "Scan All Presets" — save each preset's results individually
        if (lastScanPreset === 'All Presets' && scanAllSummary?.presetSummary) {
          const presetSummary = scanAllSummary.presetSummary;
          const savePromises = [];

          for (const [presetId, presetInfo] of Object.entries(presetSummary)) {
            // Filter results that matched this preset
            const presetResults = results.filter(
              (r) => r.matched_presets && r.matched_presets.includes(presetId)
            );

            if (presetResults.length > 0) {
              const displayName = presetInfo.name || presetId;
              savePromises.push(
                saveResults(presetId, displayName, presetResults)
                  .then(() => {
                    console.log(`[Screener] Auto-saved ${presetResults.length} results for ${presetId}`);
                  })
                  .catch((err) => {
                    console.error(`[Screener] Failed to auto-save results for ${presetId}:`, err);
                  })
              );
            }
          }

          Promise.all(savePromises)
            .then(() => {
              console.log(`[Screener] All preset results saved from Scan All Presets`);
              fetchScanStatus();
            })
            .catch((err) => {
              console.error('[Screener] Error saving scan-all results:', err);
            });
        } else {
          // Single preset scan — save normally
          // Find display name for the preset
          let displayName = lastScanPreset;
          for (const category of Object.values(PRESET_CATEGORIES)) {
            const found = category.presets.find(p => p.id === lastScanPreset);
            if (found) {
              displayName = found.name;
              break;
            }
          }

          // Auto-save results
          saveResults(lastScanPreset, displayName, results)
            .then(() => {
              console.log(`[Screener] Auto-saved ${results.length} results for ${lastScanPreset}`);
              // Refresh scan status to update indicators
              fetchScanStatus();
            })
            .catch((err) => {
              console.error('[Screener] Failed to auto-save results:', err);
            });
        }
      }
    }

    // Reset the saved flag when a new scan starts
    if (loading) {
      hasSavedCurrentScanRef.current = false;
    }
  }, [loading, results, lastScanPreset, scanAllSummary, saveResults, fetchScanStatus]);

  // Auto-run scan when preset is provided in URL
  useEffect(() => {
    if (urlPreset && !hasAutoScannedRef.current && !loading) {
      hasAutoScannedRef.current = true;
      console.log(`🚀 Auto-starting scan with preset: ${urlPreset} (mode: ${urlMode})`);
      setApiStatus(`Starting ${urlMode || 'LEAPS'} scan with "${urlPreset}" preset...`);
      startStreamingScan(urlPreset);
      // Clear the URL params after starting the scan
      setSearchParams({});
    }
  }, [urlPreset, urlMode, loading, startStreamingScan, setApiStatus, setSearchParams]);

  // Handle manual stock screening
  const handleManualSubmit = (e) => {
    e.preventDefault();
    const symbolList = symbols
      .toUpperCase()
      .split(/[\s,;]+/)
      .map(s => s.trim())
      .filter(s => s.length > 0);

    if (symbolList.length === 0) {
      setApiStatus('Please enter at least one stock symbol');
      return;
    }

    startManualScreening(symbolList, topN, criteria);
  };

  const handleSelectList = (listName) => {
    setSelectedList(listName);
    const listSymbols = PREDEFINED_LISTS[listName];
    setSymbols(listSymbols.join(', '));
  };

  // Format the last scan time for display
  const formatLastScanTime = () => {
    if (!lastScanTime) return null;
    const date = new Date(lastScanTime);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 py-8 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
            Options Screener
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-400">
            Find LEAPS and swing trade opportunities using multi-factor analysis
          </p>
          <div className="mt-4 flex items-center gap-4 flex-wrap">
            {results.length > 0 && !loading && (
              <button
                onClick={clearScan}
                className="px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50 transition-colors"
              >
                Clear Results
              </button>
            )}
            {apiStatus && (
              <div className="text-sm font-medium text-gray-700 dark:text-gray-300">{apiStatus}</div>
            )}
          </div>
        </div>

        {/* Full Auto Lockdown Banner */}
        {isLocked && (
          <div className="mb-6">
            <FullAutoBanner message="Full Auto mode is active. Screener actions are locked to prevent interference with automation." />
          </div>
        )}

        {/* Scan Status Banner - Shows when there's an active scan or recent results */}
        {(loading || (results.length > 0 && lastScanTime)) && (
          <div className={`mb-6 rounded-lg p-4 ${loading ? 'bg-blue-50 border border-blue-200 dark:bg-blue-900/20 dark:border-blue-800' : 'bg-green-50 border border-green-200 dark:bg-green-900/20 dark:border-green-800'}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {loading ? (
                  <>
                    <div className="animate-pulse">
                      <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                    </div>
                    <span className="font-medium text-blue-800 dark:text-blue-300">
                      Scan in progress{activePreset ? ` (${activePreset})` : ''}...
                    </span>
                  </>
                ) : (
                  <>
                    <span className="text-green-600 dark:text-green-400 text-lg">✓</span>
                    <span className="font-medium text-green-800 dark:text-green-300">
                      {results.length} results from {lastScanPreset || 'scan'} • {formatLastScanTime()}
                    </span>
                  </>
                )}
              </div>
              {loading && scanProgress && (
                <div className="text-sm text-blue-600 dark:text-blue-400">
                  {scanProgress.processed}/{scanProgress.total} stocks • {scanProgress.passed} candidates
                </div>
              )}
            </div>
            {loading && scanProgress && (
              <div className="mt-2">
                <div className="w-full bg-blue-200 dark:bg-blue-900 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${scanProgress.total ? (scanProgress.processed / scanProgress.total) * 100 : 0}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Scan All Presets Summary Card */}
        {!loading && scanAllSummary && scanAllSummary.presetSummary && (
          <ScanAllSummaryCard summary={scanAllSummary} />
        )}

        {/* Market Regime Banner */}
        <MarketRegimeBanner />

        {/* Tab Navigation */}
        <div className="mb-6">
          <div className="border-b border-gray-200 dark:border-gray-700">
            <nav className="flex space-x-8" aria-label="Tabs">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                    activeTab === tab.id
                      ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300'
                  }`}
                >
                  <span className="text-lg">{tab.label}</span>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{tab.description}</p>
                </button>
              ))}
            </nav>
          </div>
        </div>

        {/* Tab Content */}
        <div className="mb-8">
          {/* Tab 1: Quick Presets */}
          {activeTab === 'presets' && (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-5">
              <div className="space-y-4">
                {Object.entries(PRESET_CATEGORIES).map(([categoryId, category]) => (
                  <div key={categoryId}>
                    <div className="flex items-center gap-1.5 mb-2">
                      <span className="text-base">{category.icon}</span>
                      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">{category.title}</h3>
                      <span className="text-xs text-gray-400 dark:text-gray-500">— {category.description}</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {category.presets.map((preset) => {
                        const metadata = getScanMetadata(preset.id);
                        return (
                          <PresetButton
                            key={preset.id}
                            preset={preset}
                            onClick={startStreamingScan}
                            disabled={loading || isLocked}
                            isActive={activePreset === preset.id}
                            hasSavedResults={metadata.has_results}
                            stockCount={metadata.stock_count}
                          />
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between">
                <div className="text-xs text-gray-400 dark:text-gray-500">
                  Hover a preset for details.
                  <span className="text-blue-500 dark:text-blue-400 ml-1">Results are preserved when you navigate away.</span>
                </div>
                <button
                  onClick={startScanAllPresets}
                  disabled={loading || isLocked}
                  className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-sm font-semibold rounded-lg hover:from-indigo-700 hover:to-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                >
                  Scan All Presets
                </button>
              </div>
            </div>
          )}

          {/* Tab 2: Custom Criteria */}
          {activeTab === 'custom' && (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 border border-transparent dark:border-gray-700">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">Custom Screening Criteria</h2>
              <p className="text-gray-600 dark:text-gray-400 mb-6">
                Fine-tune your filters to find the perfect opportunities. Adjust the sliders below and run a market scan.
              </p>
              <div className={isLocked ? 'opacity-50 pointer-events-none' : ''}>
                <CriteriaForm
                  onCriteriaChange={setCriteria}
                  initialCriteria={criteria}
                />
              </div>
              <div className="mt-6">
                <button
                  onClick={() => startBatchScan(criteria)}
                  disabled={loading || isLocked}
                  className="w-full px-6 py-4 bg-gradient-to-r from-green-600 to-teal-600 text-white rounded-lg font-semibold hover:from-green-700 hover:to-teal-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Scanning...' : '🌐 Run Market Scan with Custom Criteria'}
                </button>
              </div>
            </div>
          )}

          {/* Tab 3: Manual Stocks */}
          {activeTab === 'manual' && (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 border border-transparent dark:border-gray-700">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">Manual Stock Selection</h2>
              <p className="text-gray-600 dark:text-gray-400 mb-6">
                Enter specific stock symbols to screen, or select from predefined watchlists.
              </p>

              {/* Predefined Lists */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Quick Start: Select a Watchlist
                </label>
                <div className="flex flex-wrap gap-2">
                  {Object.keys(PREDEFINED_LISTS).map((listName) => (
                    <button
                      key={listName}
                      type="button"
                      onClick={() => handleSelectList(listName)}
                      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                        selectedList === listName
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
                      }`}
                    >
                      {listName}
                    </button>
                  ))}
                </div>
              </div>

              {/* Stock Symbols Input */}
              <form onSubmit={handleManualSubmit} className="space-y-4">
                <div>
                  <label htmlFor="symbols" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Stock Symbols (comma or space separated)
                  </label>
                  <textarea
                    id="symbols"
                    rows={4}
                    value={symbols}
                    onChange={(e) => setSymbols(e.target.value)}
                    placeholder="Enter stock symbols (e.g., AAPL, MSFT, GOOGL, NVDA, TSLA)"
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
                    disabled={loading || isLocked}
                  />
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    Example: AAPL, MSFT, GOOGL or AAPL MSFT GOOGL
                  </p>
                </div>

                {/* Top N Results */}
                <div>
                  <label htmlFor="topN" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Number of Top Results
                  </label>
                  <input
                    id="topN"
                    type="number"
                    min={1}
                    max={100}
                    value={topN}
                    onChange={(e) => setTopN(parseInt(e.target.value))}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                    disabled={loading || isLocked}
                  />
                </div>

                {/* Submit Buttons */}
                <div className="flex gap-3">
                  <button
                    type="submit"
                    disabled={loading || isLocked}
                    className="flex-1 px-6 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loading ? 'Screening...' : 'Screen Selected Stocks'}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSymbols('');
                      setSelectedList('');
                    }}
                    disabled={loading}
                    className="px-6 py-3 bg-gray-200 text-gray-700 rounded-lg font-semibold hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
                  >
                    Clear
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Tab 4: Alerts */}
          {activeTab === 'alerts' && (
            <AlertsTab onSelectAlert={setSelectedAlert} />
          )}
        </div>

        {/* Loading State with Progress */}
        {loading && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 mb-6 border border-transparent dark:border-gray-700">
            {scanProgress ? (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    🔍 Scanning Market{activePreset ? ` (${activePreset})` : ''}...
                  </h3>
                  <button
                    onClick={cancelScan}
                    className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors text-sm"
                  >
                    Cancel Scan
                  </button>
                </div>

                {/* Progress Bar */}
                <div className="mb-4">
                  <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400 mb-1">
                    <span>Progress: {scanProgress.processed || 0} / {scanProgress.total || '...'} stocks</span>
                    <span>{scanProgress.total ? Math.round((scanProgress.processed / scanProgress.total) * 100) : 0}%</span>
                  </div>
                  <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
                    <div
                      className="bg-gradient-to-r from-blue-500 to-purple-500 h-3 rounded-full transition-all duration-300"
                      style={{ width: `${scanProgress.total ? (scanProgress.processed / scanProgress.total) * 100 : 0}%` }}
                    />
                  </div>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div className="bg-blue-50 dark:bg-blue-900/30 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">{scanProgress.processed || 0}</div>
                    <div className="text-xs text-gray-600 dark:text-gray-400">Processed</div>
                  </div>
                  <div className="bg-green-50 dark:bg-green-900/30 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-green-600 dark:text-green-400">{scanProgress.passed || 0}</div>
                    <div className="text-xs text-gray-600 dark:text-gray-400">Candidates Found</div>
                  </div>
                  <div className="bg-purple-50 dark:bg-purple-900/30 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-purple-600 dark:text-purple-400">{scanProgress.total || '...'}</div>
                    <div className="text-xs text-gray-600 dark:text-gray-400">Total Stocks</div>
                  </div>
                </div>

                {/* Live Results Preview */}
                {scanProgress.candidates && scanProgress.candidates.length > 0 && (
                  <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                    <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                      🏆 Top Candidates (Live)
                    </h4>
                    <div className="text-sm text-gray-600 dark:text-gray-400">
                      {scanProgress.candidates.slice(0, 5).map((candidate, idx) => (
                        <div key={idx} className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                          <span className="font-medium text-gray-900 dark:text-gray-100">{candidate.symbol}</span>
                          <span className="text-green-600 dark:text-green-400">Score: {candidate.score?.toFixed(1) || candidate.composite_score?.toFixed(1) || 'N/A'}</span>
                        </div>
                      ))}
                      {scanProgress.candidates.length > 5 && (
                        <div className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                          +{scanProgress.candidates.length - 5} more candidates...
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Navigation hint */}
                <div className="mt-4 text-sm text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
                  💡 You can navigate away to Command Center or Settings. Your scan will continue and results will be here when you return.
                </div>
              </div>
            ) : (
              <Loading message={scanType === 'batch' ? "Scanning market with custom criteria... This may take a few minutes." : "Initializing scan..."} />
            )}
          </div>
        )}

        {/* Error Message */}
        {error && !loading && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-6">
            <div className="flex items-start">
              <div className="text-red-600 dark:text-red-400 mr-3 text-xl">⚠️</div>
              <div>
                <h3 className="font-semibold text-red-900 dark:text-red-300 mb-1">Error</h3>
                <p className="text-red-800 dark:text-red-400">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Results */}
        {!loading && results.length > 0 && (
          <ResultsTable
            results={results}
            onSelectStock={setSelectedStock}
          />
        )}

        {/* Stock Detail Modal */}
        {selectedStock && (
          <StockDetail
            stock={selectedStock}
            onClose={() => setSelectedStock(null)}
          />
        )}

        {/* Alert Detail Modal */}
        {selectedAlert && (
          <AlertDetail
            alert={selectedAlert}
            onClose={() => setSelectedAlert(null)}
          />
        )}
      </div>
    </div>
  );
}
