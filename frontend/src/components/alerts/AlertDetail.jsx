/**
 * AlertDetail Component
 * Shows full details for an alert, including fetched stock data
 * Supports both webhook alerts and LEAPS Trader dynamic alert notifications
 */
import { useState, useEffect } from 'react';
import Card from '../common/Card';
import Button from '../common/Button';
import Tooltip from '../common/Tooltip';
import { formatCurrency, formatDateTime, formatPercent, getChangeColor } from '../../utils/formatters';
import { screenSingleStock } from '../../api/screener';
import { StockChart } from '../charts';
import { SentimentCard } from '../sentiment/SentimentCard';

// Alert type display config
const ALERT_TYPE_CONFIG = {
  iv_rank_below: { icon: '📉', label: 'IV Rank Below', unit: '%' },
  iv_rank_above: { icon: '📈', label: 'IV Rank Above', unit: '%' },
  price_above: { icon: '⬆️', label: 'Price Above', unit: '$' },
  price_below: { icon: '⬇️', label: 'Price Below', unit: '$' },
  rsi_oversold: { icon: '🔻', label: 'RSI Oversold', unit: '' },
  rsi_overbought: { icon: '🔺', label: 'RSI Overbought', unit: '' },
  price_cross_sma: { icon: '📊', label: 'Price Cross SMA', unit: '' },
  earnings_approaching: { icon: '📅', label: 'Earnings Approaching', unit: ' days' },
  screening_match: { icon: '✅', label: 'Screening Match', unit: '' },
  leaps_available: { icon: '🎯', label: 'LEAPS Available', unit: '' },
};

