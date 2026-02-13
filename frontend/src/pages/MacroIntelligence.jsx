/**
 * Macro Intelligence Page
 * Deep-dive into catalyst data, liquidity, and Trade Readiness
 * Drill-down from Command Center for detailed macro analysis
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getCatalystSummary,
  getLiquidityCatalyst,
  getLiquidityHistory,
  getCatalystHistory,
} from '../api/macroIntelligence';
import { getMRI, explainMetric } from '../api/commandCenter';
import {
  TradeReadinessGauge,
  LiquidityWidget,
  MRIGauge,
} from '../components/command-center';

// Placeholder components for future phases
const PlaceholderCatalyst = ({ title, description, metrics }) => (
  <div className="bg-gray-800 rounded-lg p-4 opacity-60">
    <div className="flex items-center justify-between mb-2">
      <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
        {title}
      </h3>
      <span className="text-xs text-blue-400 bg-blue-900/30 px-2 py-0.5 rounded">Coming Soon</span>
    </div>
    <p className="text-sm text-gray-500 mb-3">{description}</p>
    {metrics && (
      <div className="text-xs text-gray-600">
        Expected metrics: {metrics.join(', ')}
      </div>
    )}
  </div>
);

export default function MacroIntelligence() {
  const navigate = useNavigate();

  // Data states
  const [catalystSummary, setCatalystSummary] = useState(null);
  const [liquidityData, setLiquidityData] = useState(null);
  const [mriData, setMriData] = useState(null);
  const [liquidityHistory, setLiquidityHistory] = useState(null);

  // UI states
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  // Explanation modal state
  const [explaining, setExplaining] = useState(false);
  const [explanation, setExplanation] = useState(null);

  const fetchData = useCallback(async (showRefreshing = false) => {
    try {
      if (showRefreshing) setRefreshing(true);
      else setLoading(true);
      setError(null);

      const [summary, liquidity, mri, history] = await Promise.all([
        getCatalystSummary(),
        getLiquidityCatalyst(),
        getMRI(),
        getLiquidityHistory(168), // 7 days
      ]);

      setCatalystSummary(summary);
      setLiquidityData(liquidity);
      setMriData(mri);
      setLiquidityHistory(history);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Error fetching macro intelligence data:', err);
      setError(err.message || 'Failed to load macro intelligence data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // Refresh every 5 minutes
    const interval = setInterval(() => fetchData(true), 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleExplain = async (metricName, value) => {
    try {
      setExplaining(true);
      const result = await explainMetric(
        metricName,
        value,
        `Current macro conditions from Macro Intelligence page`
      );
      setExplanation(result);
    } catch (err) {
      console.error('Error getting explanation:', err);
    } finally {
      setExplaining(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 text-white p-6">
        <div className="max-w-7xl mx-auto">
          <div className="animate-pulse space-y-4">
            <div className="h-8 bg-gray-800 rounded w-1/3"></div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="h-64 bg-gray-800 rounded"></div>
              <div className="h-64 bg-gray-800 rounded"></div>
            </div>
            <div className="h-48 bg-gray-800 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => navigate('/command-center')}
                className="text-gray-400 hover:text-white"
              >
                ← Back
              </button>
              <h1 className="text-2xl font-bold">Macro Intelligence</h1>
            </div>
            <p className="text-gray-400 text-sm mt-1">
              Deep-dive into liquidity, catalysts, and market conditions
            </p>
          </div>

          <div className="flex items-center gap-4">
            {lastUpdated && (
              <span className="text-xs text-gray-500">
                Updated: {lastUpdated.toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={() => fetchData(true)}
              disabled={refreshing}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                refreshing
                  ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700 text-white'
              }`}
            >
              {refreshing ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
        </div>

        {/* Error Banner */}
        {error && (
          <div className="mb-6 p-4 bg-red-900/50 border border-red-500 rounded-lg text-red-200">
            {error}
          </div>
        )}

        {/* Main Content Grid */}
        <div className="space-y-6">
          {/* Section 1: Trade Readiness (Primary) */}
          <section>
            <h2 className="text-lg font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <span className="text-xl">📊</span> Trade Readiness
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <TradeReadinessGauge
                data={catalystSummary}
                loading={loading}
                onExplain={handleExplain}
              />
              <MRIGauge
                data={mriData}
                loading={loading}
                onExplain={handleExplain}
              />
            </div>
          </section>

          {/* Section 2: Liquidity & Financial Conditions */}
          <section>
            <h2 className="text-lg font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <span className="text-xl">💧</span> Liquidity & Financial Conditions
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2">
                <LiquidityWidget
                  data={liquidityData}
                  loading={loading}
                  onExplain={handleExplain}
                />
              </div>
              <div className="bg-gray-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  Liquidity Trend (7d)
                </h3>
                {liquidityHistory?.history?.length > 0 ? (
                  <div className="h-32 flex items-end gap-1">
                    {liquidityHistory.history.slice(-24).map((point, idx) => {
                      const score = point.score || 50;
                      const height = Math.max(10, score);
                      const color = score > 66 ? '#dc2626' : score < 33 ? '#22c55e' : '#eab308';
                      return (
                        <div
                          key={idx}
                          className="flex-1 rounded-t transition-all hover:opacity-80"
                          style={{ height: `${height}%`, backgroundColor: color }}
                          title={`${new Date(point.timestamp).toLocaleString()}: ${score.toFixed(0)}`}
                        />
                      );
                    })}
                  </div>
                ) : (
                  <div className="h-32 flex items-center justify-center text-gray-500 text-sm">
                    No historical data available
                  </div>
                )}
                <div className="flex justify-between mt-2 text-xs text-gray-500">
                  <span>7 days ago</span>
                  <span>Now</span>
                </div>
              </div>
            </div>
          </section>

          {/* Section 3: Options Positioning (Phase 3 - Placeholder) */}
          <section>
            <h2 className="text-lg font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <span className="text-xl">📉</span> Options Positioning
            </h2>
            <PlaceholderCatalyst
              title="Index-Level Options Positioning"
              description="Put/Call ratio, IV rank, gamma exposure, and OI walls for SPY/QQQ"
              metrics={['Put/Call Ratio', 'IV Rank', 'GEX', 'Max Pain', 'OI Walls']}
            />
          </section>

          {/* Section 4: Tier 2 Catalysts (Placeholders) */}
          <section>
            <h2 className="text-lg font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <span className="text-xl">⚠️</span> Additional Catalysts
              <span className="text-xs text-gray-500 font-normal">(Tier 2 - Coming Soon)</span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <PlaceholderCatalyst
                title="Credit Stress"
                description="High yield and investment grade spreads for early risk-off warning"
                metrics={['HY OAS', 'IG OAS', 'Spread Changes']}
              />
              <PlaceholderCatalyst
                title="Volatility Structure"
                description="VIX term structure, VVIX, and skew analysis"
                metrics={['VIX', 'VIX3M', 'Term Slope', 'VVIX']}
              />
              <PlaceholderCatalyst
                title="Event Density"
                description="Upcoming macro events weighted by importance"
                metrics={['Event Count', 'Importance Score', 'Next Events']}
              />
            </div>
          </section>

          {/* Section 5: Cross-Asset Confirmation (Tier 3 - Placeholder) */}
          <section>
            <h2 className="text-lg font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <span className="text-xl">🌐</span> Cross-Asset Confirmation
              <span className="text-xs text-gray-500 font-normal">(Tier 3 - Coming Soon)</span>
            </h2>
            <PlaceholderCatalyst
              title="Cross-Asset Analysis"
              description="Confirmation signals from correlated assets (bonds, dollar, commodities)"
              metrics={['SPY', 'TLT', 'DXY', 'GLD', 'USO', 'Divergence Score']}
            />
          </section>
        </div>

        {/* Explanation Modal */}
        {explanation && (
          <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
            onClick={() => setExplanation(null)}
          >
            <div
              className="bg-gray-800 rounded-lg p-6 max-w-lg w-full"
              onClick={(e) => e.stopPropagation()}
            >
              <h3 className="text-lg font-semibold mb-3">
                {explanation.metric_name || 'Explanation'}
              </h3>
              <p className="text-gray-300 whitespace-pre-wrap">
                {explanation.explanation || 'No explanation available'}
              </p>
              <button
                onClick={() => setExplanation(null)}
                className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm"
              >
                Close
              </button>
            </div>
          </div>
        )}

        {/* Loading Overlay for Explanation */}
        {explaining && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-gray-800 rounded-lg p-6">
              <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto"></div>
              <p className="text-gray-300 mt-3">Getting explanation...</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
