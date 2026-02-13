/**
 * StrategySelector Component
 *
 * Interactive strategy recommendation interface:
 * - Input conviction and risk tolerance
 * - Get AI-powered strategy recommendations
 * - View delta/DTE targets
 * - Calculate position sizing
 */
import React, { useState, useEffect } from 'react';
import { strategyAPI } from '../../api/strategy';
import PositionSizer from './PositionSizer';
import RiskRewardChart from './RiskRewardChart';

const RISK_LEVELS = [
  { value: 'conservative', label: 'Conservative', description: 'Lower risk, smaller positions' },
  { value: 'moderate', label: 'Moderate', description: 'Balanced approach' },
  { value: 'aggressive', label: 'Aggressive', description: 'Higher risk for higher reward' }
];

const getStrategyColor = (strategy) => {
  const colors = {
    'leaps_call': 'bg-green-100 text-green-800 border-green-300',
    'long_call': 'bg-green-50 text-green-700 border-green-200',
    'bull_call_spread': 'bg-emerald-100 text-emerald-800 border-emerald-300',
    'long_put': 'bg-red-100 text-red-800 border-red-300',
    'bear_put_spread': 'bg-red-50 text-red-700 border-red-200',
    'iron_condor': 'bg-purple-100 text-purple-800 border-purple-300',
    'wait': 'bg-yellow-100 text-yellow-800 border-yellow-300',
    'avoid': 'bg-gray-100 text-gray-600 border-gray-300'
  };
  return colors[strategy] || 'bg-blue-100 text-blue-800 border-blue-300';
};

const getConfidenceBar = (confidence) => {
  const width = `${confidence * 10}%`;
  let color = 'bg-gray-400';
  if (confidence >= 8) color = 'bg-green-500';
  else if (confidence >= 6) color = 'bg-blue-500';
  else if (confidence >= 4) color = 'bg-yellow-500';
  else color = 'bg-red-500';

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width }} />
      </div>
      <span className="text-sm font-medium w-8">{confidence}/10</span>
    </div>
  );
};

