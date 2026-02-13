/**
 * AI Morning Brief - Collapsible AI-generated market summary
 */
import { useState, useMemo } from 'react';

// Strategy-based stock recommendations
const STRATEGY_RECOMMENDATIONS = {
  rotation: {
    title: "Sector Rotation Play",
    leapsPuts: {
      label: "LEAPS Puts on Growth/Tech (6-12+ months)",
      description: "High-beta growth names vulnerable to rate/multiple compression",
      picks: [
        { symbol: "NVDA", reason: "Premium rich, sensitive to AI hype cycles" },
        { symbol: "TSLA", reason: "High valuation, execution risks on multiple fronts" },
        { symbol: "ARKK", reason: "Pure growth/innovation play, rate sensitive" },
        { symbol: "SHOP", reason: "E-commerce normalization continuing" },
        { symbol: "AMD", reason: "Semiconductor cycle exposure" },
      ]
    },
    swingCalls: {
      label: "Swing Calls on Defensives (1-3 months)",
      description: "Sectors benefiting from rotation flows",
      picks: [
        { symbol: "XLU", reason: "Utilities ETF - Rate sensitivity turning positive" },
        { symbol: "KO", reason: "Dividend aristocrat, recession-resistant" },
        { symbol: "PG", reason: "Consumer staples, pricing power" },
        { symbol: "JNJ", reason: "Healthcare defensive, dividend yield" },
        { symbol: "WMT", reason: "Recession-proof consumer staples" },
      ]
    },
    timing: [
      "Watch 10Y yield levels - above 4.5% accelerates growth pain",
      "Monitor VIX - spikes favor defensive rotation",
      "Fed pivot signals could reverse this trade quickly",
      "Earnings season reactions will validate/challenge thesis",
    ],
    riskManagement: "Size positions appropriately - LEAPS puts can decay slowly but swing calls need tighter stops. Consider taking profits on 15-20% moves in either direction.",
  },
  bullish: {
    title: "Bullish Momentum Play",
    leapsCalls: {
      label: "LEAPS Calls on Leaders (6-12+ months)",
      description: "Strong fundamentals with upside catalyst potential",
      picks: [
        { symbol: "AAPL", reason: "Services growth, AI integration, buybacks" },
        { symbol: "MSFT", reason: "Cloud + AI dominance, enterprise strength" },
        { symbol: "GOOGL", reason: "AI catch-up narrative, search moat" },
        { symbol: "META", reason: "Reels momentum, efficiency gains" },
        { symbol: "AMZN", reason: "AWS reacceleration, retail margins" },
      ]
    },
    swingCalls: {
      label: "Swing Calls on Breakouts (2-4 weeks)",
      description: "Technical breakout candidates",
      picks: [
        { symbol: "CRM", reason: "Cloud recovery, AI features" },
        { symbol: "NOW", reason: "Enterprise software leader" },
        { symbol: "UBER", reason: "Profitability inflection" },
        { symbol: "ABNB", reason: "Travel demand, margin expansion" },
        { symbol: "SQ", reason: "Fintech recovery, Cash App growth" },
      ]
    },
    timing: [
      "Best entries on 2-3% pullbacks to support levels",
      "Watch for volume confirmation on breakouts",
      "Earnings dates - position accordingly",
      "Monitor Fed tone for risk-on/off shifts",
    ],
    riskManagement: "Use 20-25% position sizing max. Set stops at recent swing lows. Take partial profits at 1.5R moves.",
  },
  bearish: {
    title: "Defensive/Bearish Play",
    leapsPuts: {
      label: "LEAPS Puts on Vulnerable Names (6-12+ months)",
      description: "Companies facing fundamental headwinds",
      picks: [
        { symbol: "COIN", reason: "Crypto winter extension risk" },
        { symbol: "SNOW", reason: "Valuation compression, competition" },
        { symbol: "DASH", reason: "Profitability path unclear" },
        { symbol: "RIVN", reason: "Cash burn, execution challenges" },
        { symbol: "LCID", reason: "EV competition intensifying" },
      ]
    },
    hedges: {
      label: "Portfolio Hedges",
      description: "Protection against market downside",
      picks: [
        { symbol: "SQQQ", reason: "3x inverse Nasdaq for short-term hedge" },
        { symbol: "VXX", reason: "Volatility spike play" },
        { symbol: "TLT", reason: "Long bonds as equity hedge" },
        { symbol: "GLD", reason: "Gold for uncertainty" },
        { symbol: "UUP", reason: "Dollar strength play" },
      ]
    },
    timing: [
      "Add puts on bounces to resistance",
      "VIX below 15 = cheap protection",
      "Watch credit spreads for stress signals",
      "Major support breaks = increase hedge size",
    ],
    riskManagement: "Limit hedge positions to 5-10% of portfolio. Use defined-risk strategies like put spreads for capital efficiency.",
  },
  ivCrush: {
    title: "IV Crush Strategy",
    leapsCalls: {
      label: "Low IV LEAPS Opportunities (6-12+ months)",
      description: "Cheap options with catalyst potential",
      picks: [
        { symbol: "DIS", reason: "Streaming turnaround, parks strength" },
        { symbol: "PYPL", reason: "Beaten down, activist involvement" },
        { symbol: "INTC", reason: "Fab turnaround narrative" },
        { symbol: "BA", reason: "Production ramp recovery" },
        { symbol: "NKE", reason: "Brand strength, inventory clearing" },
      ]
    },
    swingCalls: {
      label: "Post-Earnings IV Crush Plays",
      description: "Names with elevated IV pre-earnings",
      picks: [
        { symbol: "Check IV Rank", reason: "Look for IVR > 50%" },
        { symbol: "Sell Spreads", reason: "Credit strategies into earnings" },
        { symbol: "Iron Condors", reason: "Neutral expected moves" },
      ]
    },
    timing: [
      "Enter LEAPS when IV Rank < 30%",
      "Avoid buying options 2 weeks before earnings",
      "Post-earnings day 1-3 often best entry",
      "Watch for IV crush opportunities after big moves",
    ],
    riskManagement: "IV matters most for LEAPS. A 10% IV difference can mean 15-20% price difference. Always check IV percentile before entry.",
  },
};

