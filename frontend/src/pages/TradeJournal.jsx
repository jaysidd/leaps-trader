/**
 * TradeJournal page — view all bot-executed trades, active positions, and performance
 */
import { useState, useEffect } from 'react';
import botAPI from '../api/bot';

const STATUS_BADGES = {
  open: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  closed: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
  pending_entry: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  pending_exit: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  pending_approval: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  cancelled: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-500',
  error: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

export default function TradeJournal() {
  const [activeTab, setActiveTab] = useState('active');
  const [trades, setTrades] = useState([]);
  const [activeTrades, setActiveTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState({ status: '', symbol: '', asset_type: '', limit: 50 });

  useEffect(() => {
    if (activeTab === 'active') {
      loadActiveTrades();
    } else {
      loadTrades();
    }
  }, [activeTab, filters]);

  const loadActiveTrades = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await botAPI.getActiveTrades();
      setActiveTrades(data || []);
    } catch (err) {
      console.error('Failed to load active trades:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to load active trades');
    } finally {
      setLoading(false);
    }
  };

  const loadTrades = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (filters.status) params.status = filters.status;
      if (filters.symbol) params.symbol = filters.symbol;
      if (filters.asset_type) params.asset_type = filters.asset_type;
      params.limit = filters.limit;

      const data = await botAPI.listTrades(params);
      setTrades(data.trades || []);
      setTotal(data.total || 0);
    } catch (err) {
      console.error('Failed to load trades:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to load trades');
    } finally {
      setLoading(false);
    }
  };

  const tabs = [
    { id: 'active', label: 'Active Positions', count: activeTrades.length },
    { id: 'history', label: 'Trade History', count: total },
  ];

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 py-8 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Trade Journal</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">All bot-executed trades and active positions</p>
        </div>

        {/* Tab Navigation */}
        <div className="mb-6 border-b border-gray-200 dark:border-gray-700">
          <nav className="flex space-x-8">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
                }`}
              >
                {tab.label}
                {tab.count > 0 && (
                  <span className="ml-2 px-2 py-0.5 text-xs rounded-full bg-gray-200 dark:bg-gray-700">
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>

        {/* Filters (history only) */}
        {activeTab === 'history' && (
          <div className="mb-4 flex gap-3 flex-wrap">
            <input
              type="text"
              placeholder="Symbol..."
              value={filters.symbol}
              onChange={e => setFilters(f => ({ ...f, symbol: e.target.value }))}
              className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white w-32"
            />
            <select
              value={filters.status}
              onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}
              className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white"
            >
              <option value="">All Statuses</option>
              <option value="closed">Closed</option>
              <option value="open">Open</option>
              <option value="cancelled">Cancelled</option>
              <option value="error">Error</option>
            </select>
            <select
              value={filters.asset_type}
              onChange={e => setFilters(f => ({ ...f, asset_type: e.target.value }))}
              className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white"
            >
              <option value="">All Types</option>
              <option value="stock">Stocks</option>
              <option value="option">Options</option>
            </select>
          </div>
        )}

        {/* Error Banner */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center justify-between">
            <span className="text-red-700 dark:text-red-400 text-sm">{error}</span>
            <button onClick={() => setError(null)} className="text-red-500 hover:text-red-700 text-lg leading-none">&times;</button>
          </div>
        )}

        {/* Content */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-transparent dark:border-gray-700 overflow-hidden">
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
          ) : activeTab === 'active' ? (
            <TradeTable trades={activeTrades} showExitTargets />
          ) : (
            <TradeTable trades={trades} showPL />
          )}
        </div>
      </div>
    </div>
  );
}

function TradeTable({ trades, showExitTargets = false, showPL = false }) {
  if (trades.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500 dark:text-gray-400">
        No trades found
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 dark:bg-gray-700/50">
          <tr>
            <th className="px-4 py-3 text-left text-gray-600 dark:text-gray-300 font-medium">Symbol</th>
            <th className="px-4 py-3 text-left text-gray-600 dark:text-gray-300 font-medium">Type</th>
            <th className="px-4 py-3 text-left text-gray-600 dark:text-gray-300 font-medium">Direction</th>
            <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">Qty</th>
            <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">Entry</th>
            {showExitTargets && (
              <>
                <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">TP</th>
                <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">SL</th>
              </>
            )}
            {showPL && (
              <>
                <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">Exit</th>
                <th className="px-4 py-3 text-right text-gray-600 dark:text-gray-300 font-medium">P&L</th>
                <th className="px-4 py-3 text-left text-gray-600 dark:text-gray-300 font-medium">Exit Reason</th>
              </>
            )}
            <th className="px-4 py-3 text-left text-gray-600 dark:text-gray-300 font-medium">Status</th>
            <th className="px-4 py-3 text-left text-gray-600 dark:text-gray-300 font-medium">Time</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
          {trades.map((trade, i) => {
            const pl = trade.realized_pl || 0;
            const plPct = trade.realized_pl_pct || 0;
            const plColor = pl > 0 ? 'text-green-600 dark:text-green-400' : pl < 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-500';

            return (
              <tr key={trade.id || i} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{trade.symbol}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{trade.asset_type}</td>
                <td className="px-4 py-3">
                  <span className={trade.direction === 'buy' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                    {trade.direction?.toUpperCase()}
                  </span>
                </td>
                <td className="px-4 py-3 text-right font-mono text-gray-900 dark:text-white">{trade.quantity}</td>
                <td className="px-4 py-3 text-right font-mono text-gray-900 dark:text-white">
                  {trade.entry_price ? `$${trade.entry_price.toFixed(2)}` : '-'}
                </td>
                {showExitTargets && (
                  <>
                    <td className="px-4 py-3 text-right font-mono text-green-600 dark:text-green-400">
                      {trade.take_profit_price ? `$${trade.take_profit_price.toFixed(2)}` : '-'}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-red-600 dark:text-red-400">
                      {trade.stop_loss_price ? `$${trade.stop_loss_price.toFixed(2)}` : '-'}
                    </td>
                  </>
                )}
                {showPL && (
                  <>
                    <td className="px-4 py-3 text-right font-mono text-gray-900 dark:text-white">
                      {trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : '-'}
                    </td>
                    <td className={`px-4 py-3 text-right font-mono font-medium ${plColor}`}>
                      {pl !== 0 ? `${pl >= 0 ? '+' : ''}$${pl.toFixed(2)} (${plPct >= 0 ? '+' : ''}${plPct.toFixed(1)}%)` : '-'}
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400 text-xs">
                      {trade.exit_reason?.replace('_', ' ') || '-'}
                    </td>
                  </>
                )}
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGES[trade.status] || 'bg-gray-100 text-gray-600'}`}>
                    {trade.status?.replace('_', ' ')}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500 dark:text-gray-400 text-xs">
                  {trade.created_at ? new Date(trade.created_at).toLocaleString() : '-'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