export const StrategySelector = ({
  symbol,
  stockData = null,
  onStrategySelect = null,
  className = ''
}) => {
  const [conviction, setConviction] = useState(5);
  const [riskTolerance, setRiskTolerance] = useState('moderate');
  const [portfolioValue, setPortfolioValue] = useState(50000);
  const [recommendation, setRecommendation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeView, setActiveView] = useState('strategy');

  useEffect(() => {
    if (symbol) {
      fetchRecommendation();
    }
  }, [symbol]);

  const fetchRecommendation = async () => {
    try {
      setLoading(true);
      setError(null);

      const data = await strategyAPI.getRecommendation(symbol, {
        conviction,
        riskTolerance,
        portfolioValue
      });

      setRecommendation(data);

      if (onStrategySelect) {
        onStrategySelect(data);
      }
    } catch (err) {
      setError('Failed to get strategy recommendation');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleConvictionChange = (value) => {
    setConviction(value);
  };

  const handleApply = () => {
    fetchRecommendation();
  };

  if (!symbol) {
    return (
      <div className={`bg-gray-50 rounded-lg p-6 text-center text-gray-500 ${className}`}>
        Select a stock to get strategy recommendations
      </div>
    );
  }

  return (
    <div className={`bg-white rounded-lg border shadow-sm overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-4 py-3 bg-gray-50 border-b">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-lg text-gray-900 flex items-center gap-2">
            Strategy Selector
            <span className="text-sm font-normal text-gray-500">({symbol})</span>
          </h3>
          {recommendation && (
            <span className={`px-3 py-1 rounded-full text-sm font-medium border ${getStrategyColor(recommendation.recommendation?.strategy)}`}>
              {recommendation.recommendation?.strategy?.replace(/_/g, ' ').toUpperCase()}
            </span>
          )}
        </div>
      </div>

      {/* Inputs */}
      <div className="p-4 border-b bg-gray-50">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Conviction Slider */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Conviction Score: {conviction}
            </label>
            <input
              type="range"
              min="1"
              max="10"
              value={conviction}
              onChange={(e) => handleConvictionChange(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>Low</span>
              <span>High</span>
            </div>
          </div>

          {/* Risk Tolerance */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Risk Tolerance
            </label>
            <select
              value={riskTolerance}
              onChange={(e) => setRiskTolerance(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {RISK_LEVELS.map((level) => (
                <option key={level.value} value={level.value}>
                  {level.label}
                </option>
              ))}
            </select>
          </div>

          {/* Portfolio Value */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Portfolio Value
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">$</span>
              <input
                type="number"
                value={portfolioValue}
                onChange={(e) => setPortfolioValue(Number(e.target.value))}
                className="w-full pl-7 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </div>
        </div>

        <button
          onClick={handleApply}
          disabled={loading}
          className="mt-4 w-full bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? 'Analyzing...' : 'Get Recommendation'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 bg-red-50 text-red-600">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="p-8 text-center">
          <div className="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full mx-auto"></div>
          <p className="mt-2 text-gray-500">Analyzing strategy options...</p>
        </div>
      )}

      {/* Results */}
      {!loading && recommendation && (
        <>
          {/* View Tabs */}
          <div className="flex border-b">
            {['strategy', 'sizing', 'risk'].map((view) => (
              <button
                key={view}
                onClick={() => setActiveView(view)}
                className={`px-4 py-2 text-sm font-medium transition-colors ${
                  activeView === view
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {view === 'strategy' ? 'Strategy' : view === 'sizing' ? 'Position Size' : 'Risk/Reward'}
              </button>
            ))}
          </div>

          <div className="p-4">
            {activeView === 'strategy' && (
              <StrategyDetails recommendation={recommendation} />
            )}

            {activeView === 'sizing' && (
              <PositionSizer
                symbol={symbol}
                portfolioValue={portfolioValue}
                conviction={conviction}
                regime={recommendation.context?.market_regime}
                daysToEarnings={recommendation.context?.days_to_earnings}
              />
            )}

            {activeView === 'risk' && (
              <RiskRewardChart
                strategy={recommendation.recommendation?.strategy}
                parameters={recommendation.parameters}
              />
            )}
          </div>
        </>
      )}
    </div>
  );
};

