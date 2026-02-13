/**
 * Strategy Detail Modal
 *
 * Educational popup that shows strategy mechanics, checklist,
 * entry/exit rules, and failure modes from the Trading Prompt Library.
 * Triggered by clicking on the strategy name in the Trading Signals table.
 */
import { useState } from 'react';

// ── Strategy Content Database ──────────────────────────────────────────────────
// Adapted from: /guides/TradingPromptLibrary.md + /trading-strategies/TradingStrategyPlaybook.md

const STRATEGY_DATA = {
  orb_breakout: {
    name: 'ORB Breakout',
    fullName: 'Opening Range Breakout + VWAP Trend',
    category: 'Intraday Trend',
    timeframe: '5m',
    icon: '🚀',
    color: 'blue',
    description:
      'Trend-following setup that trades the breakout of the Opening Range (first 15 minutes) aligned with VWAP and the higher-timeframe trend direction. Looks for volume expansion on the breakout candle.',
    how_it_works: [
      'Define the Opening Range (OR) = high/low of the first 3 completed 5-minute candles after cash open.',
      'Wait for a candle to CLOSE above OR High (long) or below OR Low (short).',
      'Confirm with volume spike (volume > 1.2x VolMA20) and RVOL threshold.',
      'Pullback to ORH/ORL or VWAP must hold for confirmation entry.',
      'Higher-timeframe trend must align: EMA8 > EMA21 for longs, EMA8 < EMA21 for shorts.',
    ],
    checklist: [
      { label: 'Trend Aligned', detail: 'H1 trend direction matches trade direction (EMA20 > EMA50 for bull, inverse for bear)' },
      { label: 'OR Break + Close', detail: 'Candle closes beyond OR High/Low (not just a wick)' },
      { label: 'VWAP Supportive', detail: 'Price above VWAP for longs, below VWAP for shorts' },
      { label: 'Volume Confirmed', detail: 'Breakout candle volume > 1.2x 20-bar average, RVOL >= 1.30' },
      { label: 'Market Proxy Aligned', detail: 'SPY/QQQ direction supports the trade bias' },
    ],
    entry_rules: {
      long: 'Close breaks above ORH, then pullback holds ORH or reclaims VWAP. Enter on confirmation close.',
      short: 'Close breaks below ORL, then pullback rejects ORL or loses VWAP. Enter on confirmation close.',
    },
    stop_rules: 'Stop = OR High/Low minus 0.5x ATR(14, 5m), OR below breakout candle low. Exit immediately if price closes back inside the OR.',
    target_rules: 'TP1 at 1R (risk:reward 1:1), then trail under EMA8 (5m). TP2 at session extension / next key level. Move to breakeven after TP1.',
    risk_management: 'Risk per trade: defined by ATR. R:R minimum 1.5:1. Max 1 re-entry if initial breakout fails and sets up again.',
    failure_modes: [
      'Close back below ORH (long) or above ORL (short) = failed breakout, exit immediately',
      'Mixed trend regime on higher timeframe = NO TRADE',
      'Low RVOL (< 1.20) = insufficient momentum, skip',
      'ATR% below 0.55 = not enough volatility for clean move',
    ],
    scoring: {
      title: 'Confluence Scoring (0-10)',
      factors: [
        { name: 'Trend alignment', weight: 2 },
        { name: 'OR break + close quality', weight: 2 },
        { name: 'VWAP context', weight: 2 },
        { name: 'Volume confirmation', weight: 2 },
        { name: 'Market proxy alignment', weight: 2 },
      ],
    },
    filters: {
      'Min ATR% (5m)': '0.45-0.80 (start 0.55)',
      'RVOL (5m)': '1.20-1.60 (start 1.30)',
      'Volume Spike': '> 1.20x VolMA20',
      'Skip After Open': '3 bars (15 min)',
    },
    example: {
      title: 'Example: AAPL ORB Breakout Long',
      steps: [
        '9:30-9:45 AM: First 3 candles form OR with High at $186.50, Low at $184.80',
        '9:50 AM: 5m candle closes at $186.75, above ORH ($186.50) with 1.8x volume spike',
        'Confirmation: Price above VWAP ($185.90), EMA8 > EMA21 on H1',
        'Entry at $186.75 on close',
        'Stop at $186.50 - (0.5 x $1.20 ATR) = $185.90',
        'TP1 at $187.60 (1R), trail under EMA8 for TP2',
      ],
    },
  },

  vwap_pullback: {
    name: 'VWAP Pullback',
    fullName: 'VWAP Pullback Trend Continuation',
    category: 'Intraday Trend',
    timeframe: '5m / 15m',
    icon: '📐',
    color: 'purple',
    description:
      'Trend-day continuation setup that enters on a pullback to VWAP or the 20/21 EMA. Requires the pullback to show volume contraction followed by a trigger candle with expansion back in the trend direction.',
    how_it_works: [
      'Identify an established trend: price on the trend side of VWAP with EMA8 > EMA21 (bull) or EMA8 < EMA21 (bear).',
      'Wait for a pullback to VWAP or the 20/21 EMA with decreasing volume (contraction).',
      'Look for a trigger candle: a close that reclaims VWAP with structure (higher-low for longs, lower-high for shorts).',
      'Volume should expand on the trigger candle vs the pullback candles.',
      'RSI(14) should be above 50 for longs or below 50 for shorts.',
    ],
    checklist: [
      { label: 'Trend Established', detail: 'EMA8 > EMA21 for longs, price trending on correct side of VWAP' },
      { label: 'Pullback Quality', detail: 'Orderly pullback to VWAP/EMA with lower volume (contraction)' },
      { label: 'VWAP Reclaim', detail: 'Trigger candle closes back above VWAP (long) or below VWAP (short)' },
      { label: 'Volume Pattern', detail: 'Volume contracts on pullback, expands on trigger candle' },
      { label: 'Level Confluence', detail: 'Pullback zone aligns with key level (PDH/PDL, gap level, support/resistance)' },
    ],
    entry_rules: {
      long: 'Price tags VWAP or EMA21 during pullback with volume contraction, then close reclaims VWAP with higher-low structure.',
      short: 'Price rallies to VWAP or EMA21 with volume contraction, then close back below VWAP with lower-high structure.',
    },
    stop_rules: 'Stop below pullback swing low + 1.0x ATR buffer. Exit if price loses VWAP and cannot reclaim within 2 bars.',
    target_rules: 'TP1 at prior swing high/low. TP2 at session extension. Move to breakeven after TP1. Trail under EMA8 or last higher-low.',
    risk_management: 'R:R minimum 1.5:1. Prefer entries where pullback is shallow (38-50% retracement of the trend leg). Deeper pullbacks require stronger trigger.',
    failure_modes: [
      'VWAP fails to hold on the pullback (closes below VWAP for 2+ bars) = trend weakening',
      'Volume does not contract on pullback = selling/buying pressure, not a healthy pullback',
      'No clear higher-low (long) or lower-high (short) structure before trigger',
      'RSI divergence against the trend = momentum fading',
    ],
    scoring: {
      title: 'Confluence Scoring (0-10)',
      factors: [
        { name: 'Trend alignment', weight: 2 },
        { name: 'VWAP context', weight: 2 },
        { name: 'Pullback quality', weight: 2 },
        { name: 'Volume pattern', weight: 2 },
        { name: 'Level confluence', weight: 2 },
      ],
    },
    filters: {
      'EMA Alignment': 'EMA8 > EMA21 (long) or EMA8 < EMA21 (short)',
      'RSI(14)': '> 50 for longs, < 50 for shorts',
      'Volume Contraction': 'Pullback volume < VolMA20',
      'MACD': 'Histogram > 0 (long) or < 0 (short)',
    },
    example: {
      title: 'Example: MSFT VWAP Pullback Long',
      steps: [
        'Morning trend: MSFT gaps up, EMA8 > EMA21 on 5m, price above VWAP at $415.50',
        '10:15 AM: Pullback begins, price drifts toward VWAP ($414.80) with declining volume',
        '10:30 AM: Price tags VWAP at $414.85, volume is 60% of 20-bar avg (contraction)',
        '10:35 AM: Trigger candle closes at $415.20, back above VWAP with 1.3x volume expansion',
        'Entry at $415.20, Stop below pullback low $414.60 - ATR buffer = $414.10',
        'TP1 at morning high $416.40 (1.1R), trail under EMA8 for TP2',
      ],
    },
  },

  range_breakout: {
    name: 'Range Breakout',
    fullName: 'Range Breakout / HOD-LOD Momentum',
    category: 'Intraday Swing',
    timeframe: '15m',
    icon: '💥',
    color: 'orange',
    description:
      'Breakout from a defined range (last 30 bars or session high/low) on the 15-minute timeframe, aligned with EMA trend and confirmed by volume expansion. Designed for fewer, higher-quality trend legs with wider stops.',
    how_it_works: [
      'Define the range: highest high and lowest low of the last 30 bars (configurable) on 15m.',
      'Wait for a 15m candle to CLOSE above the range high (long) or below the range low (short).',
      'Confirm with volume spike and RVOL >= threshold.',
      'EMA8 must be above EMA21 for longs, below for shorts.',
      'RSI(14) should be >= 55 for longs or <= 45 for shorts (momentum confirmation).',
    ],
    checklist: [
      { label: 'Range Defined', detail: 'Clear consolidation range with at least 30 bars of price action (15m)' },
      { label: 'Break + Close', detail: '15m candle closes beyond range boundary (not just a wick)' },
      { label: 'Volume Expansion', detail: 'Breakout candle shows volume spike > 1.15x VolMA20, RVOL >= 1.20' },
      { label: 'EMA Trend', detail: 'EMA8 > EMA21 (long) or EMA8 < EMA21 (short) confirming direction' },
      { label: 'Momentum Confirmed', detail: 'RSI(14) >= 55 for longs or <= 45 for shorts, MACD histogram supportive' },
    ],
    entry_rules: {
      long: 'Close breaks above range high with volume spike, RVOL >= threshold, and EMA8 > EMA21.',
      short: 'Close breaks below range low with volume spike, RVOL >= threshold, and EMA8 < EMA21.',
    },
    stop_rules: 'Stop below range high minus 0.6x ATR(14, 15m) OR below breakout bar low. Exit immediately if price closes back inside the range.',
    target_rules: 'Trail under EMA21 once in profit. TP1 at next key level (PDH, swing high). TP2 at session extension.',
    risk_management: 'R:R minimum 1.5:1. Skip bars after open: 2 bars (30 min) to avoid opening noise. Max 1 re-entry per range level.',
    failure_modes: [
      'Close returns inside the range = failed breakout, exit immediately',
      'Low RVOL (< 1.10) = no real institutional participation',
      'EMA8/EMA21 not aligned with breakout direction = counter-trend trade, higher failure rate',
      'Breakout on declining volume = likely false breakout',
    ],
    scoring: {
      title: 'Confluence Scoring (0-10)',
      factors: [
        { name: 'Trend alignment', weight: 2 },
        { name: 'Compression quality', weight: 2 },
        { name: 'Break volume', weight: 2 },
        { name: 'VWAP context', weight: 2 },
        { name: 'Market proxy', weight: 2 },
      ],
    },
    filters: {
      'Min ATR% (15m)': '0.60-1.20 (start 0.80)',
      'RVOL (15m)': '1.10-1.50 (start 1.20)',
      'Volume Spike': '> 1.15x VolMA20',
      'Skip After Open': '2 bars (30 min)',
      'ADX (optional)': '> 20 for trend confirmation',
    },
    example: {
      title: 'Example: NVDA Range Breakout Long',
      steps: [
        'Morning session: NVDA consolidates between $875-$882 for 2 hours on 15m chart',
        '11:45 AM: 15m candle closes at $883.50, above range high $882 with 1.6x volume spike',
        'Confirmation: EMA8 ($880) > EMA21 ($878), RSI at 58, RVOL at 1.35',
        'Entry at $883.50 on close',
        'Stop at $882 - (0.6 x $3.50 ATR) = $879.90',
        'Trail under EMA21, first target at prior day high $890',
      ],
    },
  },
};

