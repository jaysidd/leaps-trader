/**
 * Backtesting Page — Configure, run, and analyze strategy backtests
 *
 * Sections:
 * 1. Configuration form (symbol, strategy, timeframe, dates, capital)
 * 2. Results dashboard (metrics, equity curve, trade log)
 * 3. History table of past backtests
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { createChart, LineSeries } from 'lightweight-charts';
import useBacktestStore from '../stores/backtestStore';

// ─── Strategy metadata ───────────────────────────────────────────────
const STRATEGIES = [
  { value: 'orb_breakout', label: 'ORB Breakout', timeframes: ['5m', '15m'] },
  { value: 'vwap_pullback', label: 'VWAP Pullback', timeframes: ['5m', '15m', '1h'] },
  { value: 'range_breakout', label: 'Range Breakout', timeframes: ['15m', '1h', '1d'] },
  { value: 'trend_following', label: 'Trend Following', timeframes: ['1h', '1d'] },
  { value: 'mean_reversion', label: 'Mean Reversion', timeframes: ['1d'] },
];

const CAP_SIZES = [
  { value: 'large_cap', label: 'Large Cap' },
  { value: 'mid_cap', label: 'Mid Cap' },
  { value: 'small_cap', label: 'Small Cap' },
];

// ─── Helpers ─────────────────────────────────────────────────────────
function formatDate(d) {
  return new Date(d).toISOString().split('T')[0];
}

function sixMonthsAgo() {
  const d = new Date();
  d.setMonth(d.getMonth() - 6);
  return formatDate(d);
}

function today() {
  return formatDate(new Date());
}

// ═════════════════════════════════════════════════════════════════════════════
// Stat Card Component
// ═════════════════════════════════════════════════════════════════════════════

function StatCard({ label, value, suffix = '', color = 'blue', icon }) {
  const colorMap = {
    blue: 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
    green: 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300',
    red: 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300',
    yellow: 'bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300',
    purple: 'bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300',
    gray: 'bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-300',
  };

  return (
    <div className={`rounded-xl p-4 ${colorMap[color] || colorMap.gray}`}>
      <div className="flex items-center gap-2 mb-1">
        {icon && <span className="text-lg">{icon}</span>}
        <p className="text-xs font-medium uppercase tracking-wide opacity-70">{label}</p>
      </div>
      <p className="text-2xl font-bold">
        {value !== null && value !== undefined ? value : '—'}{suffix}
      </p>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Equity Curve Chart
// ═════════════════════════════════════════════════════════════════════════════

function EquityCurve({ data, totalReturn }) {
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!chartContainerRef.current || !data || data.length === 0) return;

    // Clean up previous chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const isDark = document.documentElement.classList.contains('dark');

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 300,
      layout: {
        background: { color: isDark ? '#1f2937' : '#ffffff' },
        textColor: isDark ? '#9ca3af' : '#6b7280',
      },
      grid: {
        vertLines: { color: isDark ? '#374151' : '#e5e7eb' },
        horzLines: { color: isDark ? '#374151' : '#e5e7eb' },
      },
      rightPriceScale: {
        borderColor: isDark ? '#374151' : '#e5e7eb',
      },
      timeScale: {
        borderColor: isDark ? '#374151' : '#e5e7eb',
        timeVisible: true,
      },
    });

    const lineColor = totalReturn >= 0 ? '#10b981' : '#ef4444';

    const series = chart.addSeries(LineSeries, {
      color: lineColor,
      lineWidth: 2,
      crosshairMarkerVisible: true,
      priceFormat: {
        type: 'price',
        precision: 0,
        minMove: 1,
      },
    });

    // Convert data to lightweight-charts format
    const chartData = data.map(point => {
      // Parse "YYYY-MM-DD HH:MM" format
      const parts = point.date.split(' ');
      const datePart = parts[0];
      const timePart = parts[1] || '00:00';
      const [year, month, day] = datePart.split('-').map(Number);
      const [hour, minute] = timePart.split(':').map(Number);

      // Convert to Unix timestamp
      const dt = new Date(year, month - 1, day, hour, minute);
      return {
        time: Math.floor(dt.getTime() / 1000),
        value: point.value,
      };
    }).filter(p => !isNaN(p.time) && p.value !== null);

    if (chartData.length > 0) {
      series.setData(chartData);
      chart.timeScale().fitContent();
    }

    chartRef.current = chart;

    // Resize handler
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [data, totalReturn]);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border border-gray-200 dark:border-gray-700">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
        Equity Curve
      </h3>
      <div ref={chartContainerRef} />
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Trade Log Table
// ═════════════════════════════════════════════════════════════════════════════

function TradeLog({ trades }) {
  if (!trades || trades.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
          Trade Log
        </h3>
        <p className="text-gray-500 dark:text-gray-400 text-sm">No trades executed during this backtest.</p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm border border-gray-200 dark:border-gray-700">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
        Trade Log ({trades.length} trades)
      </h3>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">#</th>
              <th className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Entry</th>
              <th className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Exit</th>
              <th className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Dir</th>
              <th className="text-right py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Entry $</th>
              <th className="text-right py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Exit $</th>
              <th className="text-right py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Size</th>
              <th className="text-right py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">P&L $</th>
              <th className="text-right py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">P&L %</th>
              <th className="text-right py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Bars</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i} className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30">
                <td className="py-2 px-3 text-gray-500 dark:text-gray-400">{i + 1}</td>
                <td className="py-2 px-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">{t.entry_date}</td>
                <td className="py-2 px-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">{t.exit_date}</td>
                <td className="py-2 px-3">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                    t.direction === 'buy'
                      ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400'
                      : 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400'
                  }`}>
                    {t.direction?.toUpperCase()}
                  </span>
                </td>
                <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">${t.entry_price?.toFixed(2)}</td>
                <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">${t.exit_price?.toFixed(2)}</td>
                <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">{t.size}</td>
                <td className={`py-2 px-3 text-right font-medium ${
                  t.pnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                }`}>
                  {t.pnl >= 0 ? '+' : ''}${t.pnl?.toFixed(2)}
                </td>
                <td className={`py-2 px-3 text-right font-medium ${
                  t.pnl_pct >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                }`}>
                  {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct?.toFixed(2)}%
                </td>
                <td className="py-2 px-3 text-right text-gray-500 dark:text-gray-400">{t.bars_held}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Main Page Component
// ═════════════════════════════════════════════════════════════════════════════

export default function Backtesting() {
  const currentResult = useBacktestStore(state => state.currentResult);
  const backtests = useBacktestStore(state => state.backtests);
  const running = useBacktestStore(state => state.running);
  const error = useBacktestStore(state => state.error);
  const runBacktest = useBacktestStore(state => state.runBacktest);
  const fetchBacktests = useBacktestStore(state => state.fetchBacktests);
  const loadResult = useBacktestStore(state => state.loadResult);
  const deleteBacktest = useBacktestStore(state => state.deleteBacktest);
  const clearError = useBacktestStore(state => state.clearError);
  const clearResult = useBacktestStore(state => state.clearResult);
  const stopPolling = useBacktestStore(state => state.stopPolling);

  // ─── Form State ────────────────────────────────────────────────
  const [symbol, setSymbol] = useState('AAPL');
  const [strategy, setStrategy] = useState('orb_breakout');
  const [timeframe, setTimeframe] = useState('5m');
  const [capSize, setCapSize] = useState('large_cap');
  const [startDate, setStartDate] = useState(sixMonthsAgo());
  const [endDate, setEndDate] = useState(today());
  const [capital, setCapital] = useState(100000);
  const [positionPct, setPositionPct] = useState(10);

  // Load history on mount
  useEffect(() => {
    fetchBacktests();
    return () => stopPolling();
  }, []);

  // Update available timeframes when strategy changes
  const selectedStrategy = STRATEGIES.find(s => s.value === strategy);
  const availableTimeframes = selectedStrategy?.timeframes || ['15m'];

  useEffect(() => {
    if (!availableTimeframes.includes(timeframe)) {
      setTimeframe(availableTimeframes[0]);
    }
  }, [strategy]);

  // ─── Handlers ──────────────────────────────────────────────────
  const handleRun = async () => {
    clearError();
    try {
      await runBacktest({
        symbol: symbol.toUpperCase().trim(),
        strategy,
        timeframe,
        cap_size: capSize,
        start_date: startDate,
        end_date: endDate,
        initial_capital: capital,
        position_size_pct: positionPct,
      });
    } catch (err) {
      // Error already set in store
    }
  };

  const handleLoadResult = async (id) => {
    clearError();
    await loadResult(id);
  };

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    if (window.confirm('Delete this backtest?')) {
      try {
        await deleteBacktest(id);
      } catch (err) {
        // Error set in store
      }
    }
  };

  const r = currentResult;
  const isCompleted = r?.status === 'completed';

  // ─── Render ────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 py-8 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Backtesting</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            Test your trading strategies against historical data
          </p>
        </div>

        {/* Error Banner */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg flex justify-between items-center">
            <p className="text-red-700 dark:text-red-300 text-sm">{error}</p>
            <button onClick={clearError} className="text-red-500 hover:text-red-700 text-sm font-medium">
              Dismiss
            </button>
          </div>
        )}

        {/* ─── Configuration Form ──────────────────────────────── */}
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Configuration
          </h2>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Symbol */}
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Symbol</label>
              <input
                type="text"
                value={symbol}
                onChange={e => setSymbol(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="AAPL"
              />
            </div>

            {/* Strategy */}
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Strategy</label>
              <select
                value={strategy}
                onChange={e => setStrategy(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500"
              >
                {STRATEGIES.map(s => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>

            {/* Timeframe */}
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Timeframe</label>
              <select
                value={timeframe}
                onChange={e => setTimeframe(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500"
              >
                {availableTimeframes.map(tf => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>

            {/* Cap Size */}
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Cap Size</label>
              <select
                value={capSize}
                onChange={e => setCapSize(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500"
              >
                {CAP_SIZES.map(c => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>

            {/* Start Date */}
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={e => setStartDate(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* End Date */}
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={e => setEndDate(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Initial Capital */}
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Capital ($)</label>
              <input
                type="number"
                value={capital}
                onChange={e => setCapital(Number(e.target.value))}
                min={1000}
                step={1000}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Position Size % */}
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Position Size %</label>
              <input
                type="number"
                value={positionPct}
                onChange={e => setPositionPct(Number(e.target.value))}
                min={1}
                max={100}
                step={1}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Run Button */}
          <div className="mt-5 flex items-center gap-3">
            <button
              onClick={handleRun}
              disabled={running || !symbol.trim()}
              className={`px-6 py-2.5 rounded-lg font-medium text-white transition-colors ${
                running || !symbol.trim()
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              {running ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Running...
                </span>
              ) : (
                'Run Backtest'
              )}
            </button>
            {running && r && (
              <span className="text-sm text-gray-500 dark:text-gray-400">
                Status: {r.status}...
              </span>
            )}
          </div>
        </div>

        {/* ─── Results Section ─────────────────────────────────── */}
        {isCompleted && (
          <>
            {/* Result Header */}
            <div className="mb-4 flex items-center gap-3">
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                Results: {r.symbol} — {STRATEGIES.find(s => s.value === r.strategy)?.label || r.strategy}
              </h2>
              <span className="text-sm text-gray-500 dark:text-gray-400">
                {r.timeframe} | {r.cap_size?.replace('_', ' ')} | {r.start_date} to {r.end_date}
              </span>
            </div>

            {/* Metric Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              <StatCard
                label="Total Return"
                value={r.total_return_pct?.toFixed(2)}
                suffix="%"
                color={r.total_return_pct >= 0 ? 'green' : 'red'}
                icon={r.total_return_pct >= 0 ? '📈' : '📉'}
              />
              <StatCard
                label="Sharpe Ratio"
                value={r.sharpe_ratio?.toFixed(2)}
                color={r.sharpe_ratio >= 1 ? 'green' : r.sharpe_ratio >= 0 ? 'yellow' : 'red'}
                icon="📊"
              />
              <StatCard
                label="Max Drawdown"
                value={r.max_drawdown_pct?.toFixed(2)}
                suffix="%"
                color={r.max_drawdown_pct <= 10 ? 'green' : r.max_drawdown_pct <= 20 ? 'yellow' : 'red'}
                icon="📉"
              />
              <StatCard
                label="Win Rate"
                value={r.win_rate?.toFixed(1)}
                suffix="%"
                color={r.win_rate >= 55 ? 'green' : r.win_rate >= 45 ? 'yellow' : 'red'}
                icon="🎯"
              />
              <StatCard
                label="Total Trades"
                value={r.total_trades}
                color="blue"
                icon="🔄"
              />
              <StatCard
                label="Profit Factor"
                value={r.profit_factor?.toFixed(2)}
                color={r.profit_factor >= 1.5 ? 'green' : r.profit_factor >= 1 ? 'yellow' : 'red'}
                icon="💰"
              />
              <StatCard
                label="Avg Win"
                value={r.avg_win_pct?.toFixed(2)}
                suffix="%"
                color="green"
                icon="✅"
              />
              <StatCard
                label="Avg Loss"
                value={r.avg_loss_pct?.toFixed(2)}
                suffix="%"
                color="red"
                icon="❌"
              />
            </div>

            {/* Secondary Stats Row */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
              <StatCard label="Final Value" value={`$${r.final_value?.toLocaleString()}`} color="gray" />
              <StatCard label="Winning" value={r.winning_trades} color="green" />
              <StatCard label="Losing" value={r.losing_trades} color="red" />
              <StatCard label="Best Trade" value={r.best_trade_pct?.toFixed(2)} suffix="%" color="green" />
              <StatCard label="Worst Trade" value={r.worst_trade_pct?.toFixed(2)} suffix="%" color="red" />
            </div>

            {/* Equity Curve */}
            {r.equity_curve && r.equity_curve.length > 0 && (
              <div className="mb-6">
                <EquityCurve data={r.equity_curve} totalReturn={r.total_return_pct} />
              </div>
            )}

            {/* Trade Log */}
            <div className="mb-6">
              <TradeLog trades={r.trade_log} />
            </div>
          </>
        )}

        {/* Running / Failed states */}
        {r && r.status === 'running' && (
          <div className="bg-white dark:bg-gray-800 rounded-xl p-8 shadow-sm border border-gray-200 dark:border-gray-700 mb-6 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-gray-700 dark:text-gray-300 font-medium">Running backtest...</p>
            <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
              Fetching data and simulating {r.symbol} with {STRATEGIES.find(s => s.value === r.strategy)?.label || r.strategy}
            </p>
          </div>
        )}

        {r && r.status === 'failed' && (
          <div className="bg-red-50 dark:bg-red-900/20 rounded-xl p-6 border border-red-200 dark:border-red-800 mb-6">
            <h3 className="text-red-700 dark:text-red-400 font-semibold text-lg mb-2">Backtest Failed</h3>
            <p className="text-red-600 dark:text-red-300 text-sm">{r.error_message || 'Unknown error'}</p>
            <button
              onClick={clearResult}
              className="mt-3 px-4 py-1.5 bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300 rounded-lg text-sm font-medium hover:bg-red-200 dark:hover:bg-red-900/60"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* ─── History Section ─────────────────────────────────── */}
        {backtests.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Backtest History
            </h2>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Date</th>
                    <th className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Symbol</th>
                    <th className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Strategy</th>
                    <th className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">TF</th>
                    <th className="text-right py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Return</th>
                    <th className="text-right py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Sharpe</th>
                    <th className="text-right py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Trades</th>
                    <th className="text-center py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Status</th>
                    <th className="text-center py-2 px-3 text-gray-600 dark:text-gray-400 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {backtests.map(bt => (
                    <tr
                      key={bt.id}
                      onClick={() => bt.status === 'completed' && handleLoadResult(bt.id)}
                      className={`border-b border-gray-100 dark:border-gray-700/50 ${
                        bt.status === 'completed' ? 'cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/10' : ''
                      } ${r?.id === bt.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}
                    >
                      <td className="py-2 px-3 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                        {bt.created_at ? new Date(bt.created_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="py-2 px-3 font-medium text-gray-900 dark:text-white">{bt.symbol}</td>
                      <td className="py-2 px-3 text-gray-700 dark:text-gray-300">
                        {STRATEGIES.find(s => s.value === bt.strategy)?.label || bt.strategy}
                      </td>
                      <td className="py-2 px-3 text-gray-500 dark:text-gray-400">{bt.timeframe}</td>
                      <td className={`py-2 px-3 text-right font-medium ${
                        bt.total_return_pct >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                      }`}>
                        {bt.total_return_pct !== null ? `${bt.total_return_pct?.toFixed(2)}%` : '—'}
                      </td>
                      <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                        {bt.sharpe_ratio !== null ? bt.sharpe_ratio?.toFixed(2) : '—'}
                      </td>
                      <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                        {bt.total_trades ?? '—'}
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          bt.status === 'completed' ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400' :
                          bt.status === 'failed' ? 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400' :
                          bt.status === 'running' ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400' :
                          'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                        }`}>
                          {bt.status}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-center">
                        <button
                          onClick={e => handleDelete(e, bt.id)}
                          className="text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                          title="Delete"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
