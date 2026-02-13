/**
 * Trade Execution Modal
 * Place market/limit orders via Alpaca
 */
import { useState, useEffect } from 'react';
import tradingAPI from '../../api/trading';
import useSignalsStore from '../../stores/signalsStore';

export default function TradeExecutionModal({ signal, onClose, onSuccess }) {
  const [quantity, setQuantity] = useState('');
  const [orderType, setOrderType] = useState('market');
  const [limitPrice, setLimitPrice] = useState(signal?.entry_price?.toFixed(2) || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [orderResult, setOrderResult] = useState(null);
  const [account, setAccount] = useState(null);

  const { tradingMode, fetchTradingMode } = useSignalsStore();

  useEffect(() => {
    fetchAccount();
    fetchTradingMode();
  }, []);

  const fetchAccount = async () => {
    try {
      const data = await tradingAPI.getAccount();
      setAccount(data);
    } catch (err) {
      console.error('Failed to fetch account:', err);
    }
  };

  const side = signal?.direction === 'buy' ? 'buy' : 'sell';
  const currentPrice = signal?.entry_price || 0;
  const estimatedCost = quantity ? parseFloat(quantity) * currentPrice : 0;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const orderData = {
        symbol: signal.symbol,
        qty: parseFloat(quantity),
        side: side,
        order_type: orderType,
      };

      if (orderType === 'limit') {
        orderData.limit_price = parseFloat(limitPrice);
      }

      const result = await tradingAPI.placeOrder(orderData);

      if (result.error) {
        setError(result.error);
      } else {
        setOrderResult(result);
      }
    } catch (err) {
      setError(err.message || 'Failed to place order');
    } finally {
      setLoading(false);
    }
  };

  // Order success view
  if (orderResult) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60] p-4">
        <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
          <div className="text-center">
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h3 className="text-xl font-bold text-gray-900 mb-2">Order Submitted!</h3>
            <p className="text-gray-600 mb-4">
              Your {side.toUpperCase()} order for {signal.symbol} has been submitted.
            </p>

            <div className="bg-gray-50 rounded-lg p-4 text-left mb-4">
              <div className="flex justify-between mb-2">
                <span className="text-gray-500">Order ID</span>
                <span className="font-mono text-sm">{orderResult.order_id?.slice(0, 12)}...</span>
              </div>
              <div className="flex justify-between mb-2">
                <span className="text-gray-500">Symbol</span>
                <span className="font-semibold">{orderResult.symbol}</span>
              </div>
              <div className="flex justify-between mb-2">
                <span className="text-gray-500">Quantity</span>
                <span className="font-semibold">{orderResult.qty} shares</span>
              </div>
              <div className="flex justify-between mb-2">
                <span className="text-gray-500">Type</span>
                <span className="font-semibold capitalize">{orderResult.type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Status</span>
                <span className={`font-semibold ${
                  orderResult.status === 'filled' ? 'text-green-600' :
                  orderResult.status === 'pending_new' || orderResult.status === 'accepted' ? 'text-yellow-600' :
                  'text-gray-600'
                }`}>
                  {orderResult.status?.replace(/_/g, ' ')}
                </span>
              </div>
              {orderResult.filled_avg_price && (
                <div className="flex justify-between mt-2 pt-2 border-t">
                  <span className="text-gray-500">Fill Price</span>
                  <span className="font-semibold text-green-600">
                    ${orderResult.filled_avg_price.toFixed(2)}
                  </span>
                </div>
              )}
            </div>

            {tradingMode?.paper_mode !== false && (
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-4">
                <p className="text-yellow-800 text-sm">
                  <span className="font-semibold">Paper Trading Mode</span> - This is a simulated trade.
                </p>
              </div>
            )}

            <button
              onClick={() => {
                onSuccess?.();
                onClose();
              }}
              className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60] p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full">
        {/* Header */}
        <div className="border-b border-gray-200 px-6 py-4 flex justify-between items-center">
          <div>
            <h3 className="text-lg font-bold text-gray-900">Execute Trade</h3>
            <p className="text-gray-500 text-sm">{signal.symbol}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Trading Mode Warning */}
          {tradingMode?.paper_mode === false && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex items-center gap-2 text-red-800">
                <span className="text-xl">⚠️</span>
                <span className="font-bold">LIVE TRADING MODE</span>
              </div>
              <p className="text-red-700 text-sm mt-1">
                This will place a real order with real money.
              </p>
            </div>
          )}

          {tradingMode?.paper_mode !== false && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
              <p className="text-yellow-800 text-sm">
                <span className="font-semibold">Paper Trading</span> - Simulated order, no real money.
              </p>
            </div>
          )}

          {/* Trade Summary */}
          <div className="bg-gray-50 rounded-lg p-4">
            <div className="flex justify-between items-center mb-3">
              <span className="text-gray-600">Direction</span>
              <span className={`px-3 py-1 rounded-full text-sm font-bold ${
                side === 'buy' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
              }`}>
                {side.toUpperCase()}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-600">Current Price</span>
              <span className="font-semibold">${currentPrice.toFixed(2)}</span>
            </div>
          </div>

          {/* Quantity Input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Quantity (shares)
            </label>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              min="1"
              step="1"
              required
              className="w-full border border-gray-300 rounded-lg px-4 py-3 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="Enter number of shares"
            />
            {account?.buying_power && (
              <p className="text-xs text-gray-500 mt-1">
                Buying power: ${parseFloat(account.buying_power).toLocaleString()}
              </p>
            )}
          </div>

          {/* Order Type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Order Type
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setOrderType('market')}
                className={`flex-1 py-2 rounded-lg font-medium transition-colors ${
                  orderType === 'market'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                Market
              </button>
              <button
                type="button"
                onClick={() => setOrderType('limit')}
                className={`flex-1 py-2 rounded-lg font-medium transition-colors ${
                  orderType === 'limit'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                Limit
              </button>
            </div>
          </div>

          {/* Limit Price (if limit order) */}
          {orderType === 'limit' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Limit Price
              </label>
              <input
                type="number"
                value={limitPrice}
                onChange={(e) => setLimitPrice(e.target.value)}
                min="0.01"
                step="0.01"
                required
                className="w-full border border-gray-300 rounded-lg px-4 py-3 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Enter limit price"
              />
            </div>
          )}

          {/* Estimated Cost */}
          {quantity && (
            <div className="bg-blue-50 rounded-lg p-4">
              <div className="flex justify-between items-center">
                <span className="text-gray-600">Estimated {side === 'buy' ? 'Cost' : 'Proceeds'}</span>
                <span className="text-xl font-bold text-blue-600">
                  ${estimatedCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </div>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-red-700 text-sm">{error}</p>
            </div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading || !quantity}
            className={`w-full py-3 rounded-lg font-medium transition-colors ${
              loading || !quantity
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : side === 'buy'
                  ? 'bg-green-600 text-white hover:bg-green-700'
                  : 'bg-red-600 text-white hover:bg-red-700'
            }`}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Placing Order...
              </span>
            ) : (
              `Place ${side.toUpperCase()} Order`
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
