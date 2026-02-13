/**
 * Signal Detail Modal
 * Comprehensive signal breakdown per SignalAlert.md format
 * Now includes AI Deep Analysis panel (Trading Prompt Library)
 */
import { useState, useEffect } from 'react';
import useSignalsStore from '../../stores/signalsStore';
import tradingAPI from '../../api/trading';
import { aiAPI } from '../../api/ai';
import TradeExecutionModal from './TradeExecutionModal';
import PositionCard from './PositionCard';

// Direction badge component
const DirectionBadge = ({ direction }) => {
  const isBuy = direction === 'buy';
  return (
    <span className={`px-3 py-1 rounded-full text-sm font-bold ${
      isBuy ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
    }`}>
      {isBuy ? '\u{1F4C8} LONG' : '\u{1F4C9} SHORT'}
    </span>
  );
};

// Confidence meter component
const ConfidenceMeter = ({ score }) => {
  const getColor = () => {
    if (score >= 75) return 'bg-green-500';
    if (score >= 50) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-3 bg-gray-200 rounded-full overflow-hidden">
        <div
          className={`h-full ${getColor()} transition-all duration-500`}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className={`font-bold text-lg ${
        score >= 75 ? 'text-green-600' : score >= 50 ? 'text-yellow-600' : 'text-red-600'
      }`}>
        {score?.toFixed(0)}%
      </span>
    </div>
  );
};

// Info card for grouped data
const InfoCard = ({ title, children, className = '' }) => (
  <div className={`bg-gray-50 rounded-lg p-4 ${className}`}>
    <h4 className="text-sm font-semibold text-gray-500 uppercase mb-3">{title}</h4>
    {children}
  </div>
);

// Price row component
const PriceRow = ({ label, value, color = 'text-gray-900', prefix = '$' }) => (
  <div className="flex justify-between items-center py-1">
    <span className="text-gray-600">{label}</span>
    <span className={`font-semibold ${color}`}>
      {value ? `${prefix}${value.toFixed(2)}` : '-'}
    </span>
  </div>
);

// =============================================================================
// AI DEEP ANALYSIS PANEL
// =============================================================================

const ConvictionBadge = ({ conviction }) => {
  const getStyle = () => {
    if (conviction >= 8) return 'bg-green-100 text-green-700 border-green-300';
    if (conviction >= 6) return 'bg-yellow-100 text-yellow-700 border-yellow-300';
    if (conviction >= 4) return 'bg-orange-100 text-orange-700 border-orange-300';
    return 'bg-red-100 text-red-700 border-red-300';
  };

  return (
    <span className={`inline-flex items-center px-3 py-1.5 rounded-full text-lg font-bold border ${getStyle()}`}>
      {conviction}/10
    </span>
  );
};

const ActionPill = ({ action }) => {
  const styles = {
    enter_now: 'bg-green-600 text-white',
    wait_for_pullback: 'bg-yellow-500 text-white',
    wait_for_trigger: 'bg-yellow-500 text-white',
    wait_for_stabilization: 'bg-yellow-500 text-white',
    skip: 'bg-red-500 text-white',
  };

  const labels = {
    enter_now: 'Enter Now',
    wait_for_pullback: 'Wait for Pullback',
    wait_for_trigger: 'Wait for Trigger',
    wait_for_stabilization: 'Wait for Stabilization',
    skip: 'Skip',
  };

  return (
    <span className={`px-3 py-1.5 rounded-full text-sm font-bold ${styles[action] || 'bg-gray-500 text-white'}`}>
      {labels[action] || action}
    </span>
  );
};

const ChecklistItem = ({ label, passed }) => (
  <div className="flex items-center gap-2">
    <span className={passed ? 'text-green-500' : 'text-red-400'}>{passed ? '\u2705' : '\u274C'}</span>
    <span className={`text-sm ${passed ? 'text-gray-700' : 'text-gray-500'}`}>{label}</span>
  </div>
);

