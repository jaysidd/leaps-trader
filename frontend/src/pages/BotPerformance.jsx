/**
 * BotPerformance page — trading bot performance analytics
 * Shows: summary stats, daily performance, equity curve, exit reason breakdown
 */
import { useState, useEffect } from 'react';
import botAPI from '../api/bot';

export default function BotPerformance() {
  const [performance, setPerformance] = useState(null);
  const [dailyRecords, setDailyRecords] = useState([]);
  const [exitReasons, setExitReasons] = useState({});
  const [todayPerf, setTodayPerf] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    loadData();
  }, [days]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const endDate = new Date().toISOString().split('T')[0];
      const startDate = new Date(Date.now() - days * 86400000).toISOString().split('T')[0];

      const [perf, daily, exits, today] = await Promise.all([
        botAPI.getPerformance({ start_date: startDate, end_date: endDate }),
        botAPI.getDailyPerformance({ start_date: startDate, end_date: endDate, limit: days }),
        botAPI.getExitReasonBreakdown({ start_date: startDate, end_date: endDate }),
        botAPI.getTodayPerformance(),
      ]);

      setPerformance(perf);
      setDailyRecords(daily || []);
      setExitReasons(exits || {});
      setTodayPerf(today);
    } catch (err) {
      console.error('Failed to load performance data:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to load performance data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900 flex justify-center items-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const p = performance || {};

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 py-8 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Bot Performance</h1>
            <p className="text-gray-600 dark:text-gray-400 mt-1">
              {p.period?.start} to {p.period?.end}
            </p>
          </div>
          <div className="flex gap-2">
            {[7, 30, 90].map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${
                  days === d
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                }`}
              >
                {d}D
              </button>
            ))}
          </div>
        </div>

        {/* Error Banner */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center justify-between">
            <span className="text-red-700 dark:text-red-400 text-sm">{error}</span>
            <button onClick={() => setError(null)} className="text-red-500 hover:text-red-700 text-lg leading-none">&times;</button>
          </div>
        )}

        {/* Today Banner */}
        {todayPerf && (
          <div className="mb-6 p-4 bg-white dark:bg-gray-800 rounded-lg shadow border border-transparent dark:border-gray-700">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-gray-900 dark:text-white">Today</h3>
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                todayPerf.status === 'running' ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
              }`}>{todayPerf.status}</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mt-3">
              <MiniStat label="P&L" value={`$${(todayPerf.daily_pl || 0).toFixed(2)}`} positive={todayPerf.daily_pl >= 0} />
              <MiniStat label="Trades" value={todayPerf.daily_trades} />
              <MiniStat label="Wins" value={todayPerf.daily_wins} positive />
              <MiniStat label="Losses" value={todayPerf.daily_losses} positive={false} />
              <MiniStat label="Win Rate" value={`${todayPerf.win_rate}%`} positive={todayPerf.win_rate >= 50} />
              <MiniStat label="Positions" value={todayPerf.open_positions} />
            </div>
          </div>
        )}

        {/* Summary Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-6">
          <StatCard label="Total Trades" value={p.total_trades || 0} />
          <StatCard label="Win Rate" value={`${p.win_rate || 0}%`} positive={p.win_rate >= 50} />
          <StatCard label="Total P&L" value={`$${(p.total_pl || 0).toFixed(2)}`} positive={p.total_pl >= 0} />
          <StatCard label="Avg P&L/Trade" value={`$${(p.avg_pl_per_trade || 0).toFixed(2)}`} positive={p.avg_pl_per_trade >= 0} />
          <StatCard label="Profit Factor" value={(p.profit_factor || 0).toFixed(2)} positive={p.profit_factor >= 1} />
          <StatCard label="Max Drawdown" value={`$${(p.max_drawdown || 0).toFixed(2)}`} positive={false} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <StatCard label="Avg Win" value={`$${(p.avg_win || 0).toFixed(2)}`} positive />
          <StatCard label="Avg Loss" value={`$${(p.avg_loss || 0).toFixed(2)}`} positive={false} />
          <StatCard label="Best Trade" value={`$${(p.best_trade || 0).toFixed(2)}`} positive />
          <StatCard label="Worst Trade" value={`$${(p.worst_trade || 0).toFixed(2)}`} positive={false} />
        </div>

        {/* Strategy Breakdown */}
        {p.by_strategy && Object.keys(p.by_strategy).length > 0 && (
          <div className="mb-6 bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-transparent dark:border-gray-700">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">By Strategy</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {Object.entries(p.by_strategy).map(([strategy, data]) => (
                <div key={strategy} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <div className="font-medium text-gray-900 dark:text-white text-sm">{strategy.replace('_', ' ')}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {data.count} trades | {data.wins}W / {data.losses}L
                  </div>
                  <div className={`text-sm font-mono font-medium mt-1 ${data.pl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                    ${data.pl.toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Asset Type Breakdown */}
        {p.by_asset_type && Object.keys(p.by_asset_type).length > 0 && (
          <div className="mb-6 bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-transparent dark:border-gray-700">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">By Asset Type</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(p.by_asset_type).map(([type, data]) => (
                <div key={type} className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <div className="font-medium text-gray-900 dark:text-white capitalize">{type}</div>
                  <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                    {data.count} trades | {data.wins}W / {data.losses}L
                  </div>
                  <div className={`text-lg font-mono font-medium mt-1 ${data.pl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                    ${data.pl.toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Exit Reason Breakdown */}
        {Object.keys(exitReasons).length > 0 && (
          <div className="mb-6 bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-transparent dark:border-gray-700">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Exit Reasons</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(exitReasons).map(([reason, data]) => (
                <div key={reason} className="p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center">
                  <div className="text-sm font-medium text-gray-900 dark:text-white">{reason.replace('_', ' ')}</div>
                  <div className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{data.count}</div>
                  <div className={`text-xs font-mono ${data.total_pl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                    ${data.total_pl.toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Daily Performance Table */}
        {dailyRecords.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-transparent dark:border-gray-700 overflow-hidden">
            <div className="p-6 pb-3">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Daily Breakdown</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-700/50">
                  <tr>
                    <th className="px-4 py-3 text-left text-gray-600 dark:text-gray-300 font-medium">Date</th>
                    <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">Trades</th>
                    <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">W/L</th>
                    <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">Win Rate</th>
                    <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">Net P&L</th>
                    <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">Best</th>
                    <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">Worst</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {dailyRecords.map(d => (
                    <tr key={d.date} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                      <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{d.date}</td>
                      <td className="px-4 py-3 text-right text-gray-900 dark:text-white">{d.trades}</td>
                      <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">{d.wins}W / {d.losses}L</td>
                      <td className="px-4 py-3 text-right text-gray-900 dark:text-white">{d.win_rate?.toFixed(0)}%</td>
                      <td className={`px-4 py-3 text-right font-mono font-medium ${(d.net_pl || 0) >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                        ${(d.net_pl || 0).toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-green-600 dark:text-green-400">${(d.best_trade || 0).toFixed(2)}</td>
                      <td className="px-4 py-3 text-right font-mono text-red-600 dark:text-red-400">${(d.worst_trade || 0).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Empty State */}
        {p.total_trades === 0 && (
          <div className="text-center py-16 bg-white dark:bg-gray-800 rounded-lg shadow border border-transparent dark:border-gray-700">
            <p className="text-gray-500 dark:text-gray-400 text-lg">No trades recorded yet</p>
            <p className="text-gray-400 dark:text-gray-500 text-sm mt-2">
              Configure and start the trading bot in Settings &rarr; Auto Trading
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Helper Components ────────────────────────────────

function StatCard({ label, value, positive }) {
  const colorClass = positive === undefined ? 'text-gray-900 dark:text-white' :
    positive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 border border-transparent dark:border-gray-700">
      <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider">{label}</div>
      <div className={`text-xl font-bold mt-1 font-mono ${colorClass}`}>{value}</div>
    </div>
  );
}

function MiniStat({ label, value, positive }) {
  const colorClass = positive === undefined ? 'text-gray-900 dark:text-white' :
    positive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400';

  return (
    <div>
      <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
      <div className={`font-bold font-mono ${colorClass}`}>{value}</div>
    </div>
  );
}