export default function AlertDetail({ alert, onClose }) {
  const [stockData, setStockData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('alert');

  // Check if this is a LEAPS Trader notification
  const isLeapsTraderNotification = alert?.provider === 'LEAPS Trader' || alert?._isNotification;

  // Fetch stock data when alert is opened
  useEffect(() => {
    if (alert?.symbol) {
      fetchStockData();
    }
  }, [alert?.symbol]);

  const fetchStockData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Screen the single stock to get full analysis
      const data = await screenSingleStock(alert.symbol);
      setStockData(data);
    } catch (err) {
      console.error('Error fetching stock data:', err);
      setError('Failed to fetch stock analysis. The symbol may not be available for screening.');
    } finally {
      setLoading(false);
    }
  };

  if (!alert) return null;

  // Extract fields based on alert type
  const {
    symbol,
    direction,
    event_type,
    entry_zone,
    stop_loss,
    tp1,
    tp2,
    current_price,
    alert_timestamp,
    received_at,
    status,
    provider,
    setup_id,
    // LEAPS Trader notification fields
    alert_name,
    alert_type,
    threshold_value,
    triggered_value,
    message,
    triggered_at,
    is_read,
    channels_sent,
  } = alert;

  // Calculate potential returns
  const calculateReturns = () => {
    if (!entry_zone || entry_zone.length < 2) return null;

    const entryMid = (entry_zone[0] + entry_zone[1]) / 2;
    const riskAmount = Math.abs(entryMid - stop_loss);
    const tp1Return = Math.abs(tp1 - entryMid);
    const tp2Return = Math.abs(tp2 - entryMid);

    return {
      entry: entryMid,
      riskPercent: ((riskAmount / entryMid) * 100).toFixed(2),
      tp1Percent: ((tp1Return / entryMid) * 100).toFixed(2),
      tp2Percent: ((tp2Return / entryMid) * 100).toFixed(2),
      riskReward1: (tp1Return / riskAmount).toFixed(2),
      riskReward2: (tp2Return / riskAmount).toFixed(2),
    };
  };

  const returns = calculateReturns();

  const TABS = [
    { id: 'alert', label: isLeapsTraderNotification ? 'Notification Details' : 'Alert Details', icon: '🔔' },
    { id: 'chart', label: 'Chart', icon: '📈' },
    { id: 'analysis', label: 'Stock Analysis', icon: '📊' },
    { id: 'sentiment', label: 'Sentiment', icon: '📰' },
  ];

  // Get alert type config for LEAPS Trader notifications
  const alertTypeConfig = ALERT_TYPE_CONFIG[alert_type] || { icon: '🔔', label: alert_type, unit: '' };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-white rounded-lg max-w-5xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 z-10">
          <div className="flex justify-between items-center mb-4">
            <div>
              {isLeapsTraderNotification ? (
                /* LEAPS Trader Notification Header */
                <>
                  <h2 className="text-2xl font-bold text-gray-800 flex items-center gap-3">
                    <span className="text-2xl">{alertTypeConfig.icon}</span>
                    {alert_name || 'Alert Notification'}
                    <span className="font-bold text-blue-600">{symbol}</span>
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      is_read ? 'bg-gray-100 text-gray-600' : 'bg-blue-100 text-blue-800'
                    }`}>
                      {is_read ? 'Read' : 'Unread'}
                    </span>
                  </h2>
                  <p className="text-sm text-gray-600 mt-1">
                    Provider: LEAPS Trader | Type: {alertTypeConfig.label}
                    {channels_sent?.length > 0 && ` | Sent via: ${channels_sent.join(', ')}`}
                  </p>
                </>
              ) : (
                /* Webhook Alert Header */
                <>
                  <h2 className="text-2xl font-bold text-gray-800 flex items-center gap-3">
                    {symbol}
                    <span className={`px-3 py-1 rounded-full text-sm font-semibold uppercase ${
                      direction === 'buy' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
                    }`}>
                      {direction}
                    </span>
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      event_type === 'new_setup' ? 'bg-purple-100 text-purple-800' : 'bg-orange-100 text-orange-800'
                    }`}>
                      {event_type === 'new_setup' ? '🆕 New Setup' : '🎯 Triggered'}
                    </span>
                  </h2>
                  <p className="text-sm text-gray-600">
                    Provider: {provider} | Setup ID: {setup_id} | Status: <span className={`font-medium ${
                      status === 'active' ? 'text-green-600' :
                      status === 'triggered' ? 'text-blue-600' :
                      status === 'expired' ? 'text-gray-500' : 'text-red-600'
                    }`}>{status}</span>
                  </p>
                </>
              )}
            </div>
            <Button onClick={onClose} variant="secondary">
              Close
            </Button>
          </div>

          {/* Tab Navigation */}
          <div className="flex space-x-1 border-b -mb-4">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                  activeTab === tab.id
                    ? 'bg-blue-50 text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                }`}
              >
                <span className="mr-1">{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="p-6">
          {/* Alert Details Tab */}
          {activeTab === 'alert' && (
            <div className="space-y-6">
              {isLeapsTraderNotification ? (
                /* LEAPS Trader Notification Details */
                <>
                  {/* Alert Message */}
                  <Card title={`${alertTypeConfig.icon} Alert Triggered`}>
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                      <p className="text-lg text-blue-900">{message}</p>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                      <div className="text-center p-4 bg-gray-50 rounded-lg">
                        <div className="text-sm text-gray-500 uppercase font-medium">Symbol</div>
                        <div className="text-2xl font-bold text-blue-600">{symbol}</div>
                      </div>
                      <div className="text-center p-4 bg-purple-50 rounded-lg">
                        <div className="text-sm text-purple-600 uppercase font-medium">Alert Type</div>
                        <div className="text-xl font-bold text-purple-700">{alertTypeConfig.label}</div>
                      </div>
                      <div className="text-center p-4 bg-orange-50 rounded-lg">
                        <div className="text-sm text-orange-600 uppercase font-medium">Threshold</div>
                        <div className="text-xl font-bold text-orange-700">
                          {alertTypeConfig.unit === '$' ? formatCurrency(threshold_value) : `${threshold_value}${alertTypeConfig.unit}`}
                        </div>
                      </div>
                      <div className="text-center p-4 bg-green-50 rounded-lg">
                        <div className="text-sm text-green-600 uppercase font-medium">Triggered Value</div>
                        <div className="text-xl font-bold text-green-700">
                          {alertTypeConfig.unit === '$' ? formatCurrency(triggered_value) :
                           triggered_value !== null ? `${typeof triggered_value === 'number' ? triggered_value.toFixed(2) : triggered_value}${alertTypeConfig.unit}` : 'N/A'}
                        </div>
                      </div>
                    </div>
                  </Card>

                  {/* Notification Details */}
                  <Card title="📋 Notification Details">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="text-sm text-gray-500">Triggered At</div>
                        <div className="text-lg font-medium text-gray-900">{formatDateTime(triggered_at)}</div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-500">Notification Channels</div>
                        <div className="text-lg font-medium text-gray-900">
                          {channels_sent?.length > 0 ? channels_sent.map(ch => (
                            <span key={ch} className="inline-flex items-center px-2 py-1 rounded bg-gray-100 text-gray-700 text-sm mr-2">
                              {ch === 'telegram' && '📱 '}
                              {ch === 'app' && '🔔 '}
                              {ch}
                            </span>
                          )) : 'None'}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-500">Status</div>
                        <div className={`text-lg font-medium ${is_read ? 'text-gray-600' : 'text-blue-600'}`}>
                          {is_read ? 'Read' : 'Unread'}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-500">Alert Name</div>
                        <div className="text-lg font-medium text-gray-900">{alert_name || 'N/A'}</div>
                      </div>
                    </div>
                  </Card>

                  {/* Current Stock Price (if available from stockData) */}
                  {stockData && (
                    <Card title="💰 Current Market Data">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                          <div className="text-sm text-gray-500">Current Price</div>
                          <div className="text-xl font-bold text-gray-900">{formatCurrency(stockData.current_price)}</div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-500">Market Cap</div>
                          <div className="text-lg font-bold text-gray-800">
                            {stockData.market_cap ? `$${(stockData.market_cap / 1e9).toFixed(2)}B` : 'N/A'}
                          </div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-500">Sector</div>
                          <div className="text-lg font-bold text-gray-800">{stockData.sector || 'N/A'}</div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-500">RSI (14)</div>
                          <div className="text-lg font-bold text-gray-800">
                            {stockData.technical_indicators?.rsi_14?.toFixed(2) || 'N/A'}
                          </div>
                        </div>
                      </div>
                    </Card>
                  )}
                </>
              ) : (
                /* Webhook Alert Details (original) */
                <>
                  {/* Trade Setup */}
                  <Card title="🎯 Trade Setup">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                      <div className="text-center p-4 bg-gray-50 rounded-lg">
                        <div className="text-sm text-gray-500 uppercase font-medium">Current Price</div>
                        <div className="text-2xl font-bold text-gray-900">{formatCurrency(current_price)}</div>
                      </div>
                      <div className="text-center p-4 bg-blue-50 rounded-lg">
                        <div className="text-sm text-blue-600 uppercase font-medium">Entry Zone</div>
                        <div className="text-xl font-bold text-blue-700">
                          {entry_zone ? `${formatCurrency(entry_zone[0])} - ${formatCurrency(entry_zone[1])}` : 'N/A'}
                        </div>
                      </div>
                      <div className="text-center p-4 bg-red-50 rounded-lg">
                        <div className="text-sm text-red-600 uppercase font-medium">Stop Loss</div>
                        <div className="text-xl font-bold text-red-700">{formatCurrency(stop_loss)}</div>
                        {returns && (
                          <div className="text-xs text-red-500 mt-1">-{returns.riskPercent}% risk</div>
                        )}
                      </div>
                      <div className="text-center p-4 bg-green-50 rounded-lg">
                        <div className="text-sm text-green-600 uppercase font-medium">Take Profit 1</div>
                        <div className="text-xl font-bold text-green-700">{formatCurrency(tp1)}</div>
                        {returns && (
                          <div className="text-xs text-green-500 mt-1">+{returns.tp1Percent}%</div>
                        )}
                      </div>
                    </div>

                    {/* TP2 and Risk/Reward */}
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-6 mt-4">
                      <div className="text-center p-4 bg-green-100 rounded-lg">
                        <div className="text-sm text-green-700 uppercase font-medium">Take Profit 2</div>
                        <div className="text-xl font-bold text-green-800">{formatCurrency(tp2)}</div>
                        {returns && (
                          <div className="text-xs text-green-600 mt-1">+{returns.tp2Percent}%</div>
                        )}
                      </div>
                      {returns && (
                        <>
                          <div className="text-center p-4 bg-purple-50 rounded-lg">
                            <div className="text-sm text-purple-600 uppercase font-medium">R:R to TP1</div>
                            <div className="text-xl font-bold text-purple-700">1:{returns.riskReward1}</div>
                          </div>
                          <div className="text-center p-4 bg-purple-100 rounded-lg">
                            <div className="text-sm text-purple-700 uppercase font-medium">R:R to TP2</div>
                            <div className="text-xl font-bold text-purple-800">1:{returns.riskReward2}</div>
                          </div>
                        </>
                      )}
                    </div>
                  </Card>

                  {/* Position Sizing Calculator */}
                  {returns && (
                    <Card title="📐 Position Sizing Guide">
                      <div className="text-sm text-gray-600 mb-4">
                        Based on your risk per trade, here's the suggested position size:
                      </div>
                      <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Account Risk</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">For $10K Account</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">For $25K Account</th>
                              <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">For $50K Account</th>
                            </tr>
                          </thead>
                          <tbody className="bg-white divide-y divide-gray-200">
                            {[1, 2, 3].map((riskPct) => {
                              const riskPerUnit = returns.entry * (returns.riskPercent / 100);
                              return (
                                <tr key={riskPct}>
                                  <td className="px-4 py-2 font-medium">{riskPct}% Risk</td>
                                  <td className="px-4 py-2">{Math.floor((10000 * riskPct / 100) / riskPerUnit)} units</td>
                                  <td className="px-4 py-2">{Math.floor((25000 * riskPct / 100) / riskPerUnit)} units</td>
                                  <td className="px-4 py-2">{Math.floor((50000 * riskPct / 100) / riskPerUnit)} units</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </Card>
                  )}

                  {/* Timestamps */}
                  <Card title="⏰ Timing">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="text-sm text-gray-500">Alert Generated</div>
                        <div className="text-lg font-medium text-gray-900">{formatDateTime(alert_timestamp)}</div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-500">Received by System</div>
                        <div className="text-lg font-medium text-gray-900">{formatDateTime(received_at)}</div>
                      </div>
                    </div>
                  </Card>
                </>
              )}
            </div>
          )}

          {/* Chart Tab */}
          {activeTab === 'chart' && (
            <div className="space-y-4">
              <div className="bg-white rounded-lg border shadow-sm overflow-hidden">
                <div className="px-4 py-3 bg-gray-50 border-b">
                  <h3 className="font-semibold text-gray-900">
                    {symbol} - Interactive Chart
                  </h3>
                  <p className="text-sm text-gray-500">
                    Entry: {entry_zone ? `${formatCurrency(entry_zone[0])} - ${formatCurrency(entry_zone[1])}` : 'N/A'} |
                    SL: {formatCurrency(stop_loss)} |
                    TP1: {formatCurrency(tp1)} |
                    TP2: {formatCurrency(tp2)}
                  </p>
                </div>
                <StockChart
                  symbol={symbol}
                  height={500}
                  theme="light"
                  interval="D"
                  showToolbar={true}
                />
              </div>
            </div>
          )}

          {/* Stock Analysis Tab */}
          {activeTab === 'analysis' && (
            <div className="space-y-6">
              {loading && (
                <div className="text-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                  <p className="text-gray-600">Analyzing {symbol}...</p>
                </div>
              )}

              {error && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                  <p className="text-yellow-800">{error}</p>
                  <button
                    onClick={fetchStockData}
                    className="mt-2 text-yellow-600 hover:text-yellow-800 underline"
                  >
                    Try again
                  </button>
                </div>
              )}

              {stockData && !loading && (
                <>
                  {/* Score Overview */}
                  <Card title="📊 Screening Score">
                    <p className="text-xs text-gray-500 mb-3">
                      A single at-a-glance rating that blends multiple signals into one number. Hover each component for details.
                      <span className="ml-2 font-medium">80-100: Top tier | 60-79: Solid | 0-59: Needs caution</span>
                    </p>
                    <div className="grid grid-cols-5 gap-4">
                      <Tooltip text="Overall (0-100): Your final weighted score across all components. Use it to compare stocks side-by-side and spot the top tier quickly. Tip: two stocks can have the same Overall score for different reasons — hover each component to see what's driving it.">
                        <div className="text-center cursor-help">
                          <div className={`text-3xl font-bold ${
                            stockData.score >= 70 ? 'text-green-600' :
                            stockData.score >= 50 ? 'text-yellow-600' : 'text-red-600'
                          }`}>
                            {stockData.score?.toFixed(1) || 'N/A'}
                          </div>
                          <div className="text-sm text-gray-600">Overall</div>
                        </div>
                      </Tooltip>
                      <Tooltip text="Fundamental (35%) — Company Quality: Measures business strength — growth, profitability, balance-sheet health, and return on equity. Best for: Is this a strong company worth owning for 1-2 years?">
                        <div className="text-center cursor-help">
                          <div className="text-xl font-bold text-gray-800">
                            {stockData.fundamental_score?.toFixed(1) || 'N/A'}
                          </div>
                          <div className="text-sm text-gray-600">Fundamental (35%)</div>
                        </div>
                      </Tooltip>
                      <Tooltip text="Technical (25%) — Trend & Setup Strength: Measures price/indicator confirmation — trend alignment, RSI, MACD momentum, volume, and breakout behavior. Best for: Is the chart aligned with the thesis right now?">
                        <div className="text-center cursor-help">
                          <div className="text-xl font-bold text-gray-800">
                            {stockData.technical_score?.toFixed(1) || 'N/A'}
                          </div>
                          <div className="text-sm text-gray-600">Technical (25%)</div>
                        </div>
                      </Tooltip>
                      <Tooltip text="Options (15%) — LEAPS Trade Quality: Measures whether the LEAPS opportunity is practical — IV level, liquidity, bid-ask spread, and premium efficiency. Best for: Can I enter/exit this trade efficiently?">
                        <div className="text-center cursor-help">
                          <div className="text-xl font-bold text-gray-800">
                            {stockData.options_score?.toFixed(1) || 'N/A'}
                          </div>
                          <div className="text-sm text-gray-600">Options (15%)</div>
                        </div>
                      </Tooltip>
                      <Tooltip text="Momentum (10%) — Recent Performance & Drawdown Context: Measures returns across 1M/3M/1Y windows and penalizes sharp drawdowns. Best for: Is this name currently accelerating or fading?">
                        <div className="text-center cursor-help">
                          <div className="text-xl font-bold text-gray-800">
                            {stockData.momentum_score?.toFixed(1) || 'N/A'}
                          </div>
                          <div className="text-sm text-gray-600">Momentum (10%)</div>
                        </div>
                      </Tooltip>
                    </div>
                  </Card>

                  {/* Key Metrics */}
                  <Card title="💰 Key Metrics">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div>
                        <div className="text-sm text-gray-600">Current Price</div>
                        <div className="text-lg font-bold text-gray-800">
                          {formatCurrency(stockData.current_price)}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-600">Market Cap</div>
                        <div className="text-lg font-bold text-gray-800">
                          {stockData.market_cap ? `$${(stockData.market_cap / 1e9).toFixed(2)}B` : 'N/A'}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-600">RSI (14)</div>
                        <div className="text-lg font-bold text-gray-800">
                          {stockData.technical_indicators?.rsi_14?.toFixed(2) || 'N/A'}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-600">Sector</div>
                        <div className="text-lg font-bold text-gray-800">
                          {stockData.sector || 'N/A'}
                        </div>
                      </div>
                    </div>
                  </Card>

                  {/* Returns */}
                  {stockData.returns && (
                    <Card title="📈 Historical Returns">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {stockData.returns.return_1m !== undefined && (
                          <div>
                            <div className="text-sm text-gray-600">1 Month</div>
                            <div className={`text-lg font-bold ${getChangeColor(stockData.returns.return_1m)}`}>
                              {formatPercent(stockData.returns.return_1m)}
                            </div>
                          </div>
                        )}
                        {stockData.returns.return_3m !== undefined && (
                          <div>
                            <div className="text-sm text-gray-600">3 Months</div>
                            <div className={`text-lg font-bold ${getChangeColor(stockData.returns.return_3m)}`}>
                              {formatPercent(stockData.returns.return_3m)}
                            </div>
                          </div>
                        )}
                        {stockData.returns.return_6m !== undefined && (
                          <div>
                            <div className="text-sm text-gray-600">6 Months</div>
                            <div className={`text-lg font-bold ${getChangeColor(stockData.returns.return_6m)}`}>
                              {formatPercent(stockData.returns.return_6m)}
                            </div>
                          </div>
                        )}
                        {stockData.returns.return_1y !== undefined && (
                          <div>
                            <div className="text-sm text-gray-600">1 Year</div>
                            <div className={`text-lg font-bold ${getChangeColor(stockData.returns.return_1y)}`}>
                              {formatPercent(stockData.returns.return_1y)}
                            </div>
                          </div>
                        )}
                      </div>
                    </Card>
                  )}
                </>
              )}

              {!stockData && !loading && !error && (
                <div className="text-center py-12">
                  <button
                    onClick={fetchStockData}
                    className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Load Stock Analysis
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Sentiment Tab */}
          {activeTab === 'sentiment' && (
            <SentimentCard
              symbol={symbol}
              companyName={stockData?.name || symbol}
              showNews={true}
              showInsiders={true}
              showCatalysts={true}
            />
          )}
        </div>
      </div>
    </div>
  );
}
