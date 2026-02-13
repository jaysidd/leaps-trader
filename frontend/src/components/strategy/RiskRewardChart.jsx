/**
 * RiskRewardChart Component
 *
 * Visualizes the risk/reward profile of an options strategy:
 * - P&L diagram at expiration
 * - Breakeven point
 * - Max profit/loss zones
 * - Win/loss probability bars
 */
import React, { useMemo } from 'react';

const RiskRewardChart = ({
  strategy = 'long_call',
  parameters = {},
  currentPrice = 100,
  premium = 5,
  strike = 100,
  secondStrike = null,
  className = ''
}) => {
  const chartData = useMemo(() => {
    return generatePayoffData(strategy, currentPrice, strike, premium, secondStrike);
  }, [strategy, currentPrice, strike, premium, secondStrike]);

  const { profitTarget, stopLoss } = parameters;

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Strategy Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SummaryCard
          label="Max Profit"
          value={chartData.maxProfit}
          color="green"
          unlimited={chartData.maxProfitUnlimited}
        />
        <SummaryCard
          label="Max Loss"
          value={chartData.maxLoss}
          color="red"
        />
        <SummaryCard
          label="Breakeven"
          value={`$${chartData.breakeven.toFixed(2)}`}
          color="blue"
        />
        <SummaryCard
          label="Risk/Reward"
          value={chartData.riskRewardRatio}
          color="purple"
        />
      </div>

      {/* Payoff Diagram */}
      <div className="p-4 bg-gray-50 rounded-lg">
        <div className="text-xs text-gray-500 uppercase mb-3">P&L at Expiration</div>
        <PayoffDiagram
          data={chartData.payoffPoints}
          breakeven={chartData.breakeven}
          currentPrice={currentPrice}
          strike={strike}
        />
      </div>

      {/* Probability Zones */}
      <div className="p-4 border rounded-lg">
        <div className="text-xs text-gray-500 uppercase mb-3">Estimated Outcomes</div>
        <ProbabilityBars
          profitProb={chartData.profitProbability}
          profitTarget={profitTarget || parameters.profit_target_pct}
          stopLoss={stopLoss || parameters.stop_loss_pct}
        />
      </div>

      {/* Strategy Characteristics */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <CharacteristicItem label="Time Decay (Theta)" value={getTheta(strategy)} />
        <CharacteristicItem label="Volatility (Vega)" value={getVega(strategy)} />
        <CharacteristicItem label="Direction (Delta)" value={getDelta(strategy, parameters.target_delta)} />
        <CharacteristicItem label="Leverage" value={getLeverage(strategy)} />
      </div>
    </div>
  );
};

const SummaryCard = ({ label, value, color, unlimited = false }) => {
  const colorClasses = {
    green: 'bg-green-50 border-green-200 text-green-700',
    red: 'bg-red-50 border-red-200 text-red-700',
    blue: 'bg-blue-50 border-blue-200 text-blue-700',
    purple: 'bg-purple-50 border-purple-200 text-purple-700'
  };

  return (
    <div className={`p-3 rounded-lg border text-center ${colorClasses[color]}`}>
      <div className="text-xs uppercase opacity-70">{label}</div>
      <div className="text-lg font-bold">
        {unlimited ? 'Unlimited' : typeof value === 'number' ? `$${value.toFixed(0)}` : value}
      </div>
    </div>
  );
};

