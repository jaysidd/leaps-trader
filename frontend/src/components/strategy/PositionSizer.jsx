/**
 * PositionSizer Component
 *
 * Calculates and displays optimal position sizing:
 * - Kelly Criterion based sizing
 * - Adjustments for conviction, regime, catalysts
 * - Max contracts calculator
 * - Risk warnings
 */
import React, { useState, useEffect } from 'react';
import { strategyAPI } from '../../api/strategy';

const PositionSizer = ({
  symbol = null,
  portfolioValue = 50000,
  conviction = 5,
  regime = 'neutral',
  daysToEarnings = null,
  optionPremium = null,
  sector = null,
  className = ''
}) => {
  const [sizing, setSizing] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [customPremium, setCustomPremium] = useState(optionPremium || '');
  const [method, setMethod] = useState('kelly');

  useEffect(() => {
    calculateSize();
  }, [portfolioValue, conviction, regime, daysToEarnings, method]);

  const calculateSize = async () => {
    if (portfolioValue <= 0) return;

    try {
      setLoading(true);
      setError(null);

      const data = await strategyAPI.calculatePositionSize({
        portfolioValue,
        conviction,
        marketRegime: regime,
        daysToEarnings,
        optionPremium: customPremium ? Number(customPremium) : null,
        sector,
        method
      });

      setSizing(data);
    } catch (err) {
      setError('Failed to calculate position size');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handlePremiumChange = (e) => {
    setCustomPremium(e.target.value);
  };

  const handleCalculate = () => {
    calculateSize();
  };

  if (loading && !sizing) {
    return (
      <div className={`animate-pulse ${className}`}>
        <div className="h-32 bg-gray-200 rounded-lg"></div>
      </div>
    );
  }

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Inputs */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Option Premium ($)</label>
          <div className="flex gap-2">
            <input
              type="number"
              step="0.05"
              value={customPremium}
              onChange={handlePremiumChange}
              placeholder="e.g., 5.50"
              className="flex-1 px-3 py-1.5 border rounded text-sm focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={handleCalculate}
              className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
            >
              Calc
            </button>
          </div>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Sizing Method</label>
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            className="w-full px-3 py-1.5 border rounded text-sm focus:ring-2 focus:ring-blue-500"
          >
            <option value="kelly">Kelly Criterion</option>
            <option value="risk_based">Risk-Based (2%)</option>
            <option value="fixed_percent">Fixed Percent</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="p-2 bg-red-50 text-red-600 text-sm rounded">
          {error}
        </div>
      )}

      {sizing && (
        <>
          {/* Main Results */}
          <div className="grid grid-cols-3 gap-3">
            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-center">
              <div className="text-xs text-blue-600 uppercase">Position Size</div>
              <div className="text-2xl font-bold text-blue-800">
                {sizing.recommended_size.percent}%
              </div>
              <div className="text-sm text-blue-600">
                ${sizing.recommended_size.dollars.toLocaleString()}
              </div>
            </div>

            <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-center">
              <div className="text-xs text-green-600 uppercase">Max Contracts</div>
              <div className="text-2xl font-bold text-green-800">
                {sizing.recommended_size.max_contracts || '—'}
              </div>
              <div className="text-sm text-green-600">
                {customPremium ? `@ $${customPremium}` : 'Enter premium'}
              </div>
            </div>

            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-center">
              <div className="text-xs text-red-600 uppercase">Max Risk</div>
              <div className="text-2xl font-bold text-red-800">
                ${sizing.risk.max_risk_dollars.toLocaleString()}
              </div>
              <div className="text-sm text-red-600">
                {sizing.risk.risk_percent}% of portfolio
              </div>
            </div>
          </div>

          {/* Multipliers Breakdown */}
          <div className="p-3 bg-gray-50 rounded-lg">
            <div className="text-xs text-gray-500 uppercase mb-2">Size Calculation Breakdown</div>
            <div className="space-y-2">
              <MultiplierRow
                label="Base Size"
                value={`${sizing.multipliers.base_size_pct}%`}
                multiplier={null}
              />
              <MultiplierRow
                label="Conviction"
                value={`${conviction}/10`}
                multiplier={sizing.multipliers.conviction}
                positive={sizing.multipliers.conviction >= 1}
              />
              <MultiplierRow
                label="Market Regime"
                value={regime}
                multiplier={sizing.multipliers.regime}
                positive={sizing.multipliers.regime >= 1}
              />
              <MultiplierRow
                label="Catalyst Timing"
                value={daysToEarnings ? `${daysToEarnings}d to earnings` : 'No catalyst'}
                multiplier={sizing.multipliers.catalyst}
                positive={sizing.multipliers.catalyst >= 1}
              />
              <MultiplierRow
                label="Correlation"
                value={sector || 'N/A'}
                multiplier={sizing.multipliers.correlation}
                positive={sizing.multipliers.correlation >= 1}
              />
            </div>
          </div>

          {/* Rationale */}
          <div className="p-3 border rounded-lg">
            <div className="text-xs text-gray-500 uppercase mb-1">Sizing Logic</div>
            <p className="text-sm text-gray-700">{sizing.rationale}</p>
          </div>

          {/* Limits Hit */}
          {(sizing.limits_hit.max_position || sizing.limits_hit.max_sector || sizing.limits_hit.max_concentration) && (
            <div className="flex flex-wrap gap-2">
              {sizing.limits_hit.max_position && (
                <span className="px-2 py-1 bg-orange-100 text-orange-700 text-xs rounded">
                  Max Position Limit Applied
                </span>
              )}
              {sizing.limits_hit.max_sector && (
                <span className="px-2 py-1 bg-orange-100 text-orange-700 text-xs rounded">
                  Sector Limit Applied
                </span>
              )}
              {sizing.limits_hit.max_concentration && (
                <span className="px-2 py-1 bg-orange-100 text-orange-700 text-xs rounded">
                  Concentration Limit Applied
                </span>
              )}
            </div>
          )}

          {/* Warnings */}
          {sizing.warnings?.length > 0 && (
            <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
              <div className="text-xs text-yellow-600 uppercase mb-1">Warnings</div>
              <ul className="space-y-1">
                {sizing.warnings.map((warning, i) => (
                  <li key={i} className="text-sm text-yellow-700 flex items-start gap-2">
                    <span className="text-yellow-500">!</span>
                    <span>{warning}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
};

const MultiplierRow = ({ label, value, multiplier, positive = true }) => {
  return (
    <div className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2">
        <span className="text-gray-600">{label}:</span>
        <span className="text-gray-900 font-medium">{value}</span>
      </div>
      {multiplier !== null && (
        <span className={`font-medium ${
          multiplier > 1 ? 'text-green-600' :
          multiplier < 1 ? 'text-red-600' : 'text-gray-600'
        }`}>
          {multiplier > 1 ? '+' : ''}{((multiplier - 1) * 100).toFixed(0)}%
        </span>
      )}
    </div>
  );
};

export default PositionSizer;
