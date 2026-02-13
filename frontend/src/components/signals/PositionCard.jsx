/**
 * Position Card Component
 * Displays open position with P/L and sell buttons
 */
import { useState } from 'react';
import tradingAPI from '../../api/trading';

export default function PositionCard({ position, onClose }) {
  const [showLimitSell, setShowLimitSell] = useState(false);
  const [limitPrice, setLimitPrice] = useState('');
  const [sellQty, setSellQty] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  if (!position) return null;

  const isProfit = position.unrealized_pl >= 0;
  const plColor = isProfit ? 'text-green-600' : 'text-red-600';
  const plBgColor = isProfit ? 'bg-green-50' : 'bg-red-50';

  const handleMarketSell = async () => {
    if (!confirm(`Sell all ${position.qty} shares of ${position.symbol} at market price?`)) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await tradingAPI.closePosition(position.symbol);
      onClose?.();
    } catch (err) {
      setError(err.message || 'Failed to close position');
    } finally {
      setLoading(false);
    }
  };

  const handleLimitSell = async (e) => {
    e.preventDefault();

    if (!limitPrice || !sellQty) {
      setError('Please enter limit price and quantity');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await tradingAPI.placeOrder({
        symbol: position.symbol,
        qty: parseFloat(sellQty),
        side: 'sell',
        order_type: 'limit',
        limit_price: parseFloat(limitPrice),
      });
      setShowLimitSell(false);
      setSellQty('');
      setLimitPrice('');
      onClose?.();
    } catch (err) {
      setError(err.message || 'Failed to place limit order');
    } finally {
      setLoading(false);
    }
  };

  const handlePartialSell = async (percentage) => {
    if (!confirm(`Sell ${percentage}% of your ${position.symbol} position?`)) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await tradingAPI.closePosition(position.symbol, { percentage });
      onClose?.();
    } catch (err) {
      setError(err.message || 'Failed to close position');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`rounded-xl p-4 ${plBgColor} border ${isProfit ? 'border-green-200' : 'border-red-200'}`}>
      <div className="flex justify-between items-start mb-4">
        <div>
          <h4 className="font-bold text-gray-900">Open Position</h4>
          <p className="text-sm text-gray-600">
            {position.qty} shares @ ${position.avg_entry_price?.toFixed(2)}
          </p>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-bold ${plColor}`}>
            {isProfit ? '+' : ''}{position.unrealized_pl?.toFixed(2)}
          </div>
          <div className={`text-sm ${plColor}`}>
            ({isProfit ? '+' : ''}{position.unrealized_plpc?.toFixed(2)}%)
          </div>
        </div>
      </div>

      {/* Position Details */}
      <div className="grid grid-cols-3 gap-4 mb-4 text-sm">
        <div>
          <div className="text-gray-500">Avg Entry</div>
          <div className="font-semibold">${position.avg_entry_price?.toFixed(2)}</div>
        </div>
        <div>
          <div className="text-gray-500">Current</div>
          <div className="font-semibold">${position.current_price?.toFixed(2)}</div>
        </div>
        <div>
          <div className="text-gray-500">Market Value</div>
          <div className="font-semibold">${position.market_value?.toFixed(2)}</div>
        </div>
      </div>

      {/* Intraday P/L */}
      {position.unrealized_intraday_pl !== undefined && (
        <div className="text-sm text-gray-600 mb-4">
          Today: <span className={position.unrealized_intraday_pl >= 0 ? 'text-green-600' : 'text-red-600'}>
            {position.unrealized_intraday_pl >= 0 ? '+' : ''}${position.unrealized_intraday_pl?.toFixed(2)}
            ({position.unrealized_intraday_plpc?.toFixed(2)}%)
          </span>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="bg-red-100 border border-red-300 rounded-lg p-2 mb-4">
          <p className="text-red-700 text-sm">{error}</p>
        </div>
      )}

      {/* Sell Actions */}
      {!showLimitSell ? (
        <div className="space-y-2">
          <div className="flex gap-2">
            <button
              onClick={handleMarketSell}
              disabled={loading}
              className="flex-1 bg-red-600 text-white py-2 rounded-lg font-medium hover:bg-red-700 disabled:opacity-50"
            >
              {loading ? 'Selling...' : 'Market Sell All'}
            </button>
            <button
              onClick={() => setShowLimitSell(true)}
              disabled={loading}
              className="flex-1 bg-gray-600 text-white py-2 rounded-lg font-medium hover:bg-gray-700 disabled:opacity-50"
            >
              Limit Sell
            </button>
          </div>

          {/* Quick partial sell buttons */}
          <div className="flex gap-2">
            <button
              onClick={() => handlePartialSell(25)}
              disabled={loading}
              className="flex-1 bg-gray-200 text-gray-700 py-1 rounded text-sm hover:bg-gray-300 disabled:opacity-50"
            >
              Sell 25%
            </button>
            <button
              onClick={() => handlePartialSell(50)}
              disabled={loading}
              className="flex-1 bg-gray-200 text-gray-700 py-1 rounded text-sm hover:bg-gray-300 disabled:opacity-50"
            >
              Sell 50%
            </button>
            <button
              onClick={() => handlePartialSell(75)}
              disabled={loading}
              className="flex-1 bg-gray-200 text-gray-700 py-1 rounded text-sm hover:bg-gray-300 disabled:opacity-50"
            >
              Sell 75%
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleLimitSell} className="space-y-3">
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="block text-xs text-gray-500 mb-1">Quantity</label>
              <input
                type="number"
                value={sellQty}
                onChange={(e) => setSellQty(e.target.value)}
                max={position.qty}
                min="1"
                step="1"
                required
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                placeholder={`Max: ${position.qty}`}
              />
            </div>
            <div className="flex-1">
              <label className="block text-xs text-gray-500 mb-1">Limit Price</label>
              <input
                type="number"
                value={limitPrice}
                onChange={(e) => setLimitPrice(e.target.value)}
                min="0.01"
                step="0.01"
                required
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                placeholder="Price"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-orange-600 text-white py-2 rounded-lg font-medium hover:bg-orange-700 disabled:opacity-50"
            >
              {loading ? 'Placing...' : 'Place Limit Sell'}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowLimitSell(false);
                setError(null);
              }}
              className="px-4 bg-gray-200 text-gray-700 py-2 rounded-lg hover:bg-gray-300"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