// Map full strategy keys (with direction) to base strategies
function getBaseStrategy(strategy) {
  if (!strategy) return null;
  const base = strategy.replace(/_long$/, '').replace(/_short$/, '');
  return STRATEGY_DATA[base] || null;
}

function getDirection(strategy) {
  if (!strategy) return null;
  if (strategy.endsWith('_long')) return 'long';
  if (strategy.endsWith('_short')) return 'short';
  return null;
}

// ── Color Utility ──────────────────────────────────────────────────────────────
const colorMap = {
  blue: {
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    border: 'border-blue-200 dark:border-blue-800',
    text: 'text-blue-700 dark:text-blue-300',
    badge: 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200',
    accent: 'text-blue-600 dark:text-blue-400',
    ring: 'ring-blue-500',
  },
  purple: {
    bg: 'bg-purple-50 dark:bg-purple-900/20',
    border: 'border-purple-200 dark:border-purple-800',
    text: 'text-purple-700 dark:text-purple-300',
    badge: 'bg-purple-100 dark:bg-purple-900/40 text-purple-800 dark:text-purple-200',
    accent: 'text-purple-600 dark:text-purple-400',
    ring: 'ring-purple-500',
  },
  orange: {
    bg: 'bg-orange-50 dark:bg-orange-900/20',
    border: 'border-orange-200 dark:border-orange-800',
    text: 'text-orange-700 dark:text-orange-300',
    badge: 'bg-orange-100 dark:bg-orange-900/40 text-orange-800 dark:text-orange-200',
    accent: 'text-orange-600 dark:text-orange-400',
    ring: 'ring-orange-500',
  },
};

