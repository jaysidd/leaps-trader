/**
 * Profit/Loss Chart Component
 *
 * Visual P/L diagram showing outcomes at various stock prices.
 * Inspired by TastyTrade's curve analysis.
 */
import { useState, useEffect } from 'react';
import Card from '../common/Card';
import { screenerAPI } from '../../api/screener';
import { formatCurrency } from '../../utils/formatters';

export default function PLChart({
  strike,
  premium,
  currentPrice,
  symbol = '',
  priceRangePercent = 50,
  onCalculate = null
}) {
  const [plData, setPlData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const canCalculate = strike > 0 && premium > 0 && currentPrice > 0;

  const calculatePL = async () => {
    if (!canCalculate) return;

    setLoading(true);
    setError(null);

    try {
      const result = await screenerAPI.calculatePLTable(
        strike,
        premium,
        currentPrice,
        priceRangePercent,
        15
      );
      setPlData(result);
      if (onCalculate) onCalculate(result);
    } catch (err) {
      setError(err.message || 'Failed to calculate P/L');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (canCalculate) {
      calculatePL();
    }
  }, [strike, premium, currentPrice]);

  // Find max profit and loss for scaling
  const maxProfit = plData?.pl_table?.reduce((max, row) =>
    Math.max(max, row.profit_per_contract), 0) || 0;
  const maxLoss = plData?.pl_table?.reduce((min, row) =>
    Math.min(min, row.profit_per_contract), 0) || 0;
  const range = Math.max(Math.abs(maxProfit), Math.abs(maxLoss));

  // Calculate bar width percentage
  const getBarWidth = (value) => {
    if (range === 0) return 0;
    return Math.abs(value / range) * 50; // Max 50% width
  };

  return (
    <Card title="Profit/Loss Analysis">
      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-md text-sm">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      )}

      {plData && !loading && (
        <div className="space-y-4">
          {/* Summary */}
          <div className="grid grid-cols-3 gap-4">
            <div className="p-3 bg-red-50 rounded-lg text-center">
              <div className="text-xs text-red-600 font-medium">Max Loss</div>
              <div className="text-lg font-bold text-red-700">{formatCurrency(plData.max_loss)}</div>
              <div className="text-xs text-red-500">per contract</div>
            </div>
            <div className="p-3 bg-gray-50 rounded-lg text-center">
              <div className="text-xs text-gray-600 font-medium">Break-even</div>
              <div className="text-lg font-bold text-gray-800">{formatCurrency(plData.break_even)}</div>
              <div className="text-xs text-gray-500">at expiration</div>
            </div>
            <div className="p-3 bg-green-50 rounded-lg text-center">
              <div className="text-xs text-green-600 font-medium">Max Profit</div>
              <div className="text-lg font-bold text-green-700">Unlimited</div>
              <div className="text-xs text-green-500">for calls</div>
            </div>
          </div>

          {/* Visual P/L Chart */}
          <div className="border rounded-lg overflow-hidden">
            <div className="bg-gray-100 px-3 py-2 text-xs font-medium text-gray-700 flex justify-between">
              <span>Stock Price</span>
              <span>P/L at Expiration</span>
            </div>

            <div className="divide-y divide-gray-100">
              {plData.pl_table?.map((row, idx) => (
                <div
                  key={idx}
                  className={`flex items-center px-3 py-2 text-sm ${
                    row.is_current_price ? 'bg-blue-50' :
                    row.is_break_even ? 'bg-yellow-50' : ''
                  }`}
                >
                  {/* Price Label */}
                  <div className="w-20 flex-shrink-0">
                    <span className={`font-medium ${row.is_current_price ? 'text-blue-600' : 'text-gray-700'}`}>
                      {formatCurrency(row.stock_price)}
                    </span>
                    {row.is_current_price && (
                      <span className="ml-1 text-xs text-blue-500">(now)</span>
                    )}
                    {row.is_break_even && (
                      <span className="ml-1 text-xs text-yellow-600">(BE)</span>
                    )}
                  </div>

                  {/* Bar Chart */}
                  <div className="flex-1 flex items-center">
                    {/* Left side (losses) */}
                    <div className="w-1/2 flex justify-end pr-1">
                      {row.profit_per_contract < 0 && (
                        <div
                          className="h-5 bg-red-400 rounded-l"
                          style={{ width: `${getBarWidth(row.profit_per_contract)}%` }}
                        />
                      )}
                    </div>

                    {/* Center line */}
                    <div className="w-px h-6 bg-gray-400" />

                    {/* Right side (profits) */}
                    <div className="w-1/2 pl-1">
                      {row.profit_per_contract > 0 && (
                        <div
                          className="h-5 bg-green-400 rounded-r"
                          style={{ width: `${getBarWidth(row.profit_per_contract)}%` }}
                        />
                      )}
                    </div>
                  </div>

                  {/* P/L Value */}
                  <div className={`w-24 text-right font-medium ${
                    row.profit_per_contract > 0 ? 'text-green-600' :
                    row.profit_per_contract < 0 ? 'text-red-600' : 'text-gray-600'
                  }`}>
                    {row.profit_per_contract >= 0 ? '+' : ''}{formatCurrency(row.profit_per_contract)}
                  </div>

                  {/* Return % */}
                  <div className={`w-16 text-right text-xs ${
                    row.return_percent > 0 ? 'text-green-500' :
                    row.return_percent < 0 ? 'text-red-500' : 'text-gray-500'
                  }`}>
                    {row.return_percent > 0 ? '+' : ''}{row.return_percent?.toFixed(0)}%
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Legend */}
          <div className="flex items-center justify-center gap-6 text-xs text-gray-500">
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-blue-100 border border-blue-300 rounded"></div>
              <span>Current Price</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-yellow-100 border border-yellow-300 rounded"></div>
              <span>Break-even</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-green-400 rounded"></div>
              <span>Profit</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-red-400 rounded"></div>
              <span>Loss</span>
            </div>
          </div>

          {/* Quick Stats */}
          <div className="p-3 bg-gray-50 rounded-lg text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">Premium Paid:</span>
              <span className="font-medium">{formatCurrency(premium)} per share ({formatCurrency(premium * 100)} per contract)</span>
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-gray-600">Strike Price:</span>
              <span className="font-medium">{formatCurrency(strike)}</span>
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-gray-600">Stock must rise to break even:</span>
              <span className="font-medium text-yellow-600">
                +{((plData.break_even - currentPrice) / currentPrice * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        </div>
      )}

      {!plData && !loading && !error && (
        <div className="text-center py-8 text-gray-500">
          <p>Enter option details to see P/L analysis</p>
        </div>
      )}
    </Card>
  );
}