const StrategyDetails = ({ recommendation }) => {
  const { recommendation: rec, parameters, entry_exit, alternatives, context, suggested_contract } = recommendation;

  return (
    <div className="space-y-4">
      {/* Primary Strategy */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <div className="flex items-center justify-between mb-3">
          <div>
            <span className={`px-3 py-1 rounded-full text-sm font-medium border ${getStrategyColor(rec.strategy)}`}>
              {rec.strategy.replace(/_/g, ' ').toUpperCase()}
            </span>
          </div>
          <div className="text-right">
            <div className="text-xs text-gray-500">Confidence</div>
            {getConfidenceBar(rec.confidence)}
          </div>
        </div>

        <p className="text-sm text-gray-700 mb-3">{rec.rationale}</p>

        {rec.key_factors?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {rec.key_factors.map((factor, i) => (
              <span key={i} className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                {factor}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Parameters Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 bg-gray-50 rounded-lg text-center">
          <div className="text-xs text-gray-500 uppercase">Target Delta</div>
          <div className="text-xl font-bold text-gray-900">{parameters.target_delta?.toFixed(2)}</div>
          <div className="text-xs text-gray-400">
            ({parameters.delta_range?.[0]?.toFixed(2)} - {parameters.delta_range?.[1]?.toFixed(2)})
          </div>
        </div>

        <div className="p-3 bg-gray-50 rounded-lg text-center">
          <div className="text-xs text-gray-500 uppercase">Target DTE</div>
          <div className="text-xl font-bold text-gray-900">{parameters.target_dte}</div>
          <div className="text-xs text-gray-400">
            ({parameters.dte_range?.[0]} - {parameters.dte_range?.[1]} days)
          </div>
        </div>

        <div className="p-3 bg-gray-50 rounded-lg text-center">
          <div className="text-xs text-gray-500 uppercase">Max Position</div>
          <div className="text-xl font-bold text-gray-900">{parameters.max_position_pct}%</div>
          <div className="text-xs text-gray-400">of portfolio</div>
        </div>

        <div className="p-3 bg-gray-50 rounded-lg text-center">
          <div className="text-xs text-gray-500 uppercase">Max Risk</div>
          <div className="text-xl font-bold text-gray-900">{parameters.max_risk_pct}%</div>
          <div className="text-xs text-gray-400">of portfolio</div>
        </div>
      </div>

      {/* Entry/Exit Rules */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 border rounded-lg">
          <div className="text-xs text-gray-500">Entry Type</div>
          <div className="font-medium capitalize">{entry_exit.entry_type}</div>
        </div>
        <div className="p-3 border rounded-lg">
          <div className="text-xs text-gray-500">Profit Target</div>
          <div className="font-medium text-green-600">+{entry_exit.profit_target_pct}%</div>
        </div>
        <div className="p-3 border rounded-lg">
          <div className="text-xs text-gray-500">Stop Loss</div>
          <div className="font-medium text-red-600">-{entry_exit.stop_loss_pct}%</div>
        </div>
        <div className="p-3 border rounded-lg">
          <div className="text-xs text-gray-500">Time Stop</div>
          <div className="font-medium">{entry_exit.time_stop_dte} DTE</div>
        </div>
      </div>

      {/* Suggested Contract */}
      {suggested_contract && (
        <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
          <div className="text-xs text-green-600 uppercase tracking-wide mb-1">Suggested Contract</div>
          <div className="flex items-center gap-4">
            <div>
              <span className="font-medium capitalize">{suggested_contract.type}</span>
              <span className="mx-2">@</span>
              <span className="font-bold">${suggested_contract.strike}</span>
            </div>
            <div className="text-gray-500">{suggested_contract.expiration}</div>
            <div className="text-sm text-gray-400">({suggested_contract.target_delta} delta)</div>
          </div>
          <div className="text-xs text-gray-500 mt-1">{suggested_contract.note}</div>
        </div>
      )}

      {/* Context */}
      <div className="flex flex-wrap gap-2 text-sm">
        <span className="px-2 py-1 bg-gray-100 rounded">
          Regime: <strong className="capitalize">{context.market_regime}</strong>
        </span>
        <span className="px-2 py-1 bg-gray-100 rounded">
          IV Rank: <strong>{context.iv_rank?.toFixed(0)}%</strong>
        </span>
        <span className="px-2 py-1 bg-gray-100 rounded">
          Trend: <strong className="capitalize">{context.trend_direction}</strong>
        </span>
        {context.days_to_earnings && (
          <span className="px-2 py-1 bg-yellow-100 rounded">
            Earnings: <strong>{context.days_to_earnings} days</strong>
          </span>
        )}
      </div>

      {/* Risks */}
      {rec.risks?.length > 0 && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
          <div className="text-xs text-red-600 uppercase tracking-wide mb-2">Risks to Consider</div>
          <ul className="space-y-1">
            {rec.risks.map((risk, i) => (
              <li key={i} className="text-sm text-red-700 flex items-start gap-2">
                <span className="text-red-500">!</span>
                <span>{risk}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Alternatives */}
      {alternatives?.length > 0 && (
        <div>
          <div className="text-sm font-medium text-gray-700 mb-2">Alternative Strategies</div>
          <div className="space-y-2">
            {alternatives.map((alt, i) => (
              <div key={i} className="p-3 border rounded-lg hover:bg-gray-50">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium border ${getStrategyColor(alt.strategy)}`}>
                      {alt.strategy.replace(/_/g, ' ').toUpperCase()}
                    </span>
                    <span className="text-sm text-gray-500">
                      {alt.target_delta?.toFixed(2)} delta, {alt.target_dte} DTE
                    </span>
                  </div>
                  <span className="text-sm text-gray-400">{alt.confidence}/10</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">{alt.rationale}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default StrategySelector;