// Detect strategy type from focus text
const detectStrategy = (focusText) => {
  if (!focusText) return null;
  const text = focusText.toLowerCase();

  if (text.includes('rotation') || (text.includes('puts') && text.includes('calls'))) {
    return 'rotation';
  }
  if (text.includes('iv crush') || text.includes('low iv') || text.includes('cheap options')) {
    return 'ivCrush';
  }
  if (text.includes('bearish') || text.includes('hedge') || text.includes('defensive')) {
    return 'bearish';
  }
  if (text.includes('bullish') || text.includes('momentum') || text.includes('breakout')) {
    return 'bullish';
  }
  // Default to rotation for mixed strategies
  return 'rotation';
};

// Stock Pick Card Component
const StockPick = ({ symbol, reason, type }) => {
  const typeColors = {
    put: 'border-red-500/30 bg-red-500/10',
    call: 'border-green-500/30 bg-green-500/10',
    hedge: 'border-yellow-500/30 bg-yellow-500/10',
    neutral: 'border-blue-500/30 bg-blue-500/10',
  };

  return (
    <div className={`flex items-center justify-between p-2 rounded border ${typeColors[type] || typeColors.neutral}`}>
      <div className="flex items-center gap-2">
        <span className="font-mono font-bold text-white">{symbol}</span>
      </div>
      <span className="text-xs text-gray-400 text-right max-w-[200px]">{reason}</span>
    </div>
  );
};

