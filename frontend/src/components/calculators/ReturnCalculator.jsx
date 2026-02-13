/**
 * 5x Return Calculator Component
 *
 * Shows exactly what stock price is needed for various return multiples
 * on a LEAPS call option.
 */
import { useState, useEffect } from 'react';
import Card from '../common/Card';
import { screenerAPI } from '../../api/screener';
import { formatCurrency, formatPercent } from '../../utils/formatters';

const FEASIBILITY_COLORS = {
  'Very Achievable': 'text-green-600 bg-green-50',
  'Achievable': 'text-green-500 bg-green-50',
  'Challenging': 'text-yellow-600 bg-yellow-50',
  'Aggressive': 'text-orange-600 bg-orange-50',
  'Very Aggressive': 'text-red-600 bg-red-50',
};

export default function ReturnCalculator({
  currentPrice,
  strike,
  premium,
  dte,
  symbol = '',
  onCalculate = null
}) {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Custom inputs for manual calculation
  const [customInputs, setCustomInputs] = useState({
    currentPrice: currentPrice || '',
    strike: strike || '',
    premium: premium || '',
    dte: dte || 400,
  });

  // Use props or custom inputs
  const effectiveInputs = {
    currentPrice: currentPrice || parseFloat(customInputs.currentPrice) || 0,
    strike: strike || parseFloat(customInputs.strike) || 0,
    premium: premium || parseFloat(customInputs.premium) || 0,
    dte: dte || parseInt(customInputs.dte) || 400,
  };

  const canCalculate = effectiveInputs.currentPrice > 0 &&
                       effectiveInputs.strike > 0 &&
                       effectiveInputs.premium > 0 &&
                       effectiveInputs.dte > 0;

  const calculateReturns = async () => {
    if (!canCalculate) return;

    setLoading(true);
    setError(null);

    try {
      const result = await screenerAPI.calculate5xReturn(
        effectiveInputs.currentPrice,
        effectiveInputs.strike,
        effectiveInputs.premium,
        effectiveInputs.dte
      );
      setAnalysis(result);
      if (onCalculate) onCalculate(result);
    } catch (err) {
      setError(err.message || 'Failed to calculate');
    } finally {
      setLoading(false);
    }
  };

  // Auto-calculate when props change
  useEffect(() => {
    if (currentPrice && strike && premium && dte) {
      calculateReturns();
    }
  }, [currentPrice, strike, premium, dte]);

  return (
    <Card title="5x Return Calculator">
      {/* Input Section - Only show if no props provided */}
      {!currentPrice && (
        <div className="mb-6 p-4 bg-gray-50 rounded-lg">
          <h4 className="text-sm font-medium text-gray-700 mb-3">Enter Option Details</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Stock Price</label>
              <input
                type="number"
                value={customInputs.currentPrice}
                onChange={(e) => setCustomInputs(prev => ({ ...prev, currentPrice: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                placeholder="100.00"
                step="0.01"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Strike Price</label>
              <input
                type="number"
                value={customInputs.strike}
                onChange={(e) => setCustomInputs(prev => ({ ...prev, strike: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                placeholder="95.00"
                step="0.01"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Premium</label>
              <input
                type="number"
                value={customInputs.premium}
                onChange={(e) => setCustomInputs(prev => ({ ...prev, premium: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                placeholder="15.00"
                step="0.01"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Days to Expiry</label>
              <input
                type="number"
                value={customInputs.dte}
                onChange={(e) => setCustomInputs(prev => ({ ...prev, dte: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                placeholder="400"
              />
            </div>
          </div>
          <button
            onClick={calculateReturns}
            disabled={!canCalculate || loading}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {loading ? 'Calculating...' : 'Calculate Returns'}
          </button>
        </div>
      )}

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

      {analysis && !loading && (
        <div className="space-y-6">
          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-3 bg-blue-50 rounded-lg">
              <div className="text-xs text-blue-600 font-medium">Current Price</div>
              <div className="text-lg font-bold text-blue-800">{formatCurrency(analysis.current_price)}</div>
            </div>
            <div className="p-3 bg-gray-50 rounded-lg">
              <div className="text-xs text-gray-600 font-medium">Strike</div>
              <div className="text-lg font-bold text-gray-800">{formatCurrency(analysis.strike)}</div>
            </div>
            <div className="p-3 bg-purple-50 rounded-lg">
              <div className="text-xs text-purple-600 font-medium">Premium/Contract</div>
              <div className="text-lg font-bold text-purple-800">{formatCurrency(analysis.premium_per_contract)}</div>
            </div>
            <div className="p-3 bg-green-50 rounded-lg">
              <div className="text-xs text-green-600 font-medium">Break-even</div>
              <div className="text-lg font-bold text-green-800">{formatCurrency(analysis.break_even)}</div>
              <div className="text-xs text-green-600">+{analysis.break_even_percent_move?.toFixed(1)}%</div>
            </div>
          </div>

          {/* Return Targets Table */}
          <div>
            <h4 className="text-sm font-medium text-gray-700 mb-3">Return Targets</h4>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-100">
                    <th className="px-3 py-2 text-left font-medium text-gray-700">Target</th>
                    <th className="px-3 py-2 text-right font-medium text-gray-700">Stock Price Needed</th>
                    <th className="px-3 py-2 text-right font-medium text-gray-700">Stock Move</th>
                    <th className="px-3 py-2 text-right font-medium text-gray-700">Annualized</th>
                    <th className="px-3 py-2 text-right font-medium text-gray-700">Profit/Contract</th>
                    <th className="px-3 py-2 text-center font-medium text-gray-700">Feasibility</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.targets?.map((target, idx) => (
                    <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                      <td className="px-3 py-2 font-bold text-blue-600">{target.multiplier}</td>
                      <td className="px-3 py-2 text-right font-medium">{formatCurrency(target.target_stock_price)}</td>
                      <td className="px-3 py-2 text-right text-green-600">+{target.stock_move_percent}%</td>
                      <td className="px-3 py-2 text-right text-gray-600">{target.annualized_return_needed}%/yr</td>
                      <td className="px-3 py-2 text-right font-medium text-green-700">
                        {formatCurrency(target.profit_per_contract)}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${FEASIBILITY_COLORS[target.feasibility] || 'text-gray-600 bg-gray-100'}`}>
                          {target.feasibility}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Time Decay Info */}
          {analysis.time_decay_info && (
            <div>
              <h4 className="text-sm font-medium text-gray-700 mb-3">Time Decay Profile</h4>
              <p className="text-xs text-gray-500 mb-2">{analysis.time_decay_info.note}</p>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                {analysis.time_decay_info.decay_profile?.map((milestone, idx) => (
                  <div key={idx} className="p-2 bg-gray-50 rounded text-center">
                    <div className="text-xs text-gray-500">{milestone.milestone}</div>
                    <div className="text-sm font-medium text-gray-800">{formatCurrency(milestone.estimated_premium)}</div>
                    <div className="text-xs text-red-500">-{milestone.premium_lost_percent}%</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Key Insight */}
          <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
            <div className="flex items-start gap-2">
              <span className="text-yellow-600 text-lg">💡</span>
              <div>
                <div className="text-sm font-medium text-yellow-800">Key Insight</div>
                <div className="text-sm text-yellow-700">
                  For a <strong>5x return</strong>, {symbol || 'the stock'} needs to reach{' '}
                  <strong>{formatCurrency(analysis.targets?.find(t => t.multiplier === '5x')?.target_stock_price || 0)}</strong>{' '}
                  ({analysis.targets?.find(t => t.multiplier === '5x')?.stock_move_percent}% move) by expiration.
                  This requires an annualized return of{' '}
                  <strong>{analysis.targets?.find(t => t.multiplier === '5x')?.annualized_return_needed}%</strong>.
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