// ── Sub-Components ─────────────────────────────────────────────────────────────

const SectionHeader = ({ icon, title, color }) => (
  <h3 className={`text-lg font-bold ${color} flex items-center gap-2 mb-3`}>
    <span>{icon}</span> {title}
  </h3>
);

const ChecklistItem = ({ item, index }) => (
  <div className="flex items-start gap-3 py-2">
    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 flex items-center justify-center text-xs font-bold mt-0.5">
      {index + 1}
    </span>
    <div>
      <span className="font-semibold text-gray-900 dark:text-gray-100">{item.label}</span>
      <p className="text-sm text-gray-600 dark:text-gray-400 mt-0.5">{item.detail}</p>
    </div>
  </div>
);

const FilterBadge = ({ label, value }) => (
  <div className="flex items-center gap-2 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
    <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">{label}</span>
    <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{value}</span>
  </div>
);

const ScoreFactor = ({ name, weight }) => (
  <div className="flex items-center justify-between py-1.5">
    <span className="text-sm text-gray-700 dark:text-gray-300">{name}</span>
    <div className="flex gap-1">
      {[...Array(5)].map((_, i) => (
        <div
          key={i}
          className={`w-3 h-3 rounded-sm ${
            i < weight
              ? 'bg-amber-400 dark:bg-amber-500'
              : 'bg-gray-200 dark:bg-gray-700'
          }`}
        />
      ))}
    </div>
  </div>
);