// Today's Focus Expanded Component
const TodaysFocusExpanded = ({ focusText, onAskFollowUp }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const strategyType = detectStrategy(focusText);
  const strategy = STRATEGY_RECOMMENDATIONS[strategyType];

  if (!strategy) {
    return (
      <div className="bg-gray-700/50 rounded-lg p-3">
        <div className="text-xs text-gray-400 uppercase font-semibold mb-1">
          Today's Focus
        </div>
        <p className="text-white text-sm">{focusText}</p>
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-r from-gray-700/50 to-gray-600/30 rounded-lg border border-gray-600/50">
      {/* Focus Header */}
      <div className="p-3 border-b border-gray-600/50">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-blue-400 uppercase font-semibold mb-1 flex items-center gap-1">
              <span>🎯</span> Today's Focus
            </div>
            <p className="text-white text-sm font-medium">{focusText}</p>
          </div>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-xs text-blue-400 hover:text-blue-300 px-2 py-1 bg-blue-500/10 rounded transition-colors"
          >
            {isExpanded ? '▲ Hide Picks' : '▼ Show Picks'}
          </button>
        </div>
      </div>

      {/* Expanded Recommendations */}
      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Strategy Title */}
          <div className="text-center">
            <span className="text-lg font-bold text-white">{strategy.title}</span>
          </div>

          {/* Primary Strategy */}
          {strategy.leapsPuts && (
            <div>
              <h5 className="text-xs text-red-400 uppercase font-semibold mb-2 flex items-center gap-1">
                <span>📉</span> {strategy.leapsPuts.label}
              </h5>
              <p className="text-xs text-gray-400 mb-2">{strategy.leapsPuts.description}</p>
              <div className="space-y-1">
                {strategy.leapsPuts.picks.map((pick, idx) => (
                  <StockPick key={idx} symbol={pick.symbol} reason={pick.reason} type="put" />
                ))}
              </div>
            </div>
          )}

          {strategy.leapsCalls && (
            <div>
              <h5 className="text-xs text-green-400 uppercase font-semibold mb-2 flex items-center gap-1">
                <span>📈</span> {strategy.leapsCalls.label}
              </h5>
              <p className="text-xs text-gray-400 mb-2">{strategy.leapsCalls.description}</p>
              <div className="space-y-1">
                {strategy.leapsCalls.picks.map((pick, idx) => (
                  <StockPick key={idx} symbol={pick.symbol} reason={pick.reason} type="call" />
                ))}
              </div>
            </div>
          )}

          {/* Secondary Strategy */}
          {strategy.swingCalls && (
            <div>
              <h5 className="text-xs text-green-400 uppercase font-semibold mb-2 flex items-center gap-1">
                <span>⚡</span> {strategy.swingCalls.label}
              </h5>
              <p className="text-xs text-gray-400 mb-2">{strategy.swingCalls.description}</p>
              <div className="space-y-1">
                {strategy.swingCalls.picks.map((pick, idx) => (
                  <StockPick key={idx} symbol={pick.symbol} reason={pick.reason} type="call" />
                ))}
              </div>
            </div>
          )}

          {strategy.hedges && (
            <div>
              <h5 className="text-xs text-yellow-400 uppercase font-semibold mb-2 flex items-center gap-1">
                <span>🛡️</span> {strategy.hedges.label}
              </h5>
              <p className="text-xs text-gray-400 mb-2">{strategy.hedges.description}</p>
              <div className="space-y-1">
                {strategy.hedges.picks.map((pick, idx) => (
                  <StockPick key={idx} symbol={pick.symbol} reason={pick.reason} type="hedge" />
                ))}
              </div>
            </div>
          )}

          {/* Timing Considerations */}
          {strategy.timing && (
            <div className="bg-blue-500/10 rounded-lg p-3 border border-blue-500/20">
              <h5 className="text-xs text-blue-400 uppercase font-semibold mb-2 flex items-center gap-1">
                <span>⏰</span> Key Timing Considerations
              </h5>
              <ul className="space-y-1">
                {strategy.timing.map((item, idx) => (
                  <li key={idx} className="text-xs text-gray-300 flex items-start gap-2">
                    <span className="text-blue-400">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Risk Management */}
          {strategy.riskManagement && (
            <div className="bg-orange-500/10 rounded-lg p-3 border border-orange-500/20">
              <h5 className="text-xs text-orange-400 uppercase font-semibold mb-2 flex items-center gap-1">
                <span>⚠️</span> Risk Management
              </h5>
              <p className="text-xs text-gray-300">{strategy.riskManagement}</p>
            </div>
          )}

          {/* Quick Actions */}
          <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-600/50">
            <button
              onClick={onAskFollowUp}
              className="flex items-center gap-1 text-xs px-3 py-1.5 bg-purple-500/20 text-purple-300 rounded hover:bg-purple-500/30 transition-colors"
            >
              <span>💬</span> Ask Copilot About This
            </button>
            <button
              onClick={() => window.location.href = '/screener?preset=iv_crush'}
              className="flex items-center gap-1 text-xs px-3 py-1.5 bg-green-500/20 text-green-300 rounded hover:bg-green-500/30 transition-colors"
            >
              <span>🔍</span> Scan Low IV Stocks
            </button>
            <button
              onClick={() => window.location.href = '/screener?preset=swing_momentum'}
              className="flex items-center gap-1 text-xs px-3 py-1.5 bg-blue-500/20 text-blue-300 rounded hover:bg-blue-500/30 transition-colors"
            >
              <span>⚡</span> Find Swing Setups
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

const StrategyBadge = ({ bias }) => {
  const colors = {
    bullish: 'bg-green-500/20 text-green-400 border-green-500/30',
    bearish: 'bg-red-500/20 text-red-400 border-red-500/30',
    neutral: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  };

  const icons = {
    bullish: '📈',
    bearish: '📉',
    neutral: '⚖️',
  };

  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded border ${colors[bias] || colors.neutral}`}>
      <span>{icons[bias] || '⚖️'}</span>
      <span className="capitalize">{bias}</span>
    </span>
  );
};

export default function MorningBrief({ data, loading, onAskFollowUp, onMinimize }) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [isMinimized, setIsMinimized] = useState(false);

  if (loading) {
    return (
      <div className="bg-gradient-to-r from-blue-900/50 to-purple-900/50 rounded-lg p-4 border border-blue-500/20 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/4 mb-3"></div>
        <div className="h-16 bg-gray-700 rounded"></div>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const brief = data.brief || data;

  if (isMinimized) {
    return (
      <div
        className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 rounded-lg p-3 border border-blue-500/20 cursor-pointer hover:border-blue-500/40 transition-colors"
        onClick={() => setIsMinimized(false)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg">🤖</span>
            <span className="text-sm text-gray-300">AI Morning Brief</span>
            <StrategyBadge bias={brief.strategy_bias} />
          </div>
          <span className="text-xs text-gray-400">Click to expand</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-r from-blue-900/50 to-purple-900/50 rounded-lg border border-blue-500/20">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-blue-500/20">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🤖</span>
          <div>
            <h3 className="text-white font-semibold">AI Morning Brief</h3>
            <p className="text-xs text-gray-400">
              {data.ai_powered ? 'Powered by Claude AI' : 'Market Analysis'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StrategyBadge bias={brief.strategy_bias} />
          <button
            onClick={() => setIsMinimized(true)}
            className="text-gray-400 hover:text-white p-1 transition-colors"
            title="Minimize"
          >
            🔇
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Greeting */}
        {brief.greeting && (
          <p className="text-gray-300 mb-3">{brief.greeting}</p>
        )}

        {/* Market Summary */}
        <p className="text-white mb-4">{brief.market_summary}</p>

        {/* Key Insight */}
        {brief.key_insight && (
          <div className="bg-blue-500/10 rounded-lg p-3 mb-4 border border-blue-500/20">
            <div className="flex items-start gap-2">
              <span className="text-lg">💡</span>
              <div>
                <div className="text-xs text-blue-400 uppercase font-semibold mb-1">
                  Key Insight
                </div>
                <p className="text-white text-sm">{brief.key_insight}</p>
              </div>
            </div>
          </div>
        )}

        {/* Expandable Details */}
        {isExpanded && (
          <div className="space-y-4">
            {/* Opportunities */}
            {brief.opportunities && brief.opportunities.length > 0 && (
              <div>
                <h4 className="text-xs text-gray-400 uppercase font-semibold mb-2 flex items-center gap-1">
                  <span>🎯</span> Opportunities
                </h4>
                <ul className="space-y-1">
                  {brief.opportunities.map((opp, idx) => (
                    <li key={idx} className="text-sm text-green-300 flex items-start gap-2">
                      <span className="text-green-500">•</span>
                      <span>{opp}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Risks */}
            {brief.risks && brief.risks.length > 0 && (
              <div>
                <h4 className="text-xs text-gray-400 uppercase font-semibold mb-2 flex items-center gap-1">
                  <span>⚠️</span> Watch Out
                </h4>
                <ul className="space-y-1">
                  {brief.risks.map((risk, idx) => (
                    <li key={idx} className="text-sm text-orange-300 flex items-start gap-2">
                      <span className="text-orange-500">•</span>
                      <span>{risk}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Recommended Focus - Enhanced with stock picks */}
            {brief.recommended_focus && (
              <TodaysFocusExpanded
                focusText={brief.recommended_focus}
                onAskFollowUp={onAskFollowUp}
              />
            )}
          </div>
        )}

        {/* Toggle Details */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="mt-3 text-xs text-gray-400 hover:text-gray-300 transition-colors"
        >
          {isExpanded ? '▲ Show Less' : '▼ Show More'}
        </button>

        {/* Ask Follow-up */}
        {onAskFollowUp && (
          <div className="mt-4 pt-4 border-t border-blue-500/20">
            <button
              onClick={onAskFollowUp}
              className="w-full text-left text-sm text-gray-400 hover:text-white bg-gray-700/30 rounded-lg p-3 transition-colors flex items-center gap-2"
            >
              <span>💬</span>
              <span>Ask follow-up question...</span>
            </button>
          </div>
        )}
      </div>

      {/* Generated timestamp */}
      {data.generated_at && (
        <div className="px-4 pb-3 text-xs text-gray-500">
          Generated {new Date(data.generated_at).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