const AIDeepAnalysisPanel = ({ signalId }) => {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);

  const fetchAnalysis = async () => {
    if (analysis) {
      setExpanded(!expanded);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await aiAPI.analyzeSignal(signalId);
      setAnalysis(data);
      setExpanded(true);
    } catch (err) {
      console.error('AI Deep Analysis error:', err);
      const detail = err.response?.data?.detail;
      if (detail?.includes('Budget exceeded') || detail?.includes('budget')) {
        setError('AI budget exceeded for today. Try again tomorrow.');
      } else {
        setError(detail || err.message || 'Failed to run AI analysis');
      }
    } finally {
      setLoading(false);
    }
  };

  // Friendly checklist labels
  const checklistLabels = {
    trend_aligned: 'Trend Aligned',
    volume_confirmed: 'Volume Confirmed',
    vwap_supportive: 'VWAP Supportive',
    room_to_target: 'Room to Target',
    no_event_risk: 'No Event Risk',
    extended_from_mean: 'Extended From Mean',
    stabilization_signal: 'Stabilization Signal',
    no_trend_day: 'No Trend Day (Range)',
    iv_context_favorable: 'IV Context Favorable',
    no_binary_event: 'No Binary Event',
  };

  return (
    <div className="border border-indigo-200 rounded-xl overflow-hidden">
      {/* Toggle Button */}
      <button
        onClick={fetchAnalysis}
        disabled={loading}
        className="w-full px-5 py-3 flex items-center justify-between bg-gradient-to-r from-indigo-50 to-purple-50 hover:from-indigo-100 hover:to-purple-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-lg">{loading ? '\u23F3' : '\u{1F9E0}'}</span>
          <span className="font-semibold text-indigo-700">
            {loading ? 'Analyzing with Claude AI...' : analysis ? 'AI Deep Analysis' : 'Run AI Deep Analysis'}
          </span>
          {analysis?.cached && (
            <span className="text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded">cached</span>
          )}
        </div>
        {analysis && !loading && (
          <span className="text-indigo-400">{expanded ? '\u25B2' : '\u25BC'}</span>
        )}
      </button>

      {/* Loading Spinner */}
      {loading && (
        <div className="px-5 py-8 text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mb-3"></div>
          <p className="text-gray-500 text-sm">Classifying regime and running deep analysis...</p>
          <p className="text-gray-400 text-xs mt-1">This may take 10-15 seconds</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="px-5 py-4 bg-red-50 border-t border-red-200">
          <p className="text-red-600 text-sm">{error}</p>
          <button
            onClick={() => { setError(null); setAnalysis(null); }}
            className="text-red-500 text-xs underline mt-1"
          >
            Try again
          </button>
        </div>
      )}

      {/* Analysis Results */}
      {analysis && expanded && !loading && (
        <div className="px-5 py-4 space-y-5 border-t border-indigo-100">
          {/* Top Bar: Conviction + Action + Strategy */}
          <div className="flex flex-wrap items-center gap-3">
            <ConvictionBadge conviction={analysis.conviction} />
            <ActionPill action={analysis.action} />
            {analysis.strategy_match && (
              <span className="text-sm text-gray-600 bg-gray-100 px-2 py-1 rounded">
                {analysis.strategy_match}
              </span>
            )}
            {analysis.strategy_fit_score != null && (
              <span className="text-xs text-gray-500">
                Fit: {analysis.strategy_fit_score}%
              </span>
            )}
          </div>

          {/* Summary */}
          {analysis.summary && (
            <div className="bg-indigo-50 rounded-lg p-4">
              <p className="text-gray-800 font-medium leading-relaxed">{analysis.summary}</p>
            </div>
          )}

          {/* Checklist */}
          {analysis.checklist && Object.keys(analysis.checklist).length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-gray-500 uppercase mb-2">Quality Checklist</h5>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {Object.entries(analysis.checklist).map(([key, passed]) => (
                  <ChecklistItem
                    key={key}
                    label={checklistLabels[key] || key.replace(/_/g, ' ')}
                    passed={passed}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Entry + Risk Side-by-Side */}
          <div className="grid md:grid-cols-2 gap-4">
            {analysis.entry_assessment && (
              <div className="bg-gray-50 rounded-lg p-3">
                <h5 className="text-xs font-semibold text-gray-500 uppercase mb-2">Entry Assessment</h5>
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Quality</span>
                    <span className={`font-medium ${
                      analysis.entry_assessment.quality === 'excellent' ? 'text-green-600' :
                      analysis.entry_assessment.quality === 'good' ? 'text-blue-600' :
                      analysis.entry_assessment.quality === 'fair' ? 'text-yellow-600' : 'text-red-600'
                    }`}>
                      {analysis.entry_assessment.quality}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Timing</span>
                    <span className="font-medium text-gray-700">{analysis.entry_assessment.timing}</span>
                  </div>
                  {analysis.entry_assessment.reasoning && (
                    <p className="text-gray-600 text-xs mt-2">{analysis.entry_assessment.reasoning}</p>
                  )}
                </div>
              </div>
            )}

            {analysis.risk_assessment && (
              <div className="bg-gray-50 rounded-lg p-3">
                <h5 className="text-xs font-semibold text-gray-500 uppercase mb-2">Risk Assessment</h5>
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Stop Quality</span>
                    <span className="font-medium text-gray-700">{analysis.risk_assessment.stop_quality}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Risk/Reward</span>
                    <span className={`font-medium ${
                      analysis.risk_assessment.risk_reward === 'excellent' ? 'text-green-600' :
                      analysis.risk_assessment.risk_reward === 'good' ? 'text-blue-600' :
                      analysis.risk_assessment.risk_reward === 'fair' ? 'text-yellow-600' : 'text-red-600'
                    }`}>
                      {analysis.risk_assessment.risk_reward}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Position Size</span>
                    <span className="font-medium text-gray-700">{analysis.risk_assessment.position_size_suggestion}</span>
                  </div>
                  {analysis.risk_assessment.reasoning && (
                    <p className="text-gray-600 text-xs mt-2">{analysis.risk_assessment.reasoning}</p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Targets */}
          {analysis.targets && (
            <div className="bg-gray-50 rounded-lg p-3">
              <h5 className="text-xs font-semibold text-gray-500 uppercase mb-2">AI Targets</h5>
              <div className="grid grid-cols-3 gap-3 text-sm">
                {analysis.targets.target_1 && (
                  <div>
                    <span className="text-gray-500">Target 1</span>
                    <p className="font-medium text-green-600">
                      {analysis.targets.target_1.price ? `$${Number(analysis.targets.target_1.price).toFixed(2)}` : 'N/A'}
                    </p>
                    {analysis.targets.target_1.reasoning && (
                      <p className="text-xs text-gray-500">{analysis.targets.target_1.reasoning}</p>
                    )}
                  </div>
                )}
                {analysis.targets.target_2 && (
                  <div>
                    <span className="text-gray-500">Target 2</span>
                    <p className="font-medium text-green-600">
                      {analysis.targets.target_2.price ? `$${Number(analysis.targets.target_2.price).toFixed(2)}` : 'N/A'}
                    </p>
                    {analysis.targets.target_2.reasoning && (
                      <p className="text-xs text-gray-500">{analysis.targets.target_2.reasoning}</p>
                    )}
                  </div>
                )}
                {analysis.targets.trail_method && (
                  <div>
                    <span className="text-gray-500">Trail Method</span>
                    <p className="font-medium text-gray-700">{analysis.targets.trail_method.replace(/_/g, ' ')}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Options Play */}
          {analysis.options_play && analysis.options_play.structure !== 'none' && (
            <div className="bg-purple-50 rounded-lg p-3">
              <h5 className="text-xs font-semibold text-purple-600 uppercase mb-2">Options Recommendation</h5>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-gray-500">Structure</span>
                  <p className="font-medium text-purple-700">{analysis.options_play.structure?.replace(/_/g, ' ')}</p>
                </div>
                <div>
                  <span className="text-gray-500">IV Assessment</span>
                  <p className={`font-medium ${
                    analysis.options_play.iv_assessment === 'cheap' ? 'text-green-600' :
                    analysis.options_play.iv_assessment === 'expensive' || analysis.options_play.iv_assessment === 'WARNING_elevated' ? 'text-red-600' :
                    'text-gray-700'
                  }`}>
                    {analysis.options_play.iv_assessment?.replace(/_/g, ' ')}
                  </p>
                </div>
                {analysis.options_play.suggested_strike_area && analysis.options_play.suggested_strike_area !== 'N/A' && (
                  <div>
                    <span className="text-gray-500">Strike Area</span>
                    <p className="font-medium text-gray-700">{analysis.options_play.suggested_strike_area}</p>
                  </div>
                )}
                {analysis.options_play.suggested_dte && analysis.options_play.suggested_dte !== 'N/A' && (
                  <div>
                    <span className="text-gray-500">DTE</span>
                    <p className="font-medium text-gray-700">{analysis.options_play.suggested_dte}</p>
                  </div>
                )}
              </div>
              {analysis.options_play.reasoning && (
                <p className="text-xs text-gray-600 mt-2">{analysis.options_play.reasoning}</p>
              )}
            </div>
          )}

          {/* Failure Mode Warning */}
          {analysis.failure_mode && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
              <h5 className="text-xs font-semibold text-amber-700 uppercase mb-1">Invalidation / Failure Mode</h5>
              <p className="text-sm text-amber-800">{analysis.failure_mode}</p>
            </div>
          )}

          {/* Earnings Warning */}
          {analysis.earnings_warning && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <h5 className="text-xs font-semibold text-red-700 uppercase mb-1">Earnings Warning</h5>
              <p className="text-sm text-red-800">{analysis.earnings_warning}</p>
            </div>
          )}

          {/* Meta info */}
          <div className="text-xs text-gray-400 text-right">
            {analysis.analysis_type && <span>Type: {analysis.analysis_type} | </span>}
            {analysis.model && <span>Model: {analysis.model.split('/').pop()} | </span>}
            {analysis.analyzed_at && <span>{new Date(analysis.analyzed_at).toLocaleString()}</span>}
          </div>
        </div>
      )}
    </div>
  );
};

// =============================================================================
// MAIN MODAL
// =============================================================================

export default function SignalDetailModal({ signal, onClose }) {
  const [showTradeModal, setShowTradeModal] = useState(false);
  const [position, setPosition] = useState(null);
  const [positionLoading, setPositionLoading] = useState(false);
  const { tradingMode, fetchTradingMode } = useSignalsStore();

  // Fetch position for this symbol if exists
  useEffect(() => {
    if (signal) {
      fetchPosition();
      fetchTradingMode();
    }
  }, [signal]);

  const fetchPosition = async () => {
    if (!signal?.symbol) return;
    setPositionLoading(true);
    try {
      const data = await tradingAPI.getPosition(signal.symbol);
      setPosition(data.position);
    } catch (error) {
      setPosition(null);
    } finally {
      setPositionLoading(false);
    }
  };

  if (!signal) return null;

  const riskAmount = signal.entry_price && signal.stop_loss
    ? Math.abs(signal.entry_price - signal.stop_loss)
    : null;
  const rewardAmount = signal.entry_price && signal.target_1
    ? Math.abs(signal.target_1 - signal.entry_price)
    : null;

  return (
    <>
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
            <div className="flex items-center gap-4">
              <div>
                <h2 className="text-2xl font-bold text-gray-900">{signal.symbol}</h2>
                <p className="text-gray-500">{signal.name || 'Trading Signal'}</p>
              </div>
              <DirectionBadge direction={signal.direction} />
              <span className="px-2 py-1 bg-gray-100 rounded text-sm font-medium">
                {signal.timeframe}
              </span>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-3xl leading-none"
            >
              &times;
            </button>
          </div>

          <div className="p-6 space-y-6">
            {/* Main Trade Card */}
            <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-6">
              <div className="grid md:grid-cols-2 gap-6">
                {/* Left: Confidence & Strategy */}
                <div className="space-y-4">
                  <div>
                    <label className="text-sm text-gray-500 font-medium">Confidence Score</label>
                    <ConfidenceMeter score={signal.confidence_score} />
                  </div>
                  <div>
                    <label className="text-sm text-gray-500 font-medium">Strategy</label>
                    <p className="text-lg font-semibold capitalize">
                      {signal.strategy?.replace(/_/g, ' ') || 'Auto'}
                    </p>
                  </div>
                </div>

                {/* Right: Key Prices */}
                <div className="bg-white rounded-lg p-4 shadow-sm">
                  <PriceRow label="Entry Price" value={signal.entry_price} color="text-blue-600" />
                  {signal.entry_zone_low && signal.entry_zone_high && (
                    <PriceRow
                      label="Entry Zone"
                      value={null}
                      prefix=""
                      color="text-gray-600"
                    />
                  )}
                  {signal.entry_zone_low && (
                    <div className="text-sm text-gray-500 text-right">
                      ${signal.entry_zone_low?.toFixed(2)} - ${signal.entry_zone_high?.toFixed(2)}
                    </div>
                  )}
                  <PriceRow label="Stop Loss" value={signal.stop_loss} color="text-red-600" />
                  <PriceRow label="Target 1" value={signal.target_1} color="text-green-600" />
                  {signal.target_2 && (
                    <PriceRow label="Target 2" value={signal.target_2} color="text-green-600" />
                  )}
                  <div className="border-t border-gray-100 mt-2 pt-2">
                    <PriceRow
                      label="Risk:Reward"
                      value={signal.risk_reward_ratio}
                      prefix=""
                      color="text-indigo-600"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Position Card (if exists) */}
            {positionLoading ? (
              <div className="text-center py-4 text-gray-500">Loading position...</div>
            ) : position ? (
              <PositionCard position={position} onClose={fetchPosition} />
            ) : null}

            {/* AI Deep Analysis Panel */}
            {signal.id && (
              <AIDeepAnalysisPanel signalId={signal.id} />
            )}

            {/* AI Journaling Section (from signal engine) */}
            {signal.ai_reasoning && (
              <InfoCard title="Signal Engine Reasoning">
                <p className="text-gray-700 leading-relaxed">{signal.ai_reasoning}</p>
              </InfoCard>
            )}

            {/* Trade Parameters */}
            <div className="grid md:grid-cols-2 gap-4">
              {/* Risk Management */}
              <InfoCard title="Risk Management">
                {signal.stop_loss_logic && (
                  <div className="mb-3">
                    <label className="text-xs text-gray-500">Stop Loss Logic</label>
                    <p className="text-gray-700">{signal.stop_loss_logic}</p>
                  </div>
                )}
                {signal.target_logic && (
                  <div className="mb-3">
                    <label className="text-xs text-gray-500">Target Logic</label>
                    <p className="text-gray-700">{signal.target_logic}</p>
                  </div>
                )}
                {riskAmount && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Risk per share:</span>
                    <span className="text-red-600 font-medium">${riskAmount.toFixed(2)}</span>
                  </div>
                )}
                {rewardAmount && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Reward per share:</span>
                    <span className="text-green-600 font-medium">${rewardAmount.toFixed(2)}</span>
                  </div>
                )}
              </InfoCard>

              {/* Invalidation Conditions */}
              <InfoCard title="Invalidation Conditions">
                {signal.invalidation_conditions?.length > 0 ? (
                  <ul className="space-y-2">
                    {signal.invalidation_conditions.map((condition, idx) => (
                      <li key={idx} className="flex items-start gap-2 text-gray-700">
                        <span className="text-red-500">{'\u26A0\uFE0F'}</span>
                        <span>{condition}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-gray-500 text-sm">
                    Exit if price closes back inside breakout level or loses VWAP/EMA support.
                  </p>
                )}
              </InfoCard>
            </div>

            {/* Technical Snapshot */}
            {signal.technical_snapshot && (
              <InfoCard title="Technical Snapshot">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {Object.entries(signal.technical_snapshot).map(([key, value]) => (
                    <div key={key} className="text-center">
                      <div className="text-xs text-gray-500 uppercase">{key.replace(/_/g, ' ')}</div>
                      <div className="font-semibold">
                        {typeof value === 'number' ? value.toFixed(2) : value || '-'}
                      </div>
                    </div>
                  ))}
                </div>
              </InfoCard>
            )}

            {/* Institutional & Order Flow Data */}
            <div className="grid md:grid-cols-2 gap-4">
              {signal.institutional_data && (
                <InfoCard title="Institutional Indicators">
                  <div className="space-y-2">
                    {signal.institutional_data.vwap && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">VWAP</span>
                        <span className="font-medium">${signal.institutional_data.vwap.toFixed(2)}</span>
                      </div>
                    )}
                    {signal.institutional_data.opening_range_high && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">OR High</span>
                        <span className="font-medium">${signal.institutional_data.opening_range_high.toFixed(2)}</span>
                      </div>
                    )}
                    {signal.institutional_data.opening_range_low && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">OR Low</span>
                        <span className="font-medium">${signal.institutional_data.opening_range_low.toFixed(2)}</span>
                      </div>
                    )}
                  </div>
                </InfoCard>
              )}

              {signal.order_flow_data && (
                <InfoCard title="Order Flow">
                  <div className="space-y-2">
                    {signal.order_flow_data.rvol && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">RVOL</span>
                        <span className={`font-medium ${
                          signal.order_flow_data.rvol >= 1.5 ? 'text-green-600' : ''
                        }`}>
                          {signal.order_flow_data.rvol.toFixed(2)}x
                        </span>
                      </div>
                    )}
                    {signal.order_flow_data.volume_spike && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">Volume Spike</span>
                        <span className="text-green-600 font-medium">Yes</span>
                      </div>
                    )}
                  </div>
                </InfoCard>
              )}
            </div>

            {/* Signal Timestamp */}
            <div className="text-sm text-gray-500 text-center">
              Signal generated: {signal.generated_at
                ? new Date(signal.generated_at).toLocaleString()
                : 'Unknown'}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="sticky bottom-0 bg-white border-t border-gray-200 px-6 py-4 flex gap-4">
            <button
              onClick={onClose}
              className="flex-1 bg-gray-100 text-gray-700 py-3 rounded-lg font-medium hover:bg-gray-200 transition-colors"
            >
              Close
            </button>
            {!position && (
              <button
                onClick={() => setShowTradeModal(true)}
                className="flex-1 bg-green-600 text-white py-3 rounded-lg font-medium hover:bg-green-700 transition-colors flex items-center justify-center gap-2"
              >
                <span>Execute Trade</span>
                {tradingMode?.paper_mode !== false && (
                  <span className="text-xs bg-green-700 px-2 py-0.5 rounded">PAPER</span>
                )}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Trade Execution Modal */}
      {showTradeModal && (
        <TradeExecutionModal
          signal={signal}
          onClose={() => setShowTradeModal(false)}
          onSuccess={() => {
            setShowTradeModal(false);
            fetchPosition();
          }}
        />
      )}
    </>
  );
}