const PayoffDiagram = ({ data, breakeven, currentPrice, strike }) => {
  const height = 120;
  const width = 300;
  const padding = { top: 10, bottom: 20, left: 40, right: 10 };

  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Calculate scales
  const minPrice = Math.min(...data.map(d => d.price));
  const maxPrice = Math.max(...data.map(d => d.price));
  const minPnL = Math.min(...data.map(d => d.pnl), 0);
  const maxPnL = Math.max(...data.map(d => d.pnl), 0);

  const scaleX = (price) => padding.left + ((price - minPrice) / (maxPrice - minPrice)) * chartWidth;
  const scaleY = (pnl) => padding.top + chartHeight - ((pnl - minPnL) / (maxPnL - minPnL || 1)) * chartHeight;

  // Generate path
  const pathD = data.map((d, i) => {
    const x = scaleX(d.price);
    const y = scaleY(d.pnl);
    return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
  }).join(' ');

  // Zero line
  const zeroY = scaleY(0);

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="max-w-md mx-auto">
      {/* Zero line */}
      <line
        x1={padding.left}
        y1={zeroY}
        x2={width - padding.right}
        y2={zeroY}
        stroke="#9CA3AF"
        strokeDasharray="4"
      />

      {/* Profit area */}
      <path
        d={`${pathD} L ${scaleX(maxPrice)} ${zeroY} L ${scaleX(minPrice)} ${zeroY} Z`}
        fill="url(#profitGradient)"
        opacity="0.3"
      />

      {/* P&L line */}
      <path
        d={pathD}
        fill="none"
        stroke="#2563EB"
        strokeWidth="2"
      />

      {/* Breakeven marker */}
      <circle
        cx={scaleX(breakeven)}
        cy={scaleY(0)}
        r="4"
        fill="#2563EB"
      />

      {/* Current price marker */}
      <line
        x1={scaleX(currentPrice)}
        y1={padding.top}
        x2={scaleX(currentPrice)}
        y2={height - padding.bottom}
        stroke="#10B981"
        strokeDasharray="2"
      />

      {/* Labels */}
      <text x={padding.left - 5} y={scaleY(maxPnL)} fontSize="10" textAnchor="end" fill="#6B7280">
        +${maxPnL.toFixed(0)}
      </text>
      <text x={padding.left - 5} y={scaleY(minPnL)} fontSize="10" textAnchor="end" fill="#6B7280">
        -${Math.abs(minPnL).toFixed(0)}
      </text>
      <text x={scaleX(breakeven)} y={height - 5} fontSize="10" textAnchor="middle" fill="#2563EB">
        BE: ${breakeven.toFixed(0)}
      </text>

      {/* Gradient definition */}
      <defs>
        <linearGradient id="profitGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#10B981" />
          <stop offset="50%" stopColor="#10B981" stopOpacity="0" />
          <stop offset="50%" stopColor="#EF4444" stopOpacity="0" />
          <stop offset="100%" stopColor="#EF4444" />
        </linearGradient>
      </defs>
    </svg>
  );
};

const ProbabilityBars = ({ profitProb, profitTarget, stopLoss }) => {
  const lossProb = 100 - profitProb;

  return (
    <div className="space-y-3">
      <div>
        <div className="flex justify-between text-sm mb-1">
          <span className="text-green-600">Profit ({profitTarget ? `>${profitTarget}%` : 'Any'})</span>
          <span className="font-medium text-green-700">{profitProb}%</span>
        </div>
        <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-green-500 transition-all"
            style={{ width: `${profitProb}%` }}
          />
        </div>
      </div>

      <div>
        <div className="flex justify-between text-sm mb-1">
          <span className="text-red-600">Loss ({stopLoss ? `>-${stopLoss}%` : 'Any'})</span>
          <span className="font-medium text-red-700">{lossProb}%</span>
        </div>
        <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-red-500 transition-all"
            style={{ width: `${lossProb}%` }}
          />
        </div>
      </div>

      <p className="text-xs text-gray-500 italic">
        Probabilities are estimates based on historical data and implied volatility
      </p>
    </div>
  );
};

const CharacteristicItem = ({ label, value }) => {
  const { text, color } = value;
  return (
    <div className="flex items-center justify-between p-2 bg-gray-50 rounded">
      <span className="text-gray-600">{label}</span>
      <span className={`font-medium ${color}`}>{text}</span>
    </div>
  );
};

// Helper functions
function generatePayoffData(strategy, currentPrice, strike, premium, secondStrike) {
  const points = [];
  const premiumPer100 = premium * 100;
  const priceRange = currentPrice * 0.4; // +/- 40% price range

  for (let i = 0; i <= 20; i++) {
    const price = currentPrice - priceRange + (priceRange * 2 * i / 20);
    let pnl = 0;

    switch (strategy) {
      case 'long_call':
      case 'leaps_call':
        pnl = price > strike
          ? (price - strike) * 100 - premiumPer100
          : -premiumPer100;
        break;

      case 'long_put':
      case 'leaps_put':
        pnl = price < strike
          ? (strike - price) * 100 - premiumPer100
          : -premiumPer100;
        break;

      case 'bull_call_spread':
        const spreadWidth = secondStrike ? secondStrike - strike : strike * 0.05;
        if (price <= strike) {
          pnl = -premiumPer100;
        } else if (price >= strike + spreadWidth) {
          pnl = spreadWidth * 100 - premiumPer100;
        } else {
          pnl = (price - strike) * 100 - premiumPer100;
        }
        break;

      case 'bear_put_spread':
        const bearSpread = secondStrike ? strike - secondStrike : strike * 0.05;
        if (price >= strike) {
          pnl = -premiumPer100;
        } else if (price <= strike - bearSpread) {
          pnl = bearSpread * 100 - premiumPer100;
        } else {
          pnl = (strike - price) * 100 - premiumPer100;
        }
        break;

      case 'iron_condor':
        // Simplified - assume premium received
        const condorWidth = strike * 0.1;
        if (price >= strike - condorWidth && price <= strike + condorWidth) {
          pnl = premiumPer100;
        } else {
          pnl = -condorWidth * 100 + premiumPer100;
        }
        break;

      default:
        pnl = price > strike
          ? (price - strike) * 100 - premiumPer100
          : -premiumPer100;
    }

    points.push({ price, pnl });
  }

  // Calculate summary stats
  const maxProfit = Math.max(...points.map(p => p.pnl));
  const maxLoss = Math.min(...points.map(p => p.pnl));
  const breakeven = strategy.includes('call') || strategy.includes('CALL')
    ? strike + premium
    : strike - premium;

  const maxProfitUnlimited = ['long_call', 'leaps_call'].includes(strategy);

  const riskRewardRatio = maxLoss !== 0
    ? `1:${Math.abs(maxProfit / maxLoss).toFixed(1)}`
    : 'N/A';

  // Rough profit probability based on delta
  const profitProbability = strategy.includes('call') ? 45 : 55;

  return {
    payoffPoints: points,
    maxProfit,
    maxLoss: Math.abs(maxLoss),
    maxProfitUnlimited,
    breakeven,
    riskRewardRatio,
    profitProbability
  };
}

