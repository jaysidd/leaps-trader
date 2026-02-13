/**
 * Send to Bot Modal — Preview + Confirm + Execute a signal through the bot pipeline.
 *
 * Two-phase flow:
 *   1. Preview: Shows risk check, sizing, account info
 *   2. Execute: Places order through risk → size → execute pipeline
 *
 * Unlike TradeExecutionModal (which places raw Alpaca orders), this modal
 * routes through the full bot pipeline with risk checks, position sizing,
 * and trade journaling.
 */
import { useState, useEffect } from 'react';
import useBotStore from '../../stores/botStore';

// ─── State machine ──────────────────────────────────────────────────────────
const PHASE = {
  LOADING_PREVIEW: 'loading_preview',
  PREVIEW_READY: 'preview_ready',
  PREVIEW_ERROR: 'preview_error',
  EXECUTING: 'executing',
  SUCCESS: 'success',
  ERROR: 'error',
};

export default function SendToBotModal({ signal, onClose, onSuccess }) {
  const [phase, setPhase] = useState(PHASE.LOADING_PREVIEW);
  const [preview, setPreview] = useState(null);
  const [tradeResult, setTradeResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  const { previewSignal, executeSignal } = useBotStore();

  // ── Load preview on mount ────────────────────────────────────────────────
  useEffect(() => {
    loadPreview();
  }, []);

  const loadPreview = async () => {
    setPhase(PHASE.LOADING_PREVIEW);
    const result = await previewSignal(signal.id);
    if (result.error) {
      setErrorMsg(result.error);
      setPhase(PHASE.PREVIEW_ERROR);
    } else {
      setPreview(result);
      setPhase(PHASE.PREVIEW_READY);
    }
  };

  // ── Execute signal ───────────────────────────────────────────────────────
  const handleExecute = async () => {
    setPhase(PHASE.EXECUTING);
    const result = await executeSignal(signal.id);
    if (result.error) {
      setErrorMsg(result.error);
      setPhase(PHASE.ERROR);
    } else {
      setTradeResult(result.trade);
      setPhase(PHASE.SUCCESS);
    }
  };

  const side = signal?.direction === 'buy' ? 'BUY' : 'SELL';
  const sideColor = signal?.direction === 'buy'
    ? 'text-green-600 bg-green-100'
    : 'text-red-600 bg-red-100';

  // ═════════════════════════════════════════════════════════════════════════
  // SUCCESS VIEW
  // ═════════════════════════════════════════════════════════════════════════
  if (phase === PHASE.SUCCESS && tradeResult) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60] p-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-md w-full p-6">
          <div className="text-center">
            <div className="w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">Trade Executed!</h3>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              {side} order for {signal.symbol} placed through the bot pipeline.
            </p>

            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 text-left mb-4 space-y-2">
              <Row label="Symbol" value={tradeResult.symbol} bold />
              <Row label="Direction" value={tradeResult.direction?.toUpperCase()} />
              <Row label="Quantity" value={`${tradeResult.quantity} ${tradeResult.asset_type === 'option' ? 'contracts' : 'shares'}`} />
              {tradeResult.entry_price && (
                <Row label="Entry Price" value={`$${tradeResult.entry_price.toFixed(2)}`} color="green" />
              )}
              {tradeResult.take_profit_price && (
                <Row label="Take Profit" value={`$${tradeResult.take_profit_price.toFixed(2)}`} />
              )}
              {tradeResult.stop_loss_price && (
                <Row label="Stop Loss" value={`$${tradeResult.stop_loss_price.toFixed(2)}`} />
              )}
              <Row label="Status" value={tradeResult.status?.replace(/_/g, ' ')} />
            </div>

            {preview?.config?.paper_mode !== false && (
              <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3 mb-4">
                <p className="text-yellow-800 dark:text-yellow-300 text-sm">
                  <span className="font-semibold">Paper Trading Mode</span> — This is a simulated trade.
                </p>
              </div>
            )}

            <button
              onClick={() => { onSuccess?.(); onClose(); }}
              className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ═════════════════════════════════════════════════════════════════════════
  // MAIN VIEW (Preview / Loading / Error)
  // ═════════════════════════════════════════════════════════════════════════
  const isRiskApproved = preview?.risk_check?.approved;
  const isSizingOk = preview?.sizing && !preview.sizing.rejected;
  const canExecute = isRiskApproved && isSizingOk;
  const isLive = preview?.config?.paper_mode === false;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60] p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="border-b border-gray-200 dark:border-gray-700 px-6 py-4 flex justify-between items-center">
          <div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
              Send to Bot
              <span className={`text-xs font-bold px-2 py-0.5 rounded ${sideColor}`}>{side}</span>
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              Execute <span className="font-semibold">{signal.symbol}</span> through the bot pipeline
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-2xl leading-none"
          >
            &times;
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          {/* ── Loading ─────────────────────────────────────────────── */}
          {phase === PHASE.LOADING_PREVIEW && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-4" />
              <p className="text-gray-500 dark:text-gray-400">Loading trade preview...</p>
            </div>
          )}

          {/* ── Preview Error ───────────────────────────────────────── */}
          {phase === PHASE.PREVIEW_ERROR && (
            <div className="text-center py-8">
              <div className="w-12 h-12 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center mx-auto mb-3">
                <span className="text-red-600 dark:text-red-400 text-xl">!</span>
              </div>
              <p className="text-red-700 dark:text-red-400 font-medium mb-1">Cannot preview trade</p>
              <p className="text-red-600 dark:text-red-500 text-sm">{errorMsg}</p>
              <button onClick={onClose} className="mt-4 px-6 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600">
                Close
              </button>
            </div>
          )}

          {/* ── Execution Error ─────────────────────────────────────── */}
          {phase === PHASE.ERROR && (
            <div className="text-center py-8">
              <div className="w-12 h-12 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center mx-auto mb-3">
                <span className="text-red-600 dark:text-red-400 text-xl">!</span>
              </div>
              <p className="text-red-700 dark:text-red-400 font-medium mb-1">Execution Failed</p>
              <p className="text-red-600 dark:text-red-500 text-sm mb-4">{errorMsg}</p>
              <div className="flex gap-3 justify-center">
                <button onClick={onClose} className="px-6 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600">
                  Close
                </button>
                <button onClick={loadPreview} className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                  Retry
                </button>
              </div>
            </div>
          )}

          {/* ── Executing ───────────────────────────────────────────── */}
          {phase === PHASE.EXECUTING && (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="w-8 h-8 border-4 border-green-200 border-t-green-600 rounded-full animate-spin mb-4" />
              <p className="text-gray-700 dark:text-gray-300 font-medium">Executing trade...</p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Running risk → size → execute pipeline</p>
            </div>
          )}

          {/* ── Preview Ready ───────────────────────────────────────── */}
          {phase === PHASE.PREVIEW_READY && preview && (
            <>
              {/* Live Mode Warning */}
              {isLive && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-800 rounded-lg p-3">
                  <p className="text-red-800 dark:text-red-300 text-sm font-semibold">
                    LIVE TRADING — Real money will be used
                  </p>
                </div>
              )}

              {/* Paper Mode Indicator */}
              {!isLive && (
                <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3">
                  <p className="text-yellow-800 dark:text-yellow-300 text-sm">
                    <span className="font-semibold">Paper Trading Mode</span> — Simulated order
                  </p>
                </div>
              )}

              {/* Signal Summary */}
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Signal</h4>
                <div className="space-y-1.5">
                  <Row label="Symbol" value={signal.symbol} bold />
                  <Row label="Direction" value={side} />
                  <Row label="Strategy" value={signal.strategy || 'N/A'} />
                  <Row label="Confidence" value={signal.confidence_score ? `${signal.confidence_score.toFixed(0)}%` : 'N/A'} />
                  {signal.entry_price && <Row label="Signal Entry" value={`$${signal.entry_price.toFixed(2)}`} />}
                  {preview.current_price && <Row label="Current Price" value={`$${preview.current_price.toFixed(2)}`} color="blue" />}
                  {signal.stop_loss && <Row label="Stop Loss" value={`$${signal.stop_loss.toFixed(2)}`} />}
                  {signal.target_1 && <Row label="Target" value={`$${signal.target_1.toFixed(2)}`} />}
                </div>
              </div>

              {/* Risk Check Result */}
              <div className={`rounded-lg p-4 border ${
                isRiskApproved
                  ? 'bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-800'
                  : 'bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-800'
              }`}>
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Risk Check</h4>
                <div className="flex items-center gap-2">
                  {isRiskApproved ? (
                    <span className="text-green-600 dark:text-green-400 font-semibold flex items-center gap-1">
                      <span className="text-lg">&#10003;</span> Approved
                    </span>
                  ) : (
                    <>
                      <span className="text-red-600 dark:text-red-400 font-semibold flex items-center gap-1">
                        <span className="text-lg">&#10007;</span> Rejected
                      </span>
                      <span className="text-red-600 dark:text-red-500 text-sm ml-2">
                        {preview.risk_check.reason}
                      </span>
                    </>
                  )}
                </div>
                {preview.risk_check.warnings?.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {preview.risk_check.warnings.map((w, i) => (
                      <p key={i} className="text-yellow-700 dark:text-yellow-400 text-xs flex items-start gap-1">
                        <span>&#9888;</span> {w}
                      </p>
                    ))}
                  </div>
                )}
              </div>

              {/* Sizing Preview */}
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Position Sizing</h4>
                {preview.sizing?.rejected ? (
                  <p className="text-red-600 dark:text-red-400 text-sm">
                    Sizing rejected: {preview.sizing.reject_reason}
                  </p>
                ) : preview.sizing ? (
                  <div className="space-y-1.5">
                    <Row label="Quantity" value={`${preview.sizing.quantity} ${preview.sizing.asset_type === 'option' ? 'contracts' : 'shares'}`} bold />
                    <Row label="Notional" value={`$${preview.sizing.notional.toLocaleString()}`} />
                    <Row label="Sizing Mode" value={preview.config.sizing_mode?.replace(/_/g, ' ')} />
                    {preview.sizing.is_fractional && (
                      <p className="text-blue-600 dark:text-blue-400 text-xs">Fractional shares (notional order)</p>
                    )}
                    {preview.sizing.capped_reason && (
                      <p className="text-yellow-600 dark:text-yellow-400 text-xs">Capped: {preview.sizing.capped_reason}</p>
                    )}
                  </div>
                ) : (
                  <p className="text-gray-500 text-sm">No sizing data</p>
                )}
              </div>

              {/* Account */}
              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Account</h4>
                <div className="space-y-1.5">
                  <Row label="Equity" value={`$${preview.account.equity.toLocaleString()}`} />
                  <Row label="Buying Power" value={`$${preview.account.buying_power.toLocaleString()}`} />
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex gap-3 pt-2">
                <button
                  onClick={onClose}
                  className="flex-1 px-4 py-3 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg font-medium hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleExecute}
                  disabled={!canExecute}
                  className={`flex-1 px-4 py-3 rounded-lg font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                    isLive
                      ? 'bg-red-600 text-white hover:bg-red-700'
                      : 'bg-green-600 text-white hover:bg-green-700'
                  }`}
                >
                  {isLive ? 'Confirm & Execute (LIVE)' : 'Confirm & Execute'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function Row({ label, value, bold, color }) {
  const valueClass = [
    'text-sm',
    bold ? 'font-bold' : 'font-medium',
    color === 'green' ? 'text-green-600 dark:text-green-400' :
    color === 'blue' ? 'text-blue-600 dark:text-blue-400' :
    'text-gray-900 dark:text-gray-100',
  ].join(' ');

  return (
    <div className="flex justify-between">
      <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      <span className={valueClass}>{value}</span>
    </div>
  );
}