// ── Main Modal ─────────────────────────────────────────────────────────────────

export default function StrategyDetailModal({ strategy, onClose }) {
  const [activeTab, setActiveTab] = useState('overview');
  const data = getBaseStrategy(strategy);
  const direction = getDirection(strategy);

  if (!data) return null;

  const colors = colorMap[data.color] || colorMap.blue;

  const tabs = [
    { id: 'overview', label: 'Overview', icon: '📋' },
    { id: 'mechanics', label: 'Mechanics', icon: '⚙️' },
    { id: 'checklist', label: 'Checklist', icon: '✅' },
    { id: 'example', label: 'Example', icon: '📊' },
  ];

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* ── Header ──────────────────────────────────────────────── */}
        <div className={`${colors.bg} border-b ${colors.border} px-6 py-5`}>
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3">
                <span className="text-3xl">{data.icon}</span>
                <div>
                  <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                    {data.fullName}
                  </h2>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${colors.badge}`}>
                      {data.category}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {data.timeframe}
                    </span>
                    {direction && (
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                        direction === 'long'
                          ? 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200'
                          : 'bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200'
                      }`}>
                        {direction === 'long' ? '📈 LONG' : '📉 SHORT'}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-1 rounded-lg hover:bg-gray-200/50 dark:hover:bg-gray-700/50 transition-colors"
            >
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Description */}
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-3 leading-relaxed">
            {data.description}
          </p>
        </div>

        {/* ── Tab Bar ─────────────────────────────────────────────── */}
        <div className="flex border-b border-gray-200 dark:border-gray-700 px-6 bg-gray-50/50 dark:bg-gray-800/50">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium transition-colors relative ${
                activeTab === tab.id
                  ? `${colors.accent} border-b-2 border-current`
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              <span className="mr-1.5">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        {/* ── Content ─────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {/* OVERVIEW TAB */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* How It Works */}
              <div>
                <SectionHeader icon="🔍" title="How It Works" color={colors.accent} />
                <ol className="space-y-2 ml-1">
                  {data.how_it_works.map((step, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 flex items-center justify-center text-xs font-bold mt-0.5">
                        {i + 1}
                      </span>
                      <span className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{step}</span>
                    </li>
                  ))}
                </ol>
              </div>

              {/* Scoring */}
              <div>
                <SectionHeader icon="🎯" title={data.scoring.title} color={colors.accent} />
                <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
                  {data.scoring.factors.map((f, i) => (
                    <ScoreFactor key={i} name={f.name} weight={f.weight} />
                  ))}
                  <div className="border-t border-gray-200 dark:border-gray-700 mt-2 pt-2 flex items-center justify-between">
                    <span className="text-sm font-bold text-gray-900 dark:text-gray-100">Total</span>
                    <span className="text-sm font-bold text-amber-600 dark:text-amber-400">
                      {data.scoring.factors.reduce((sum, f) => sum + f.weight, 0)} / 10
                    </span>
                  </div>
                </div>
              </div>

              {/* Filters */}
              <div>
                <SectionHeader icon="🔧" title="Quality Filters" color={colors.accent} />
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(data.filters).map(([label, value]) => (
                    <FilterBadge key={label} label={label} value={value} />
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* MECHANICS TAB */}
          {activeTab === 'mechanics' && (
            <div className="space-y-6">
              {/* Entry Rules */}
              <div>
                <SectionHeader icon="🟢" title="Entry Rules" color="text-green-600 dark:text-green-400" />
                <div className="space-y-3">
                  <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs font-bold uppercase text-green-700 dark:text-green-300">📈 Long Entry</span>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300">{data.entry_rules.long}</p>
                  </div>
                  <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs font-bold uppercase text-red-700 dark:text-red-300">📉 Short Entry</span>
                    </div>
                    <p className="text-sm text-gray-700 dark:text-gray-300">{data.entry_rules.short}</p>
                  </div>
                </div>
              </div>

              {/* Stop Rules */}
              <div>
                <SectionHeader icon="🛑" title="Stop Loss" color="text-red-600 dark:text-red-400" />
                <div className="bg-red-50/50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30 rounded-lg p-4">
                  <p className="text-sm text-gray-700 dark:text-gray-300">{data.stop_rules}</p>
                </div>
              </div>

              {/* Target Rules */}
              <div>
                <SectionHeader icon="🎯" title="Targets & Trail" color="text-green-600 dark:text-green-400" />
                <div className="bg-green-50/50 dark:bg-green-900/10 border border-green-100 dark:border-green-900/30 rounded-lg p-4">
                  <p className="text-sm text-gray-700 dark:text-gray-300">{data.target_rules}</p>
                </div>
              </div>

              {/* Risk Management */}
              <div>
                <SectionHeader icon="⚖️" title="Risk Management" color="text-amber-600 dark:text-amber-400" />
                <div className="bg-amber-50/50 dark:bg-amber-900/10 border border-amber-100 dark:border-amber-900/30 rounded-lg p-4">
                  <p className="text-sm text-gray-700 dark:text-gray-300">{data.risk_management}</p>
                </div>
              </div>

              {/* Failure Modes */}
              <div>
                <SectionHeader icon="⚠️" title="Failure Modes (Invalidation)" color="text-red-600 dark:text-red-400" />
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 space-y-2">
                  {data.failure_modes.map((mode, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="text-red-500 mt-0.5 flex-shrink-0">✕</span>
                      <span className="text-sm text-gray-700 dark:text-gray-300">{mode}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* CHECKLIST TAB */}
          {activeTab === 'checklist' && (
            <div className="space-y-6">
              <div>
                <SectionHeader icon="✅" title="Quality Checklist" color={colors.accent} />
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                  All conditions should be met before entering the trade. Each factor contributes to the confluence score.
                </p>
                <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 divide-y divide-gray-200 dark:divide-gray-700">
                  {data.checklist.map((item, i) => (
                    <ChecklistItem key={i} item={item} index={i} />
                  ))}
                </div>
              </div>

              {/* Quick Reference Card */}
              <div className={`${colors.bg} border ${colors.border} rounded-lg p-4`}>
                <h4 className={`text-sm font-bold ${colors.accent} mb-3`}>📌 Quick Reference</h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Min Score:</span>
                    <span className="ml-2 font-semibold text-gray-900 dark:text-gray-100">
                      {data.scoring.factors.reduce((sum, f) => sum + f.weight, 0) * 0.6}/10
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Min R:R:</span>
                    <span className="ml-2 font-semibold text-gray-900 dark:text-gray-100">1.5:1</span>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Timeframe:</span>
                    <span className="ml-2 font-semibold text-gray-900 dark:text-gray-100">{data.timeframe}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 dark:text-gray-400">Category:</span>
                    <span className="ml-2 font-semibold text-gray-900 dark:text-gray-100">{data.category}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* EXAMPLE TAB */}
          {activeTab === 'example' && (
            <div className="space-y-6">
              <div>
                <SectionHeader icon="📊" title={data.example.title} color={colors.accent} />
                <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-5">
                  <div className="space-y-3">
                    {data.example.steps.map((step, i) => (
                      <div key={i} className="flex items-start gap-3">
                        <div className={`flex-shrink-0 w-7 h-7 rounded-lg ${
                          i === data.example.steps.length - 1
                            ? 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400'
                            : i === data.example.steps.length - 2
                              ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
                              : `${colors.bg} ${colors.text}`
                        } flex items-center justify-center text-xs font-bold`}>
                          {i + 1}
                        </div>
                        <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed pt-1">
                          {step}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Strategy Flow Diagram */}
              <div>
                <SectionHeader icon="🔄" title="Trade Flow" color={colors.accent} />
                <div className="flex flex-col items-center gap-2">
                  {[
                    { emoji: '👀', label: 'Identify Setup', detail: data.category },
                    { emoji: '✅', label: 'Check Quality', detail: `${data.checklist.length} checklist items` },
                    { emoji: '🎯', label: 'Score Confluence', detail: '0-10 weighted score' },
                    { emoji: '🟢', label: 'Enter Trade', detail: direction === 'long' ? data.entry_rules.long.split('.')[0] : direction === 'short' ? data.entry_rules.short.split('.')[0] : 'Per entry rules' },
                    { emoji: '📊', label: 'Manage Position', detail: 'TP1 → Breakeven → Trail' },
                  ].map((step, i, arr) => (
                    <div key={i} className="w-full max-w-md">
                      <div className="flex items-center gap-3 bg-gray-50 dark:bg-gray-800 rounded-lg px-4 py-3">
                        <span className="text-xl">{step.emoji}</span>
                        <div className="flex-1">
                          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{step.label}</div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">{step.detail}</div>
                        </div>
                      </div>
                      {i < arr.length - 1 && (
                        <div className="flex justify-center py-1">
                          <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                          </svg>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Footer ──────────────────────────────────────────────── */}
        <div className="border-t border-gray-200 dark:border-gray-700 px-6 py-4 bg-gray-50/50 dark:bg-gray-800/50 flex items-center justify-between">
          <p className="text-xs text-gray-400 dark:text-gray-500 italic">
            Educational reference from Trading Prompt Library. Not financial advice.
          </p>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors text-sm font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
