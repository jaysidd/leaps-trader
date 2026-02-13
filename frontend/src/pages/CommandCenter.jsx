/**
 * Command Center Dashboard Page
 * Central hub for market intelligence, news, predictions, and AI assistance
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getDashboard,
  explainMetric,
  getCatalystFeed,
  getMRI,
  getMacroEvents,
  getMacroDivergences,
} from '../api/commandCenter';
import {
  MarketPulse,
  FearGreedGauge,
  PolymarketWidget,
  CatalystFeed,
  MorningBrief,
  SectorHeatmap,
  CopilotChat,
  NewsWidget,
  MRIGauge,
  MacroEventDashboard,
  DivergenceAlert,
} from '../components/command-center';

// Trading mode configurations
const TRADING_MODES = {
  leaps: {
    value: 'leaps',
    label: 'LEAPS',
    icon: '📈',
    description: 'Long-term plays (1-2 years)',
    color: 'bg-green-600',
    settings: {
      dte: '365-730 days',
      delta: '0.60-0.80',
      focus: 'Fundamentals & Value',
      presets: ['conservative', 'moderate', 'growth_leaps', 'blue_chip_leaps', 'iv_crush'],
    },
    tips: [
      'Look for low IV Rank (<30%) for cheaper premiums',
      'Target delta 0.70+ for stock-like movement',
      'Best for high-conviction, long-term plays',
    ],
  },
  swing: {
    value: 'swing',
    label: 'Swing',
    icon: '⚡',
    description: '4-8 week trades',
    color: 'bg-yellow-600',
    settings: {
      dte: '30-60 days',
      delta: '0.40-0.55',
      focus: 'Momentum & Technicals',
      presets: ['swing_momentum', 'swing_breakout', 'swing_oversold', 'swing_iv_play'],
    },
    tips: [
      'RSI recovering from oversold = good entry',
      'Lower delta = more leverage, more risk',
      'Watch for upcoming catalysts (earnings, events)',
    ],
  },
  custom: {
    value: 'custom',
    label: 'Custom',
    icon: '🔧',
    description: 'Your settings',
    color: 'bg-purple-600',
    settings: {
      dte: 'You define',
      delta: 'You define',
      focus: 'Your criteria',
      presets: ['all'],
    },
    tips: [
      'Use the Screener to set custom filters',
      'Save your favorite configurations',
      'Mix strategies based on market conditions',
    ],
  },
};

const TradingModeSelector = ({ mode, onModeChange }) => {
  const modes = Object.values(TRADING_MODES);

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-gray-400">Mode:</span>
      <div className="flex bg-gray-700 rounded-lg p-1">
        {modes.map((m) => (
          <button
            key={m.value}
            onClick={() => onModeChange(m.value)}
            className={`px-3 py-1 text-sm rounded-md transition-colors flex items-center gap-1 ${
              mode === m.value
                ? `${m.color} text-white`
                : 'text-gray-300 hover:text-white hover:bg-gray-600'
            }`}
            title={m.description}
          >
            <span>{m.icon}</span>
            <span>{m.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
};

const TradingModePanel = ({ mode, onScanClick }) => {
  const modeConfig = TRADING_MODES[mode];

  return (
    <div className={`rounded-lg p-4 border ${
      mode === 'leaps' ? 'bg-green-900/20 border-green-500/30' :
      mode === 'swing' ? 'bg-yellow-900/20 border-yellow-500/30' :
      'bg-purple-900/20 border-purple-500/30'
    }`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{modeConfig.icon}</span>
          <div>
            <h3 className="text-white font-semibold">{modeConfig.label} Mode</h3>
            <p className="text-xs text-gray-400">{modeConfig.description}</p>
          </div>
        </div>
        <button
          onClick={onScanClick}
          className={`px-4 py-2 rounded-lg text-white text-sm font-medium transition-colors ${modeConfig.color} hover:opacity-90`}
        >
          🔍 Scan Now
        </button>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-3">
        <div>
          <div className="text-xs text-gray-500 uppercase">DTE Range</div>
          <div className="text-sm text-white font-medium">{modeConfig.settings.dte}</div>
        </div>
        <div>
          <div className="text-xs text-gray-500 uppercase">Delta Range</div>
          <div className="text-sm text-white font-medium">{modeConfig.settings.delta}</div>
        </div>
        <div>
          <div className="text-xs text-gray-500 uppercase">Focus</div>
          <div className="text-sm text-white font-medium">{modeConfig.settings.focus}</div>
        </div>
      </div>

      <div className="border-t border-gray-700 pt-3">
        <div className="text-xs text-gray-500 uppercase mb-2">💡 Tips for {modeConfig.label}</div>
        <ul className="space-y-1">
          {modeConfig.tips.map((tip, idx) => (
            <li key={idx} className="text-xs text-gray-300 flex items-start gap-1">
              <span className="text-gray-500">•</span>
              <span>{tip}</span>
            </li>
          ))}
        </ul>
      </div>

      {mode !== 'custom' && (
        <div className="mt-3 pt-3 border-t border-gray-700">
          <div className="text-xs text-gray-500 mb-2">Recommended Presets:</div>
          <div className="flex flex-wrap gap-1">
            {modeConfig.settings.presets.map((preset) => (
              <span
                key={preset}
                className="text-xs px-2 py-0.5 bg-gray-700 text-gray-300 rounded"
              >
                {preset.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const LastUpdated = ({ timestamp, onRefresh, isRefreshing }) => {
  if (!timestamp) return null;

  const time = new Date(timestamp).toLocaleTimeString();

  return (
    <div className="flex items-center gap-2 text-xs text-gray-500">
      <span>Updated: {time}</span>
      <button
        onClick={onRefresh}
        disabled={isRefreshing}
        className={`hover:text-gray-300 transition-colors ${isRefreshing ? 'animate-spin' : ''}`}
        title="Refresh data"
      >
        🔄
      </button>
    </div>
  );
};

export default function CommandCenter() {
  const navigate = useNavigate();
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [tradingMode, setTradingMode] = useState(() => {
    // Persist mode in localStorage
    return localStorage.getItem('tradingMode') || 'leaps';
  });
  const [chatOpen, setChatOpen] = useState(false);
  const [explanation, setExplanation] = useState(null);

  // Macro signal state
  const [mriData, setMriData] = useState(null);
  const [macroEvents, setMacroEvents] = useState(null);
  const [divergences, setDivergences] = useState(null);
  const [macroLoading, setMacroLoading] = useState(true);

  // Save mode to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('tradingMode', tradingMode);
  }, [tradingMode]);

  // Fetch dashboard data
  const fetchDashboard = useCallback(async (isRefresh = false) => {
    try {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);

      const data = await getDashboard();
      setDashboardData(data);
    } catch (err) {
      console.error('Failed to fetch dashboard:', err);
      setError('Failed to load dashboard data. Please try again.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Fetch macro signal data
  const fetchMacroData = useCallback(async () => {
    try {
      setMacroLoading(true);
      const [mri, events, divs] = await Promise.all([
        getMRI().catch(() => null),
        getMacroEvents(30).catch(() => null),
        getMacroDivergences().catch(() => null),
      ]);

      if (mri) setMriData(mri);
      if (events) setMacroEvents(events);
      if (divs) setDivergences(divs.divergences || []);
    } catch (err) {
      console.error('Failed to fetch macro data:', err);
    } finally {
      setMacroLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchDashboard();
    fetchMacroData();

    // Auto-refresh every 5 minutes
    const interval = setInterval(() => {
      fetchDashboard(true);
      fetchMacroData();
    }, 5 * 60 * 1000);

    return () => clearInterval(interval);
  }, [fetchDashboard, fetchMacroData]);

  // Handle scan button click - navigate to screener with mode preset
  const handleScanClick = () => {
    const modeConfig = TRADING_MODES[tradingMode];
    const defaultPreset = modeConfig.settings.presets[0];
    // Navigate to screener with preset as query param
    navigate(`/screener?preset=${defaultPreset}&mode=${tradingMode}`);
  };

  // Handle metric explanation
  const handleExplainMetric = async (metricName, metricValue) => {
    try {
      const result = await explainMetric(metricName, metricValue);
      if (result.success) {
        setExplanation({
          name: metricName,
          value: metricValue,
          ...result.explanation,
        });
      }
    } catch (err) {
      console.error('Failed to explain metric:', err);
    }
  };

  // Handle catalyst feed refresh
  const handleRefreshCatalysts = async () => {
    try {
      const data = await getCatalystFeed(20);
      setDashboardData((prev) => ({
        ...prev,
        catalysts: data,
      }));
    } catch (err) {
      console.error('Failed to refresh catalysts:', err);
    }
  };

  // Close explanation modal
  const closeExplanation = () => setExplanation(null);

  if (error && !dashboardData) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-xl text-white mb-2">Error Loading Dashboard</h2>
          <p className="text-gray-400 mb-4">{error}</p>
          <button
            onClick={() => fetchDashboard()}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <div className="bg-gray-800 border-b border-gray-700">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <h1 className="text-xl font-bold flex items-center gap-2">
                <span>🎯</span>
                Command Center
              </h1>
              <TradingModeSelector mode={tradingMode} onModeChange={setTradingMode} />
            </div>
            <div className="flex items-center gap-4">
              <LastUpdated
                timestamp={dashboardData?.timestamp}
                onRefresh={() => fetchDashboard(true)}
                isRefreshing={refreshing}
              />
              <button
                onClick={() => setChatOpen(true)}
                className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors text-sm"
              >
                <span>🤖</span>
                <span>AI Copilot</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Trading Mode Panel - Shows current mode settings */}
        <div className="mb-6">
          <TradingModePanel mode={tradingMode} onScanClick={handleScanClick} />
        </div>

        {/* Morning Brief */}
        <div className="mb-6">
          <MorningBrief
            data={dashboardData?.morning_brief ? {
              brief: {
                ...dashboardData.morning_brief,
                // Add mode-specific context
                recommended_focus: tradingMode === 'leaps'
                  ? dashboardData.morning_brief?.recommended_focus || 'Look for low IV opportunities'
                  : tradingMode === 'swing'
                  ? 'Focus on momentum and technical breakouts'
                  : dashboardData.morning_brief?.recommended_focus
              },
              ai_powered: true
            } : null}
            loading={loading}
            onAskFollowUp={() => setChatOpen(true)}
            tradingMode={tradingMode}
          />
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Market Data */}
          <div className="lg:col-span-2 space-y-6">
            {/* Market Pulse */}
            <MarketPulse
              data={dashboardData?.market}
              loading={loading}
            />

            {/* Sector Heatmap */}
            <SectorHeatmap
              data={dashboardData?.market?.sectors}
              loading={loading}
            />

            {/* Catalyst Feed */}
            <CatalystFeed
              data={dashboardData?.catalysts}
              loading={loading}
              onRefresh={handleRefreshCatalysts}
              onItemClick={(item) => {
                if (item.url) {
                  window.open(item.url, '_blank');
                }
              }}
            />
          </div>

          {/* Right Column - Widgets */}
          <div className="space-y-6">
            {/* Macro Risk Index */}
            <MRIGauge
              data={mriData}
              loading={macroLoading}
              onExplain={handleExplainMetric}
            />

            {/* Divergence Alerts */}
            <DivergenceAlert
              divergences={divergences}
              loading={macroLoading}
            />

            {/* Fear & Greed */}
            <FearGreedGauge
              data={dashboardData?.market?.fear_greed}
              loading={loading}
              onExplain={handleExplainMetric}
            />

            {/* Polymarket / Macro Events */}
            <MacroEventDashboard
              initialData={macroEvents}
              loading={macroLoading}
            />

            {/* Financial News */}
            <NewsWidget
              data={dashboardData?.rss_news}
              loading={loading}
              onNewsClick={(item) => {
                console.log('News clicked:', item.title);
              }}
            />

            {/* Quick Actions */}
            <div className="bg-gray-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
                Quick Actions
              </h3>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={handleScanClick}
                  className="flex items-center justify-center gap-2 p-3 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors text-sm font-medium"
                >
                  <span>🔍</span>
                  <span>Scan {TRADING_MODES[tradingMode].label}</span>
                </button>
                <button
                  onClick={() => setChatOpen(true)}
                  className="flex items-center justify-center gap-2 p-3 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-sm"
                >
                  <span>💬</span>
                  <span>Ask AI</span>
                </button>
                <a
                  href="/screener"
                  className="flex items-center justify-center gap-2 p-3 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-sm"
                >
                  <span>🎛️</span>
                  <span>Full Screener</span>
                </a>
                <a
                  href="/settings"
                  className="flex items-center justify-center gap-2 p-3 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors text-sm"
                >
                  <span>⚙️</span>
                  <span>Settings</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* AI Copilot Chat */}
      <CopilotChat
        isOpen={chatOpen}
        onClose={() => setChatOpen(false)}
        context={{
          current_page: 'command_center',
          market_summary: dashboardData?.market?.market_condition,
          trading_mode: tradingMode,
          mode_settings: TRADING_MODES[tradingMode].settings,
        }}
        isAvailable={dashboardData?.copilot_available}
      />

      {/* Metric Explanation Modal */}
      {explanation && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={closeExplanation}
        >
          <div
            className="bg-gray-800 rounded-lg p-6 max-w-md mx-4 border border-gray-700"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white capitalize">
                {explanation.name?.replace(/_/g, ' ')}
              </h3>
              <button
                onClick={closeExplanation}
                className="text-gray-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-sm">
              <div>
                <div className="text-gray-400 mb-1">Current Value</div>
                <div className="text-white text-lg font-bold">{explanation.value}</div>
              </div>

              <div>
                <div className="text-gray-400 mb-1">Definition</div>
                <div className="text-gray-200">{explanation.definition}</div>
              </div>

              <div>
                <div className="text-gray-400 mb-1">What This Means</div>
                <div className="text-gray-200">{explanation.current_interpretation}</div>
              </div>

              <div>
                <div className="text-gray-400 mb-1">Trading Implication</div>
                <div className="text-gray-200">{explanation.trading_implication}</div>
              </div>

              {explanation.action_hint && (
                <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3">
                  <div className="text-blue-400 text-xs uppercase mb-1">Pro Tip</div>
                  <div className="text-gray-200">{explanation.action_hint}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
