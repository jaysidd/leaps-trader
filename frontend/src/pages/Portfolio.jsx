/**
 * Portfolio Page
 * Modern portfolio view with multi-broker support
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import usePortfolioStore from '../stores/portfolioStore';
import usePriceStreamStore from '../stores/priceStreamStore';
import Card from '../components/common/Card';
import StockDetail from '../components/screener/StockDetail';
import { stocksAPI } from '../api/stocks';
import { screenerAPI } from '../api/screener';
import tradingAPI from '../api/trading';
import { getChangeColor, formatChangePercent } from '../utils/formatters';

// =============================================================================
// Sub-components
// =============================================================================

// Broker logos and colors
const BROKER_CONFIG = {
  robinhood: {
    name: 'Robinhood',
    logo: '🟢',
    color: 'bg-green-500',
    textColor: 'text-green-500',
    bgLight: 'bg-green-50 dark:bg-green-900/20',
  },
  alpaca: {
    name: 'Alpaca',
    logo: '🦙',
    color: 'bg-yellow-500',
    textColor: 'text-yellow-500',
    bgLight: 'bg-yellow-50 dark:bg-yellow-900/20',
  },
  webull: {
    name: 'Webull',
    logo: '🐂',
    color: 'bg-blue-500',
    textColor: 'text-blue-500',
    bgLight: 'bg-blue-50 dark:bg-blue-900/20',
  },
  td_ameritrade: {
    name: 'TD Ameritrade',
    logo: '💚',
    color: 'bg-emerald-500',
    textColor: 'text-emerald-500',
    bgLight: 'bg-emerald-50 dark:bg-emerald-900/20',
  },
};

// Format currency
const formatCurrency = (value, decimals = 2) => {
  if (value === null || value === undefined) return '--';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
};

// Format percentage
const formatPercent = (value, decimals = 2) => {
  if (value === null || value === undefined) return '--';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
};

// P/L Color
const getPLColor = (value) => {
  if (value > 0) return 'text-green-500';
  if (value < 0) return 'text-red-500';
  return 'text-gray-500';
};

// =============================================================================
// Connect Broker Modal
// =============================================================================

function ConnectBrokerModal({ broker, onClose, onConnect }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [accountName, setAccountName] = useState('');
  const [showMFA, setShowMFA] = useState(false);
  const [verificationInfo, setVerificationInfo] = useState(null);
  const [pendingConnection, setPendingConnection] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const { submitMFA } = usePortfolioStore();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    // If we're in the MFA/verification step, use submitMFA from the store
    if (showMFA && pendingConnection) {
      const result = await submitMFA(pendingConnection.id, mfaCode);
      setLoading(false);

      if (result.success) {
        onClose();
        return;
      }

      setError(result.error || 'Verification failed. Check the code and try again.');
      setMfaCode('');
      return;
    }

    // Initial connection attempt
    const result = await onConnect(
      broker.type,
      username,
      password,
      null, // Don't pass MFA code on initial attempt
      accountName || null
    );

    setLoading(false);

    if (result.requires_mfa || result.requires_verification) {
      setShowMFA(true);
      setPendingConnection(result.connection);
      if (result.verification) {
        setVerificationInfo(result.verification);
      }
      return;
    }

    if (result.success) {
      onClose();
    } else {
      setError(result.error || 'Connection failed');
    }
  };

  const config = BROKER_CONFIG[broker.type] || {};

  // Determine the verification method label
  const verifyLabel = verificationInfo?.challenge_type === 'email'
    ? 'email'
    : verificationInfo?.challenge_type === 'sms'
      ? 'SMS'
      : 'authenticator app or SMS';

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-md w-full">
        {/* Header */}
        <div className={`${config.bgLight} p-6 rounded-t-xl border-b dark:border-gray-700`}>
          <div className="flex items-center gap-3">
            <span className="text-4xl">{config.logo}</span>
            <div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                Connect to {config.name}
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {showMFA
                  ? 'Enter the verification code to continue'
                  : 'Enter your credentials to link your account'}
              </p>
            </div>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          {!showMFA ? (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Email / Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="your@email.com"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="••••••••"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Account Nickname (optional)
                </label>
                <input
                  type="text"
                  value={accountName}
                  onChange={(e) => setAccountName(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="e.g., Main Trading Account"
                />
              </div>
            </>
          ) : (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Verification Code
              </label>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                Enter the code sent via {verifyLabel}
              </p>
              <input
                type="text"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
                className="w-full px-4 py-3 text-center text-2xl tracking-widest border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="000000"
                maxLength={6}
                autoFocus
                required
              />
            </div>
          )}

          {/* Security notice */}
          <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg">
            <p className="text-xs text-blue-700 dark:text-blue-400">
              🔒 Your credentials are encrypted and only used to establish a secure connection.
            </p>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className={`flex-1 px-4 py-2 rounded-lg text-white font-medium transition-colors ${
                loading
                  ? 'bg-gray-400 cursor-not-allowed'
                  : `${config.color} hover:opacity-90`
              }`}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  {showMFA ? 'Verifying...' : 'Connecting...'}
                </span>
              ) : showMFA ? (
                'Verify'
              ) : (
                'Connect'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// =============================================================================
// Portfolio Summary Card
// =============================================================================

function PortfolioSummaryCard({ summary }) {
  if (!summary || !summary.connected) {
    return (
      <Card className="col-span-full">
        <div className="text-center py-12">
          <span className="text-6xl mb-4 block">📊</span>
          <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            No Broker Connected
          </h3>
          <p className="text-gray-600 dark:text-gray-400">
            Connect a broker account to see your portfolio summary
          </p>
        </div>
      </Card>
    );
  }

  const dayChange = summary.total_unrealized_pl || 0;
  const dayChangePercent = summary.total_unrealized_pl_percent || 0;

  return (
    <Card className="col-span-full">
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-6">
        {/* Total Value */}
        <div className="col-span-2">
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Total Portfolio Value</p>
          <p className="text-3xl font-bold text-gray-900 dark:text-white">
            {formatCurrency(summary.total_portfolio_value)}
          </p>
          <p className={`text-sm font-medium ${getPLColor(dayChange)}`}>
            {formatCurrency(dayChange)} ({formatPercent(dayChangePercent)})
          </p>
        </div>

        {/* Cash */}
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Cash</p>
          <p className="text-xl font-semibold text-gray-900 dark:text-white">
            {formatCurrency(summary.total_cash)}
          </p>
        </div>

        {/* Invested */}
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Invested</p>
          <p className="text-xl font-semibold text-gray-900 dark:text-white">
            {formatCurrency(summary.total_invested)}
          </p>
        </div>

        {/* Buying Power */}
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Buying Power</p>
          <p className="text-xl font-semibold text-gray-900 dark:text-white">
            {formatCurrency(summary.total_buying_power)}
          </p>
        </div>

        {/* Positions */}
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Positions</p>
          <p className="text-xl font-semibold text-gray-900 dark:text-white">
            {summary.total_positions}
          </p>
        </div>
      </div>
    </Card>
  );
}

// =============================================================================
// Broker Card
// =============================================================================

function BrokerCard({ broker, connection, onConnect, onDisconnect, onSync }) {
  const config = BROKER_CONFIG[broker.type] || {};
  const isConnected = connection?.status === 'connected';
  const isPending = connection?.status === 'pending_mfa';

  return (
    <div className={`border rounded-xl p-4 transition-all ${
      isConnected
        ? `border-green-300 dark:border-green-700 ${config.bgLight}`
        : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'
    }`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-3xl">{config.logo}</span>
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">{config.name}</h3>
            {isConnected && (
              <p className="text-xs text-green-600 dark:text-green-400">Connected</p>
            )}
            {isPending && (
              <p className="text-xs text-yellow-600 dark:text-yellow-400">MFA Required</p>
            )}
            {broker.coming_soon && (
              <p className="text-xs text-gray-500">Coming Soon</p>
            )}
          </div>
        </div>

        {!broker.coming_soon && (
          <div>
            {isConnected ? (
              <div className="flex gap-2">
                <button
                  onClick={() => onSync(connection.id)}
                  className="p-2 text-gray-500 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                  title="Sync"
                >
                  🔄
                </button>
                <button
                  onClick={() => onDisconnect(connection.id)}
                  className="p-2 text-gray-500 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                  title="Disconnect"
                >
                  ✕
                </button>
              </div>
            ) : (
              <button
                onClick={() => onConnect(broker)}
                disabled={!broker.available}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  broker.available
                    ? `${config.color} text-white hover:opacity-90`
                    : 'bg-gray-200 text-gray-500 cursor-not-allowed'
                }`}
              >
                Connect
              </button>
            )}
          </div>
        )}
      </div>

      {isConnected && connection && (
        <div className="grid grid-cols-2 gap-3 pt-3 border-t border-gray-200 dark:border-gray-700">
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400">Value</p>
            <p className="font-semibold text-gray-900 dark:text-white">
              {formatCurrency(connection.portfolio_value)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400">Cash</p>
            <p className="font-semibold text-gray-900 dark:text-white">
              {formatCurrency(connection.cash_balance)}
            </p>
          </div>
        </div>
      )}

      {/* Features */}
      <div className="flex gap-2 mt-3 flex-wrap">
        {broker.features?.map((feature) => (
          <span
            key={feature}
            className="px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
          >
            {feature}
          </span>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// Positions Table
// =============================================================================

// Score color helper
const getScoreColor = (score) => {
  if (score === null || score === undefined) return 'text-gray-400 dark:text-gray-500';
  if (score >= 70) return 'text-green-600 dark:text-green-400';
  if (score >= 50) return 'text-yellow-600 dark:text-yellow-400';
  return 'text-red-600 dark:text-red-400';
};

function PositionsTable({ positions, loading, onSelectStock, liveQuotes = {}, positionScores = {} }) {
  const [filter, setFilter] = useState('all');
  const [sortBy, setSortBy] = useState('value');
  const [sortDir, setSortDir] = useState('desc');

  if (loading) {
    return (
      <Card title="Positions">
        <div className="animate-pulse space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 bg-gray-200 dark:bg-gray-700 rounded" />
          ))}
        </div>
      </Card>
    );
  }

  if (!positions || positions.length === 0) {
    return (
      <Card title="Positions">
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">
          No positions found. Connect a broker to see your holdings.
        </div>
      </Card>
    );
  }

  // Filter positions
  const filteredPositions = positions.filter((p) => {
    if (filter === 'all') return true;
    return p.asset_type === filter;
  });

  // Sort positions
  const sortedPositions = [...filteredPositions].sort((a, b) => {
    let aVal, bVal;
    switch (sortBy) {
      case 'value':
        aVal = a.market_value || 0;
        bVal = b.market_value || 0;
        break;
      case 'pl':
        aVal = a.unrealized_pl || 0;
        bVal = b.unrealized_pl || 0;
        break;
      case 'plPercent':
        aVal = a.unrealized_pl_percent || 0;
        bVal = b.unrealized_pl_percent || 0;
        break;
      case 'score':
        aVal = positionScores[a.symbol]?.score || 0;
        bVal = positionScores[b.symbol]?.score || 0;
        break;
      default:
        aVal = a.symbol;
        bVal = b.symbol;
    }
    if (sortDir === 'desc') return bVal - aVal;
    return aVal - bVal;
  });

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortDir('desc');
    }
  };

  return (
    <Card
      title={
        <div className="flex items-center justify-between w-full">
          <span>Positions ({filteredPositions.length})</span>
          <div className="flex gap-2">
            {['all', 'stock', 'option', 'crypto'].map((type) => (
              <button
                key={type}
                onClick={() => setFilter(type)}
                className={`px-3 py-1 text-xs rounded-full transition-colors ${
                  filter === type
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>
        </div>
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left text-xs text-gray-500 dark:text-gray-400 border-b dark:border-gray-700">
              <th className="pb-3 pr-4">Symbol</th>
              <th
                className="pb-3 pr-4 text-right cursor-pointer hover:text-blue-500"
                onClick={() => handleSort('score')}
              >
                Score {sortBy === 'score' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
              <th className="pb-3 pr-4 text-right">Qty</th>
              <th className="pb-3 pr-4 text-right">Avg Cost</th>
              <th className="pb-3 pr-4 text-right">Price</th>
              <th className="pb-3 pr-4 text-right">% Chg</th>
              <th
                className="pb-3 pr-4 text-right cursor-pointer hover:text-blue-500"
                onClick={() => handleSort('value')}
              >
                Value {sortBy === 'value' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
              <th
                className="pb-3 pr-4 text-right cursor-pointer hover:text-blue-500"
                onClick={() => handleSort('pl')}
              >
                P/L {sortBy === 'pl' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
              <th
                className="pb-3 text-right cursor-pointer hover:text-blue-500"
                onClick={() => handleSort('plPercent')}
              >
                P/L % {sortBy === 'plPercent' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedPositions.map((position, idx) => (
              <tr
                key={`${position.symbol}-${idx}`}
                className="border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors"
                onClick={() => onSelectStock && onSelectStock(position.symbol)}
              >
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400">
                      {position.symbol}
                    </span>
                    {position.asset_type === 'option' && (
                      <span className="px-1.5 py-0.5 text-xs rounded bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400">
                        {position.option_type?.toUpperCase()}
                      </span>
                    )}
                    {position.asset_type === 'crypto' && (
                      <span className="px-1.5 py-0.5 text-xs rounded bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400">
                        CRYPTO
                      </span>
                    )}
                  </div>
                  {position.name && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-[200px]">
                      {position.name}
                    </p>
                  )}
                </td>
                <td className={`py-3 pr-4 text-right font-mono font-bold ${getScoreColor(positionScores[position.symbol]?.score)}`}>
                  {positionScores[position.symbol]?.score != null
                    ? positionScores[position.symbol].score.toFixed(1)
                    : '--'}
                </td>
                <td className="py-3 pr-4 text-right font-mono text-gray-900 dark:text-white">
                  {position.quantity}
                </td>
                <td className="py-3 pr-4 text-right font-mono text-gray-600 dark:text-gray-400">
                  {formatCurrency(position.average_cost)}
                </td>
                <td className={`py-3 pr-4 text-right font-mono font-medium ${getChangeColor(liveQuotes[position.symbol]?.change_percent)}`}>
                  {formatCurrency(position.current_price)}
                </td>
                <td className={`py-3 pr-4 text-right font-mono font-medium ${getChangeColor(liveQuotes[position.symbol]?.change_percent)}`}>
                  {formatChangePercent(liveQuotes[position.symbol]?.change_percent)}
                </td>
                <td className="py-3 pr-4 text-right font-mono font-medium text-gray-900 dark:text-white">
                  {formatCurrency(position.market_value)}
                </td>
                <td className={`py-3 pr-4 text-right font-mono font-medium ${getPLColor(position.unrealized_pl)}`}>
                  {formatCurrency(position.unrealized_pl)}
                </td>
                <td className={`py-3 text-right font-mono font-medium ${getPLColor(position.unrealized_pl_percent)}`}>
                  {formatPercent(position.unrealized_pl_percent)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// =============================================================================
// Paper Trading Tab Component
// =============================================================================

function PaperTradingTab({ positions, orders, loading, account, onSelectStock, onRefresh, onCancelOrder }) {
  if (loading) {
    return (
      <Card title="Paper Trading Positions">
        <div className="animate-pulse space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-12 bg-gray-200 dark:bg-gray-700 rounded" />
          ))}
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Paper Account Summary */}
      {account && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <span className="text-3xl">📝</span>
              <div>
                <h3 className="font-semibold text-gray-900 dark:text-white">
                  Paper Trading Account
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Simulated trading - no real money
                </p>
              </div>
            </div>
            <button
              onClick={onRefresh}
              className="px-3 py-1.5 text-sm bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 rounded-lg hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
            >
              Refresh
            </button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Equity</p>
              <p className="text-xl font-semibold text-gray-900 dark:text-white">
                {formatCurrency(account.equity)}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Buying Power</p>
              <p className="text-xl font-semibold text-blue-600 dark:text-blue-400">
                {formatCurrency(account.buying_power)}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Cash</p>
              <p className="text-xl font-semibold text-gray-900 dark:text-white">
                {formatCurrency(account.cash)}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">Portfolio Value</p>
              <p className="text-xl font-semibold text-gray-900 dark:text-white">
                {formatCurrency(account.portfolio_value)}
              </p>
            </div>
          </div>

          {/* Day Trade Info */}
          {account.daytrade_count !== undefined && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-4 text-sm">
                <span className="text-gray-500 dark:text-gray-400">
                  Day Trades: <span className="text-gray-900 dark:text-white font-medium">{account.daytrade_count}/3</span>
                </span>
                {account.pattern_day_trader && (
                  <span className="px-2 py-0.5 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 rounded text-xs">
                    PDT
                  </span>
                )}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Paper Positions Table */}
      <Card title={`Paper Positions (${positions.length})`}>
        {positions.length === 0 ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <span className="text-4xl mb-3 block">📭</span>
            <p className="font-medium">No paper trading positions</p>
            <p className="text-sm mt-1">
              Use signals to place paper trades and practice your strategy
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-xs text-gray-500 dark:text-gray-400 border-b dark:border-gray-700">
                  <th className="pb-3 pr-4">Symbol</th>
                  <th className="pb-3 pr-4 text-right">Qty</th>
                  <th className="pb-3 pr-4 text-right">Avg Cost</th>
                  <th className="pb-3 pr-4 text-right">Price</th>
                  <th className="pb-3 pr-4 text-right">Value</th>
                  <th className="pb-3 pr-4 text-right">P/L</th>
                  <th className="pb-3 text-right">P/L %</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position, idx) => (
                  <tr
                    key={`${position.symbol}-${idx}`}
                    className="border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors"
                    onClick={() => onSelectStock?.(position.symbol)}
                  >
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-gray-900 dark:text-white">
                          {position.symbol}
                        </span>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          position.side === 'long'
                            ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                            : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                        }`}>
                          {position.side?.toUpperCase() || 'LONG'}
                        </span>
                      </div>
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-gray-900 dark:text-white">
                      {position.qty}
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-gray-600 dark:text-gray-400">
                      {formatCurrency(position.avg_entry_price)}
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-gray-900 dark:text-white">
                      {formatCurrency(position.current_price)}
                    </td>
                    <td className="py-3 pr-4 text-right font-mono font-medium text-gray-900 dark:text-white">
                      {formatCurrency(position.market_value)}
                    </td>
                    <td className={`py-3 pr-4 text-right font-mono font-medium ${getPLColor(position.unrealized_pl)}`}>
                      {formatCurrency(position.unrealized_pl)}
                    </td>
                    <td className={`py-3 text-right font-mono font-medium ${getPLColor(position.unrealized_plpc * 100)}`}>
                      {formatPercent(position.unrealized_plpc * 100)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Pending Orders */}
      {orders && orders.length > 0 && (
        <Card title={`Pending Orders (${orders.length})`}>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-xs text-gray-500 dark:text-gray-400 border-b dark:border-gray-700">
                  <th className="pb-3 pr-4">Symbol</th>
                  <th className="pb-3 pr-4">Side</th>
                  <th className="pb-3 pr-4">Type</th>
                  <th className="pb-3 pr-4 text-right">Qty</th>
                  <th className="pb-3 pr-4 text-right">Limit Price</th>
                  <th className="pb-3 pr-4">Status</th>
                  <th className="pb-3 pr-4">Submitted</th>
                  <th className="pb-3"></th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => (
                  <tr
                    key={order.order_id}
                    className="border-b dark:border-gray-700 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-700/50"
                  >
                    <td className="py-3 pr-4">
                      <span className="font-semibold text-gray-900 dark:text-white">
                        {order.symbol}
                      </span>
                    </td>
                    <td className="py-3 pr-4">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                        order.side === 'buy'
                          ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                          : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                      }`}>
                        {order.side?.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-sm text-gray-600 dark:text-gray-400">
                      {order.type?.toUpperCase()}
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-gray-900 dark:text-white">
                      {order.qty}
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-gray-600 dark:text-gray-400">
                      {order.limit_price ? formatCurrency(order.limit_price) : '--'}
                    </td>
                    <td className="py-3 pr-4">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        order.status === 'filled' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' :
                        order.status === 'canceled' || order.status === 'expired' ? 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400' :
                        'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400'
                      }`}>
                        {order.status?.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-sm text-gray-500 dark:text-gray-400">
                      {order.submitted_at ? new Date(order.submitted_at).toLocaleString() : '--'}
                    </td>
                    <td className="py-3">
                      {order.status !== 'filled' && order.status !== 'canceled' && order.status !== 'expired' && (
                        <button
                          onClick={() => onCancelOrder?.(order.order_id)}
                          className="text-xs text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                        >
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

// =============================================================================
// Main Portfolio Page
// =============================================================================

export default function Portfolio() {
  const {
    brokersStatus,
    connections,
    summary,
    positions,
    summaryLoading,
    positionsLoading,
    fetchBrokersStatus,
    fetchConnections,
    fetchSummary,
    fetchPositions,
    connectBroker,
    disconnectBroker,
    syncConnection,
    startAutoRefresh,
    stopAutoRefresh,
  } = usePortfolioStore();

  const [connectModal, setConnectModal] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedStock, setSelectedStock] = useState(null);
  const [stockDetailLoading, setStockDetailLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Paper trading state
  const [paperPositions, setPaperPositions] = useState([]);
  const [paperOrders, setPaperOrders] = useState([]);
  const [paperPositionsLoading, setPaperPositionsLoading] = useState(false);
  const [paperAccount, setPaperAccount] = useState(null);

  // Detect expired broker sessions
  const expiredConnections = useMemo(
    () => connections.filter(c => c.status === 'session_expired'),
    [connections]
  );

  // Handle reconnect — disconnect the expired connection so user can re-login
  const handleReconnect = useCallback(async (conn) => {
    try {
      await disconnectBroker(conn.id);
      // Open the connect modal for this broker type
      const broker = brokersStatus.find(b => b.type === conn.broker_type);
      if (broker) {
        setConnectModal(broker);
      }
    } catch (err) {
      console.error('Error disconnecting expired broker:', err);
    }
  }, [disconnectBroker, brokersStatus]);

  // Real-time price stream
  const {
    isConnected: priceStreamConnected,
    prices: streamPrices,
    connect: connectPriceStream,
    subscribe: subscribeSymbols,
    disconnect: disconnectPriceStream,
  } = usePriceStreamStore();
  // Collect unique symbols for batch quotes (all types)
  const positionSymbols = useMemo(
    () => [...new Set(positions.map((p) => p.symbol))],
    [positions]
  );

  // Stock/option symbols only — crypto doesn't have fundamentals/technicals/options data
  const scorableSymbols = useMemo(
    () => [...new Set(positions.filter((p) => p.asset_type !== 'crypto').map((p) => p.symbol))],
    [positions]
  );

  // Fetch live quotes for daily change % (initial load)
  const [liveQuotes, setLiveQuotes] = useState({});

  useEffect(() => {
    if (positionSymbols.length === 0) return;
    stocksAPI.getBatchQuotes(positionSymbols)
      .then(data => setLiveQuotes(data.quotes || {}))
      .catch(() => setLiveQuotes({}));
  }, [positionSymbols]);

  // Connect to real-time price stream on mount
  useEffect(() => {
    connectPriceStream();
    return () => disconnectPriceStream();
  }, [connectPriceStream, disconnectPriceStream]);

  // Subscribe to position symbols for real-time updates
  useEffect(() => {
    if (positionSymbols.length > 0) {
      subscribeSymbols(positionSymbols);
    }
  }, [positionSymbols, subscribeSymbols]);

  // Merge initial quotes with real-time stream prices
  const mergedQuotes = useMemo(() => {
    const merged = { ...liveQuotes };
    // Overlay real-time prices from WebSocket
    for (const [symbol, data] of Object.entries(streamPrices)) {
      if (data.price) {
        merged[symbol] = {
          ...merged[symbol],
          price: data.price,
          lastUpdate: data.timestamp,
          isRealTime: true,
        };
      }
    }
    return merged;
  }, [liveQuotes, streamPrices]);

  // Fetch composite scores for non-crypto positions only
  const [positionScores, setPositionScores] = useState({});

  useEffect(() => {
    if (scorableSymbols.length === 0) return;
    screenerAPI.getBatchScores(scorableSymbols)
      .then(data => setPositionScores(data.scores || {}))
      .catch(() => setPositionScores({}));
  }, [scorableSymbols]);

  // Manual refresh function - syncs all connected brokers then fetches fresh data
  const handleManualRefresh = async () => {
    // Prevent double-clicks while already refreshing
    if (isRefreshing) return;

    setIsRefreshing(true);
    try {
      // First fetch fresh connections list to ensure we have the latest
      const freshConnections = await fetchConnections();

      // Get connected brokers from fresh data or fallback to state
      const brokerList = freshConnections || connections;
      const connectedBrokers = brokerList.filter(c => c.status === 'connected');

      console.log(`🔄 Syncing ${connectedBrokers.length} connected broker(s)...`);

      // Sync each connected broker to get fresh data from Robinhood
      // Note: syncConnection internally calls fetchConnections + fetchSummary + fetchPositions
      let sessionExpired = false;
      for (const conn of connectedBrokers) {
        try {
          console.log(`📡 Syncing ${conn.broker_type}...`);
          await syncConnection(conn.id);
          console.log(`✅ ${conn.broker_type} synced successfully`);
        } catch (err) {
          const status = err?.response?.status;
          if (status === 401) {
            console.warn(`⚠️ ${conn.broker_type} session expired — re-login required`);
            sessionExpired = true;
          } else {
            console.error(`❌ Failed to sync ${conn.broker_type}:`, err);
          }
        }
      }

      // Refresh connections to pick up any status changes (e.g. session_expired)
      if (sessionExpired) {
        await fetchConnections();
      }

      // If no brokers were synced, fetch data directly
      if (connectedBrokers.length === 0) {
        await Promise.all([
          fetchSummary(),
          fetchPositions(),
        ]);
      }

      console.log('✅ Portfolio refresh complete');
    } catch (err) {
      console.error('❌ Portfolio refresh failed:', err);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Fetch paper trading positions and orders from Alpaca
  const fetchPaperPositions = async () => {
    setPaperPositionsLoading(true);
    try {
      const [positionsData, accountData, ordersData] = await Promise.all([
        tradingAPI.getAllPositions(),
        tradingAPI.getAccount(),
        tradingAPI.listOrders({ status: 'open' }),
      ]);
      setPaperPositions(positionsData.positions || []);
      setPaperAccount(accountData);
      setPaperOrders(ordersData.orders || []);
    } catch (error) {
      console.error('Error fetching paper positions:', error);
      setPaperPositions([]);
      setPaperOrders([]);
    } finally {
      setPaperPositionsLoading(false);
    }
  };

  // Cancel a paper order
  const handleCancelOrder = async (orderId) => {
    try {
      await tradingAPI.cancelOrder(orderId);
      // Refresh to show updated orders
      fetchPaperPositions();
    } catch (error) {
      console.error('Error canceling order:', error);
    }
  };

  // Fetch paper positions when tab becomes active
  useEffect(() => {
    if (activeTab === 'paper-trading') {
      fetchPaperPositions();
    }
  }, [activeTab]);

  // Subscribe to paper trading symbols for real-time updates
  useEffect(() => {
    const paperSymbols = paperPositions.map((p) => p.symbol).filter(Boolean);
    if (paperSymbols.length > 0) {
      subscribeSymbols(paperSymbols);
    }
  }, [paperPositions, subscribeSymbols]);

  // Handle stock selection - fetch full details
  const handleSelectStock = async (symbol) => {
    if (!symbol) return;

    const position = positions.find(p => p.symbol === symbol);
    const isCrypto = position?.asset_type === 'crypto';

    // Crypto positions: show position data only, no stock info / scoring
    if (isCrypto) {
      setSelectedStock({
        symbol,
        name: position?.name || symbol,
        current_price: position?.current_price,
        asset_type: 'crypto',
        position: position ? {
          quantity: position.quantity,
          average_cost: position.average_cost,
          market_value: position.market_value,
          unrealized_pl: position.unrealized_pl,
          unrealized_pl_percent: position.unrealized_pl_percent,
        } : null,
      });
      return;
    }

    setStockDetailLoading(true);
    try {
      // Fetch stock info and scores in parallel
      const [stockInfo, scoresData] = await Promise.all([
        stocksAPI.getStockInfo(symbol).catch(() => null),
        screenerAPI.getBatchScores([symbol]).catch(() => ({ scores: {} })),
      ]);

      const scoreResult = scoresData.scores?.[symbol] || {};

      setSelectedStock({
        symbol,
        name: stockInfo?.name || position?.name || symbol,
        current_price: stockInfo?.currentPrice || position?.current_price,
        sector: stockInfo?.sector,
        market_cap: stockInfo?.marketCap,
        // Include position data for portfolio context
        position: position ? {
          quantity: position.quantity,
          average_cost: position.average_cost,
          market_value: position.market_value,
          unrealized_pl: position.unrealized_pl,
          unrealized_pl_percent: position.unrealized_pl_percent,
        } : null,
        // Other data from stock info
        ...stockInfo,
        // Scoring data from batch scores
        score: scoreResult.score,
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
      // Still show modal with basic position data
      const position = positions.find(p => p.symbol === symbol);
      setSelectedStock({
        symbol,
        name: position?.name || symbol,
        current_price: position?.current_price,
        position: position ? {
          quantity: position.quantity,
          average_cost: position.average_cost,
          market_value: position.market_value,
          unrealized_pl: position.unrealized_pl,
          unrealized_pl_percent: position.unrealized_pl_percent,
        } : null,
      });
    } finally {
      setStockDetailLoading(false);
    }
  };

  // Initial data fetch
  useEffect(() => {
    fetchBrokersStatus();
    fetchConnections();
    fetchSummary();
    fetchPositions();

    // Start auto-refresh
    startAutoRefresh(60000);

    return () => {
      stopAutoRefresh();
    };
  }, []);

  // Find connection for each broker
  const getConnectionForBroker = (brokerType) => {
    return connections.find((c) => c.broker_type === brokerType);
  };

  const handleConnect = async (brokerType, username, password, mfaCode, accountName) => {
    return await connectBroker(brokerType, username, password, mfaCode, accountName);
  };

  const handleDisconnect = async (connectionId) => {
    if (window.confirm('Are you sure you want to disconnect this broker?')) {
      await disconnectBroker(connectionId);
    }
  };

  const handleSync = async (connectionId) => {
    try {
      await syncConnection(connectionId);
    } catch (error) {
      console.error('Sync error:', error);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Portfolio</h1>
            <p className="text-gray-600 dark:text-gray-400">
              Manage your broker accounts and track your investments
            </p>
          </div>

          <div className="flex items-center gap-4">
            {/* Real-time price stream indicator */}
            <div className="flex items-center gap-1.5" title={priceStreamConnected ? 'Real-time prices connected' : 'Real-time prices disconnected'}>
              <span className={`w-2 h-2 rounded-full ${priceStreamConnected ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {priceStreamConnected ? 'Live' : 'Offline'}
              </span>
            </div>
            {summary?.last_sync && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Last updated: {new Date(summary.last_sync).toLocaleString()}
              </p>
            )}
            <button
              onClick={handleManualRefresh}
              disabled={isRefreshing}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              {isRefreshing ? (
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              )}
              {isRefreshing ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
        </div>

        {/* Session Expired Banner */}
        {expiredConnections.length > 0 && (
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700 rounded-lg p-4 mb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-2xl">⚠️</span>
                <div>
                  <h3 className="font-semibold text-amber-800 dark:text-amber-300">
                    Broker Session Expired
                  </h3>
                  <p className="text-sm text-amber-700 dark:text-amber-400">
                    {expiredConnections.map(c => c.account_name || c.broker_type).join(', ')} — session has expired. Please re-connect to refresh your portfolio.
                  </p>
                </div>
              </div>
              <button
                onClick={() => handleReconnect(expiredConnections[0])}
                className="px-4 py-2 bg-amber-600 text-white text-sm font-medium rounded-lg hover:bg-amber-700 transition-colors whitespace-nowrap"
              >
                Re-connect
              </button>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700 pb-2">
          {[
            { id: 'overview', label: 'Overview' },
            { id: 'positions', label: 'Positions' },
            { id: 'paper-trading', label: 'Paper Trading' },
            { id: 'brokers', label: 'Brokers' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                activeTab === tab.id
                  ? 'bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-400 border-b-2 border-blue-500'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Portfolio Summary */}
            <PortfolioSummaryCard summary={summary} />

            {/* Quick Stats Grid */}
            {summary?.connected && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {/* Top Gainers */}
                <Card>
                  <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Top Gainer</h4>
                  {positions.length > 0 ? (() => {
                    const topGainer = [...positions].sort((a, b) =>
                      (b.unrealized_pl_percent || 0) - (a.unrealized_pl_percent || 0)
                    )[0];
                    return topGainer ? (
                      <div>
                        <p className="font-semibold text-gray-900 dark:text-white">{topGainer.symbol}</p>
                        <p className="text-green-500 font-medium">{formatPercent(topGainer.unrealized_pl_percent)}</p>
                      </div>
                    ) : <p className="text-gray-500">--</p>;
                  })() : <p className="text-gray-500">--</p>}
                </Card>

                {/* Top Loser */}
                <Card>
                  <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Top Loser</h4>
                  {positions.length > 0 ? (() => {
                    const topLoser = [...positions].sort((a, b) =>
                      (a.unrealized_pl_percent || 0) - (b.unrealized_pl_percent || 0)
                    )[0];
                    return topLoser ? (
                      <div>
                        <p className="font-semibold text-gray-900 dark:text-white">{topLoser.symbol}</p>
                        <p className="text-red-500 font-medium">{formatPercent(topLoser.unrealized_pl_percent)}</p>
                      </div>
                    ) : <p className="text-gray-500">--</p>;
                  })() : <p className="text-gray-500">--</p>}
                </Card>

                {/* Largest Position */}
                <Card>
                  <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Largest Position</h4>
                  {positions.length > 0 ? (() => {
                    const largest = [...positions].sort((a, b) =>
                      (b.market_value || 0) - (a.market_value || 0)
                    )[0];
                    return largest ? (
                      <div>
                        <p className="font-semibold text-gray-900 dark:text-white">{largest.symbol}</p>
                        <p className="text-gray-600 dark:text-gray-400">{formatCurrency(largest.market_value)}</p>
                      </div>
                    ) : <p className="text-gray-500">--</p>;
                  })() : <p className="text-gray-500">--</p>}
                </Card>

                {/* Connected Brokers */}
                <Card>
                  <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Connected Brokers</h4>
                  <p className="text-2xl font-bold text-gray-900 dark:text-white">
                    {connections.filter(c => c.status === 'connected').length}
                  </p>
                  <p className="text-gray-600 dark:text-gray-400 text-sm">of {brokersStatus.length} available</p>
                </Card>
              </div>
            )}

            {/* Positions Preview */}
            <PositionsTable positions={positions} loading={positionsLoading} onSelectStock={handleSelectStock} liveQuotes={mergedQuotes} positionScores={positionScores} />
          </div>
        )}

        {/* Positions Tab */}
        {activeTab === 'positions' && (
          <PositionsTable positions={positions} loading={positionsLoading} onSelectStock={handleSelectStock} liveQuotes={mergedQuotes} positionScores={positionScores} />
        )}

        {/* Paper Trading Tab */}
        {activeTab === 'paper-trading' && (
          <PaperTradingTab
            positions={paperPositions}
            orders={paperOrders}
            loading={paperPositionsLoading}
            account={paperAccount}
            onSelectStock={handleSelectStock}
            onRefresh={fetchPaperPositions}
            onCancelOrder={handleCancelOrder}
          />
        )}

        {/* Brokers Tab */}
        {activeTab === 'brokers' && (
          <div className="space-y-4">
            <Card title="Connected Brokers">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {brokersStatus.map((broker) => (
                  <BrokerCard
                    key={broker.type}
                    broker={broker}
                    connection={getConnectionForBroker(broker.type)}
                    onConnect={(b) => setConnectModal(b)}
                    onDisconnect={handleDisconnect}
                    onSync={handleSync}
                  />
                ))}
              </div>
            </Card>
          </div>
        )}

        {/* Connect Modal */}
        {connectModal && (
          <ConnectBrokerModal
            broker={connectModal}
            onClose={() => setConnectModal(null)}
            onConnect={handleConnect}
          />
        )}

        {/* Stock Detail Modal */}
        {selectedStock && (
          <StockDetail
            stock={selectedStock}
            onClose={() => setSelectedStock(null)}
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