function getTheta(strategy) {
  const thetaMap = {
    'long_call': { text: 'Negative (hurts)', color: 'text-red-600' },
    'leaps_call': { text: 'Less Negative', color: 'text-yellow-600' },
    'long_put': { text: 'Negative (hurts)', color: 'text-red-600' },
    'leaps_put': { text: 'Less Negative', color: 'text-yellow-600' },
    'bull_call_spread': { text: 'Neutral/Slight Neg', color: 'text-yellow-600' },
    'bear_put_spread': { text: 'Neutral/Slight Neg', color: 'text-yellow-600' },
    'iron_condor': { text: 'Positive (helps)', color: 'text-green-600' },
    'cash_secured_put': { text: 'Positive (helps)', color: 'text-green-600' },
    'covered_call': { text: 'Positive (helps)', color: 'text-green-600' }
  };
  return thetaMap[strategy] || { text: 'Neutral', color: 'text-gray-600' };
}

function getVega(strategy) {
  const vegaMap = {
    'long_call': { text: 'Positive (wants high IV)', color: 'text-green-600' },
    'leaps_call': { text: 'High Positive', color: 'text-green-600' },
    'long_put': { text: 'Positive (wants high IV)', color: 'text-green-600' },
    'leaps_put': { text: 'High Positive', color: 'text-green-600' },
    'bull_call_spread': { text: 'Reduced', color: 'text-yellow-600' },
    'bear_put_spread': { text: 'Reduced', color: 'text-yellow-600' },
    'iron_condor': { text: 'Negative (wants low IV)', color: 'text-red-600' },
    'cash_secured_put': { text: 'Negative', color: 'text-red-600' },
    'covered_call': { text: 'Negative', color: 'text-red-600' }
  };
  return vegaMap[strategy] || { text: 'Neutral', color: 'text-gray-600' };
}

function getDelta(strategy, targetDelta) {
  if (targetDelta) {
    return {
      text: `${(targetDelta * 100).toFixed(0)} per contract`,
      color: targetDelta > 0 ? 'text-green-600' : 'text-red-600'
    };
  }

  const deltaMap = {
    'long_call': { text: 'Positive (bullish)', color: 'text-green-600' },
    'leaps_call': { text: 'Strong Positive', color: 'text-green-600' },
    'long_put': { text: 'Negative (bearish)', color: 'text-red-600' },
    'leaps_put': { text: 'Strong Negative', color: 'text-red-600' },
    'bull_call_spread': { text: 'Moderate Positive', color: 'text-green-600' },
    'bear_put_spread': { text: 'Moderate Negative', color: 'text-red-600' },
    'iron_condor': { text: 'Near Zero', color: 'text-gray-600' }
  };
  return deltaMap[strategy] || { text: 'Varies', color: 'text-gray-600' };
}

function getLeverage(strategy) {
  const leverageMap = {
    'long_call': { text: 'High (10-20x)', color: 'text-blue-600' },
    'leaps_call': { text: 'Medium (5-10x)', color: 'text-blue-600' },
    'long_put': { text: 'High (10-20x)', color: 'text-blue-600' },
    'leaps_put': { text: 'Medium (5-10x)', color: 'text-blue-600' },
    'bull_call_spread': { text: 'Medium (3-5x)', color: 'text-blue-600' },
    'bear_put_spread': { text: 'Medium (3-5x)', color: 'text-blue-600' },
    'iron_condor': { text: 'Low (1-2x)', color: 'text-gray-600' },
    'cash_secured_put': { text: 'Low (1x)', color: 'text-gray-600' },
    'covered_call': { text: 'Low (1x)', color: 'text-gray-600' }
  };
  return leverageMap[strategy] || { text: 'Varies', color: 'text-gray-600' };
}

export default RiskRewardChart;
