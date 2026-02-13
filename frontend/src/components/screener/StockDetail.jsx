/**
 * Stock detail modal component with tabbed interface
 */
import { useState } from 'react';
import Card from '../common/Card';
import Button from '../common/Button';
import Tooltip from '../common/Tooltip';
import { formatLargeNumber, formatCurrency, formatScore, getScoreColor, formatPercent, getChangeColor } from '../../utils/formatters';
import { StrategySelector } from '../strategy';
import { SentimentCard } from '../sentiment/SentimentCard';
import { StockChart } from '../charts';
import { ReturnCalculator, PLChart } from '../calculators';
import { MacroOverlay } from '../command-center';
import useThemeStore from '../../stores/themeStore';

const TABS = [
  { id: 'overview', label: 'Overview', icon: '📊' },
  { id: 'chart', label: 'Chart', icon: '📈' },
  { id: 'strategy', label: 'Strategy', icon: '🎯' },
  { id: 'sentiment', label: 'Sentiment', icon: '📰' },
  { id: 'options', label: 'Options', icon: '📑' },
];

export default function StockDetail({ stock, onClose }) {
  const [activeTab, setActiveTab] = useState('overview');
  const { darkMode } = useThemeStore();

  if (!stock) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-white dark:bg-gray-900 rounded-lg max-w-5xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-6 py-4 z-10">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
                {stock.symbol} - {stock.name}
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-400">{stock.sector}</p>
            </div>
            <div className="flex items-center gap-4">
              <div className={`text-3xl font-bold ${getScoreColor(stock.score)}`}>
                {formatScore(stock.score)}
              </div>
              <Button onClick={onClose} variant="secondary">
                Close
              </Button>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="flex space-x-1 border-b dark:border-gray-700 -mb-4">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                  activeTab === tab.id
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 border-b-2 border-blue-600'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800'
                }`}
              >
                <span className="mr-1">{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="p-6">
          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Macro Overlay - Shows macro context for this ticker */}
              <MacroOverlay
                symbol={stock.symbol}
                sector={stock.sector}
                compact={false}
              />

              {/* Score Overview */}
              <Card title="📊 Composite Score">
                <p className="text-xs text-gray-500 dark:text-gray-500 mb-3">
                  A single at-a-glance rating that blends multiple signals into one number. Higher is better. Hover each component for details.
                  <span className="ml-2 font-medium">80-100: Top tier | 60-79: Solid | 0-59: Needs caution</span>
                </p>
                <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                  <Tooltip text="Overall (0-100): Your final weighted score across all components. Use it to compare stocks side-by-side and spot the top tier quickly. Tip: two stocks can have the same Overall score for different reasons — hover each component to see what's driving it.">
                    <div className="text-center cursor-help">
                      <div className={`text-4xl font-bold ${getScoreColor(stock.score)}`}>
                        {formatScore(stock.score)}
                      </div>
                      <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">Overall</div>
                    </div>
                  </Tooltip>
                  <Tooltip text="Fundamental (35%) — Company Quality: Measures business strength — growth, profitability, balance-sheet health, and return on equity. High = strong growth + healthy margins + reasonable leverage. Best for: Is this a strong company worth owning for 1-2 years?">
                    <div className="text-center cursor-help">
                      <div className={`text-2xl font-bold ${getScoreColor(stock.fundamental_score)}`}>
                        {formatScore(stock.fundamental_score)}
                      </div>
                      <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">Fundamental (35%)</div>
                    </div>
                  </Tooltip>
                  <Tooltip text="Technical (25%) — Trend & Setup Strength: Measures price/indicator confirmation — trend alignment, RSI, MACD momentum, volume, and breakout behavior. High = clear uptrend with supportive momentum/volume. Best for: Is the chart aligned with the thesis right now?">
                    <div className="text-center cursor-help">
                      <div className={`text-2xl font-bold ${getScoreColor(stock.technical_score)}`}>
                        {formatScore(stock.technical_score)}
                      </div>
                      <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">Technical (25%)</div>
                    </div>
                  </Tooltip>
                  <Tooltip text="Options (15%) — LEAPS Trade Quality: Measures whether the LEAPS opportunity is practical — IV level, liquidity, bid-ask spread, and premium efficiency. High = liquid chain, tight spreads, reasonable premium. Best for: Can I enter/exit this trade efficiently?">
                    <div className="text-center cursor-help">
                      <div className={`text-2xl font-bold ${getScoreColor(stock.options_score)}`}>
                        {formatScore(stock.options_score)}
                      </div>
                      <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">Options (15%)</div>
                    </div>
                  </Tooltip>
                  <Tooltip text="Momentum (10%) — Recent Performance & Drawdown Context: Measures returns across 1M/3M/1Y windows and penalizes sharp drawdowns. High = strong recent returns with healthy trend. Best for: Is this name currently accelerating or fading?">
                    <div className="text-center cursor-help">
                      <div className={`text-2xl font-bold ${getScoreColor(stock.momentum_score)}`}>
                        {formatScore(stock.momentum_score)}
                      </div>
                      <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">Momentum (10%)</div>
                    </div>
                  </Tooltip>
                </div>
              </Card>

              {/* Key Metrics */}
              <Card title="💰 Key Metrics">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">Current Price</div>
                    <div className="text-lg font-bold text-gray-800 dark:text-white">
                      {formatCurrency(stock.current_price)}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">Market Cap</div>
                    <div className="text-lg font-bold text-gray-800 dark:text-white">
                      {formatLargeNumber(stock.market_cap)}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">RSI (14)</div>
                    <div className="text-lg font-bold text-gray-800 dark:text-white">
                      {stock.technical_indicators?.rsi_14?.toFixed(2) || 'N/A'}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">ADX (14)</div>
                    <div className="text-lg font-bold text-gray-800 dark:text-white">
                      {stock.technical_indicators?.adx_14?.toFixed(2) || 'N/A'}
                    </div>
                  </div>
                </div>
              </Card>

              {/* Returns */}
              {stock.returns && (
                <Card title="📈 Returns">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {stock.returns.return_1m !== undefined && (
                      <div>
                        <div className="text-sm text-gray-600 dark:text-gray-400">1 Month</div>
                        <div className={`text-lg font-bold ${getChangeColor(stock.returns.return_1m)}`}>
                          {formatPercent(stock.returns.return_1m)}
                        </div>
                      </div>
                    )}
                    {stock.returns.return_3m !== undefined && (
                      <div>
                        <div className="text-sm text-gray-600 dark:text-gray-400">3 Months</div>
                        <div className={`text-lg font-bold ${getChangeColor(stock.returns.return_3m)}`}>
                          {formatPercent(stock.returns.return_3m)}
                        </div>
                      </div>
                    )}
                    {stock.returns.return_6m !== undefined && (
                      <div>
                        <div className="text-sm text-gray-600 dark:text-gray-400">6 Months</div>
                        <div className={`text-lg font-bold ${getChangeColor(stock.returns.return_6m)}`}>
                          {formatPercent(stock.returns.return_6m)}
                        </div>
                      </div>
                    )}
                    {stock.returns.return_1y !== undefined && (
                      <div>
                        <div className="text-sm text-gray-600 dark:text-gray-400">1 Year</div>
                        <div className={`text-lg font-bold ${getChangeColor(stock.returns.return_1y)}`}>
                          {formatPercent(stock.returns.return_1y)}
                        </div>
                      </div>
                    )}
                  </div>
                </Card>
              )}

              {/* Fundamental Criteria */}
              {stock.fundamental_criteria && (
                <Card title="📋 Fundamental Criteria">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {Object.entries(stock.fundamental_criteria).map(([key, value]) => (
                      <div key={key} className="flex items-center gap-2">
                        <span className={`text-lg ${value ? 'text-green-600' : 'text-red-600'}`}>
                          {value ? '✅' : '❌'}
                        </span>
                        <span className="text-sm text-gray-700 dark:text-gray-300">
                          {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Technical Criteria */}
              {stock.technical_criteria && (
                <Card title="📊 Technical Criteria">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {Object.entries(stock.technical_criteria).map(([key, value]) => (
                      <div key={key} className="flex items-center gap-2">
                        <span className={`text-lg ${value ? 'text-green-600' : 'text-red-600'}`}>
                          {value ? '✅' : '❌'}
                        </span>
                        <span className="text-sm text-gray-700 dark:text-gray-300">
                          {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </div>
          )}

          {/* Chart Tab */}
          {activeTab === 'chart' && (
            <div className="space-y-4">
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
                <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="font-semibold text-gray-900 dark:text-white">
                    {stock.symbol} - Interactive Chart
                  </h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Powered by TradingView. Use toolbar for indicators and drawing tools.
                  </p>
                </div>
                <StockChart
                  symbol={stock.symbol}
                  exchange={stock.exchange}
                  height={500}
                  theme={darkMode ? 'dark' : 'light'}
                  interval="D"
                  showToolbar={true}
                />
              </div>
              <p className="text-xs text-gray-400 text-center">
                Chart data provided by TradingView. For informational purposes only.
              </p>
            </div>
          )}

          {/* Strategy Tab */}
          {activeTab === 'strategy' && (
            <StrategySelector
              symbol={stock.symbol}
              stockData={stock}
            />
          )}

          {/* Sentiment Tab */}
          {activeTab === 'sentiment' && (
            <SentimentCard
              symbol={stock.symbol}
              companyName={stock.name}
              showNews={true}
              showInsiders={true}
              showCatalysts={true}
            />
          )}

          {/* Options Tab */}
          {activeTab === 'options' && (
            <div className="space-y-6">
              {/* Options Criteria */}
              {stock.options_criteria && (
                <Card title="Options Criteria">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {Object.entries(stock.options_criteria).map(([key, value]) => (
                      <div key={key} className="flex items-center gap-2">
                        <span className={`text-lg ${value ? 'text-green-600' : 'text-red-600'}`}>
                          {value ? '✓' : '✗'}
                        </span>
                        <span className="text-sm text-gray-700 dark:text-gray-300">
                          {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* LEAPS Summary */}
              {stock.leaps_summary?.atm_option && (
                <Card title="LEAPS Option Details">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">Strike Price</div>
                      <div className="text-lg font-bold text-gray-800 dark:text-white">
                        {formatCurrency(stock.leaps_summary.atm_option.strike)}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">Premium</div>
                      <div className="text-lg font-bold text-gray-800 dark:text-white">
                        {formatCurrency(stock.leaps_summary.atm_option.last_price)}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">Open Interest</div>
                      <div className="text-lg font-bold text-gray-800 dark:text-white">
                        {stock.leaps_summary.atm_option.open_interest?.toLocaleString() || 'N/A'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">Implied Volatility</div>
                      <div className="text-lg font-bold text-gray-800 dark:text-white">
                        {formatPercent(stock.leaps_summary.atm_option.implied_volatility)}
                      </div>
                    </div>
                  </div>
                </Card>
              )}

              {/* IV Rank */}
              {stock.leaps_summary?.iv_rank !== undefined && (
                <Card title="Implied Volatility Analysis">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    <div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">IV Rank</div>
                      <div className={`text-2xl font-bold ${
                        stock.leaps_summary.iv_rank < 30 ? 'text-green-600' :
                        stock.leaps_summary.iv_rank > 70 ? 'text-red-600' : 'text-yellow-600'
                      }`}>
                        {stock.leaps_summary.iv_rank?.toFixed(1)}%
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {stock.leaps_summary.iv_rank < 30 ? 'Low (Cheap options)' :
                         stock.leaps_summary.iv_rank > 70 ? 'High (Expensive options)' : 'Normal'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">Days to Expiration</div>
                      <div className="text-2xl font-bold text-gray-800 dark:text-white">
                        {stock.leaps_summary.atm_option?.days_to_expiration || 'N/A'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 dark:text-gray-400">Expiration Date</div>
                      <div className="text-lg font-bold text-gray-800 dark:text-white">
                        {stock.leaps_summary.expiration_date || 'N/A'}
                      </div>
                    </div>
                  </div>
                </Card>
              )}

              {/* 5x Return Calculator - NEW */}
              {stock.leaps_summary?.atm_option && stock.current_price && (
                <ReturnCalculator
                  currentPrice={stock.current_price}
                  strike={stock.leaps_summary.atm_option.strike}
                  premium={stock.leaps_summary.atm_option.last_price}
                  dte={stock.leaps_summary.atm_option.days_to_expiration || 400}
                  symbol={stock.symbol}
                />
              )}

              {/* P/L Chart - NEW */}
              {stock.leaps_summary?.atm_option && stock.current_price && (
                <PLChart
                  strike={stock.leaps_summary.atm_option.strike}
                  premium={stock.leaps_summary.atm_option.last_price}
                  currentPrice={stock.current_price}
                  symbol={stock.symbol}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
