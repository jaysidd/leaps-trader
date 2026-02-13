/**
 * Autopilot Dashboard - Monitoring and control center for automated trading
 *
 * Sections:
 *   A. Status Banner - account mode, automation level, scan toggle
 *   B. Market Intelligence - MRI, regime, fear & greed, trade readiness gauges
 *   C. Active Presets - current preset selection and reasoning
 *   D. Pipeline Status - scan -> candidates -> signals -> trades flow
 *   E. Position Size Calculator - collapsible risk calculator
 *   F. Activity Feed - scrollable event log with polling
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { autopilotApi } from '../api/autopilot';
import apiClient from '../api/axios';

// =============================================================================
// Helpers
// =============================================================================

/** Format a timestamp to relative time (e.g., "2 min ago") */
function formatRelativeTime(timestamp) {
  if (!timestamp) return '';
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diffSec = Math.floor((now - then) / 1000);

  if (diffSec < 10) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

/** Map a market condition string to a Tailwind color class pair [bg, text] */
function conditionColor(condition) {
  const map = {
    bullish: ['bg-green-100 dark:bg-green-900/40', 'text-green-700 dark:text-green-300'],
    neutral: ['bg-yellow-100 dark:bg-yellow-900/40', 'text-yellow-700 dark:text-yellow-300'],
    bearish: ['bg-red-100 dark:bg-red-900/40', 'text-red-700 dark:text-red-300'],
    volatile: ['bg-orange-100 dark:bg-orange-900/40', 'text-orange-700 dark:text-orange-300'],
    unknown: ['bg-gray-100 dark:bg-gray-700', 'text-gray-600 dark:text-gray-400'],
  };
  return map[condition?.toLowerCase()] || map.unknown;
}

/** Score to color: green > 60, yellow 30-60, red < 30 */
function scoreColor(score, invert = false) {
  const val = typeof score === 'number' ? score : 0;
  if (invert) {
    if (val > 60) return 'text-red-500';
    if (val > 30) return 'text-yellow-500';
    return 'text-green-500';
  }
  if (val >= 60) return 'text-green-500';
  if (val >= 30) return 'text-yellow-500';
  return 'text-red-500';
}

/** Event type icon map */
const EVENT_ICONS = {
  scan_started: '\uD83D\uDD0D',
  scan_complete: '\u2705',
  scan_skipped: '\u23ED\uFE0F',
  signal_generated: '\uD83D\uDCE1',
  trade_executed: '\uD83D\uDCB0',
  error: '\u274C',
};

/** Format currency */
function fmt$(val) {
  if (val == null || isNaN(val)) return '$0.00';
  return '$' + Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// =============================================================================
// Sub-components
// =============================================================================

/** Gauge card for market intelligence section */
function GaugeCard({ title, value, label, color, subtext }) {
  return (
    <div className="bg-gray-800 rounded-xl p-5 border border-gray-700 flex flex-col items-center">
      <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">{title}</p>
      <p className={`text-3xl font-bold ${color}`}>
        {value != null ? value : '--'}
      </p>
      {label && <p className={`text-sm font-medium mt-1 ${color}`}>{label}</p>}
      {subtext && <p className="text-xs text-gray-500 mt-1">{subtext}</p>}
    </div>
  );
}

/** Toggle button group (3 options) */
function ToggleGroup({ options, value, onChange, disabled }) {
  return (
    <div className="flex rounded-lg overflow-hidden border border-gray-600">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          disabled={disabled}
          className={`px-3 py-1.5 text-xs font-medium transition-colors ${
            value === opt.value
              ? opt.activeClass || 'bg-blue-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

/** Confirmation dialog */
function ConfirmDialog({ open, title, message, confirmLabel, confirmClass, onConfirm, onCancel }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-800 rounded-xl border border-gray-600 p-6 max-w-md w-full mx-4 shadow-2xl">
        <h3 className="text-lg font-bold text-white mb-2">{title}</h3>
        <p className="text-gray-300 text-sm mb-6">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg bg-gray-700 text-gray-300 hover:bg-gray-600 text-sm"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`px-4 py-2 rounded-lg text-white text-sm font-medium ${confirmClass || 'bg-red-600 hover:bg-red-700'}`}
          >
            {confirmLabel || 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export default function Autopilot() {
  // ----- State -----
  const [status, setStatus] = useState(null);
  const [marketState, setMarketState] = useState(null);
  const [activity, setActivity] = useState([]);
  const [statusLoading, setStatusLoading] = useState(true);
  const [activityLoading, setActivityLoading] = useState(true);
  const [error, setError] = useState(null);

  // Toggle loading states
  const [togglingAccount, setTogglingAccount] = useState(false);
  const [togglingMode, setTogglingMode] = useState(false);
  const [togglingScan, setTogglingScan] = useState(false);
  const [togglingAutoScan, setTogglingAutoScan] = useState(false);

  // Auto-scan preset selector
  const [availablePresets, setAvailablePresets] = useState([]);
  const [savingPresets, setSavingPresets] = useState(false);

  // Confirmation dialogs
  const [confirmDialog, setConfirmDialog] = useState(null);

  // Calculator state
  const [calcOpen, setCalcOpen] = useState(false);
  const [calc, setCalc] = useState({
    accountSize: 100000,
    riskPercent: 2,
    maxPositionSize: 10000,
    symbol: '',
    entryPrice: 0,
    stopLoss: 0,
    takeProfit: 0,
  });

  // Activity feed ref for auto-scroll
  const activityRef = useRef(null);
  const prevActivityLenRef = useRef(0);

  // ----- Data Fetching -----
  const fetchStatus = useCallback(async () => {
    try {
      const [statusData, marketData] = await Promise.all([
        autopilotApi.getStatus(),
        autopilotApi.getMarketState(),
      ]);
      setStatus(statusData);
      setMarketState(marketData);
      setError(null);
    } catch (err) {
      // Only set error on first load; silently fail on polling
      if (statusLoading) {
        setError('Failed to load autopilot status: ' + (err.message || 'Unknown error'));
      }
    } finally {
      setStatusLoading(false);
    }
  }, [statusLoading]);

  const fetchActivity = useCallback(async () => {
    try {
      const data = await autopilotApi.getActivity(24, 50);
      const events = Array.isArray(data) ? data : (data?.events || []);
      setActivity(events);
      // Auto-scroll if new events arrived
      if (events.length > prevActivityLenRef.current && activityRef.current) {
        activityRef.current.scrollTop = 0;
      }
      prevActivityLenRef.current = events.length;
    } catch {
      // Silently fail on activity polling
    } finally {
      setActivityLoading(false);
    }
  }, []);

  // Fetch available screening presets for auto-scan selector
  const fetchPresets = useCallback(async () => {
    try {
      const resp = await apiClient.get('/api/v1/screener/presets');
      const data = resp.data;
      // Flatten grouped presets into a flat list of { id, name }
      const flat = [];
      if (data?.presets) {
        for (const group of data.presets) {
          for (const p of (group.presets || [])) {
            flat.push({ id: p.id, name: p.name });
          }
        }
      }
      setAvailablePresets(flat);
    } catch {
      // Silently fail — presets are optional
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchStatus();
    fetchActivity();
    fetchPresets();
  }, []);

  // Polling: status every 15s, activity every 30s
  useEffect(() => {
    const statusInterval = setInterval(fetchStatus, 15000);
    const activityInterval = setInterval(fetchActivity, 30000);
    return () => {
      clearInterval(statusInterval);
      clearInterval(activityInterval);
    };
  }, [fetchStatus, fetchActivity]);

  // ----- Toggle Handlers -----

  const handleAccountToggle = useCallback(async (paperMode) => {
    const goingLive = paperMode === false;
    const currentMode = status?.execution_mode || 'signal_only';

    if (goingLive && currentMode === 'full_auto') {
      // Extra confirmation for Live + Full Auto
      setConfirmDialog({
        title: 'Switch to LIVE + Full Auto',
        message:
          'You are about to switch to LIVE trading with Full Auto execution. Real money trades will be placed automatically without approval. Are you absolutely sure?',
        confirmLabel: 'Yes, Go Live + Full Auto',
        confirmClass: 'bg-red-600 hover:bg-red-700',
        onConfirm: async () => {
          setConfirmDialog(null);
          setTogglingAccount(true);
          try {
            await apiClient.put('/api/v1/trading/bot/config', { paper_mode: false });
            await fetchStatus();
          } catch (err) {
            setError('Failed to switch account mode: ' + (err.message || ''));
          } finally {
            setTogglingAccount(false);
          }
        },
      });
      return;
    }

    if (goingLive) {
      setConfirmDialog({
        title: 'Switch to LIVE Trading',
        message:
          'You are about to switch to LIVE trading. Real money will be used for any executed trades. Proceed?',
        confirmLabel: 'Yes, Go Live',
        confirmClass: 'bg-red-600 hover:bg-red-700',
        onConfirm: async () => {
          setConfirmDialog(null);
          setTogglingAccount(true);
          try {
            await apiClient.put('/api/v1/trading/bot/config', { paper_mode: false });
            await fetchStatus();
          } catch (err) {
            setError('Failed to switch account mode: ' + (err.message || ''));
          } finally {
            setTogglingAccount(false);
          }
        },
      });
      return;
    }

    // Switching to paper - no confirmation needed
    setTogglingAccount(true);
    try {
      await apiClient.put('/api/v1/trading/bot/config', { paper_mode: true });
      await fetchStatus();
    } catch (err) {
      setError('Failed to switch account mode: ' + (err.message || ''));
    } finally {
      setTogglingAccount(false);
    }
  }, [status, fetchStatus]);

  const handleModeToggle = useCallback(async (mode) => {
    const isPaper = status?.paper_mode !== false;
    if (mode === 'full_auto' && !isPaper) {
      setConfirmDialog({
        title: 'Enable Full Auto on LIVE Account',
        message:
          'Full Auto on a LIVE account means trades execute automatically with real money and no manual approval. Are you sure?',
        confirmLabel: 'Enable Full Auto',
        confirmClass: 'bg-red-600 hover:bg-red-700',
        onConfirm: async () => {
          setConfirmDialog(null);
          setTogglingMode(true);
          try {
            await apiClient.put('/api/v1/trading/bot/config', { execution_mode: mode });
            await fetchStatus();
          } catch (err) {
            setError('Failed to change execution mode: ' + (err.message || ''));
          } finally {
            setTogglingMode(false);
          }
        },
      });
      return;
    }

    setTogglingMode(true);
    try {
      await apiClient.put('/api/v1/trading/bot/config', { execution_mode: mode });
      await fetchStatus();
    } catch (err) {
      setError('Failed to change execution mode: ' + (err.message || ''));
    } finally {
      setTogglingMode(false);
    }
  }, [status, fetchStatus]);

  const handleAutoScanToggle = useCallback(async () => {
    setTogglingAutoScan(true);
    try {
      const current = status?.auto_scan_enabled || false;
      await apiClient.put('/api/v1/settings/key/automation.auto_scan_enabled', { value: !current });
      await fetchStatus();
    } catch (err) {
      setError('Failed to toggle auto-scan: ' + (err.message || ''));
    } finally {
      setTogglingAutoScan(false);
    }
  }, [status, fetchStatus]);

  const handlePresetToggle = useCallback(async (presetId) => {
    setSavingPresets(true);
    try {
      const currentPresets = status?.auto_scan_presets || [];
      let newPresets;
      if (currentPresets.includes(presetId)) {
        newPresets = currentPresets.filter(p => p !== presetId);
      } else {
        newPresets = [...currentPresets, presetId];
      }
      await apiClient.put('/api/v1/settings/key/automation.auto_scan_presets', { value: JSON.stringify(newPresets) });
      await fetchStatus();
    } catch (err) {
      setError('Failed to update auto-scan presets: ' + (err.message || ''));
    } finally {
      setSavingPresets(false);
    }
  }, [status, fetchStatus]);

  const handleSmartScanToggle = useCallback(async () => {
    setTogglingScan(true);
    try {
      const current = status?.smart_scan_enabled || false;
      await apiClient.put('/api/v1/settings/key/automation.smart_scan_enabled', { value: !current });
      await fetchStatus();
    } catch (err) {
      setError('Failed to toggle smart scan: ' + (err.message || ''));
    } finally {
      setTogglingScan(false);
    }
  }, [status, fetchStatus]);

  // ----- Calculator Logic (frontend-only) -----
  const calcResults = (() => {
    const { accountSize, riskPercent, maxPositionSize, entryPrice, stopLoss, takeProfit } = calc;
    if (!entryPrice || entryPrice <= 0) return null;

    const riskDollar = (accountSize * riskPercent) / 100;
    const stopDiff = entryPrice - stopLoss;
    const profitDiff = takeProfit - entryPrice;

    let positionSize = maxPositionSize;
    let shares = Math.floor(maxPositionSize / entryPrice);

    if (stopLoss > 0 && stopDiff > 0) {
      const sharesFromRisk = Math.floor(riskDollar / stopDiff);
      const sizeFromRisk = sharesFromRisk * entryPrice;
      if (sizeFromRisk < positionSize) {
        positionSize = sizeFromRisk;
        shares = sharesFromRisk;
      }
    }

    if (shares <= 0) return null;

    positionSize = shares * entryPrice;
    const potentialLoss = stopLoss > 0 && stopDiff > 0 ? shares * stopDiff : 0;
    const potentialProfit = takeProfit > 0 && profitDiff > 0 ? shares * profitDiff : 0;
    const riskReward = potentialLoss > 0 ? potentialProfit / potentialLoss : 0;
    const positionPct = (positionSize / accountSize) * 100;
    const lossPct = (potentialLoss / accountSize) * 100;
    const profitPct = (potentialProfit / accountSize) * 100;

    return {
      positionSize,
      shares,
      potentialLoss,
      potentialProfit,
      riskReward,
      positionPct,
      lossPct,
      profitPct,
    };
  })();

  const updateCalc = (field, value) => {
    setCalc((prev) => ({ ...prev, [field]: value }));
  };

  // ----- Derived state -----
  const isPaper = status?.paper_mode !== false;
  const executionMode = status?.execution_mode || 'signal_only';
  const smartScanOn = status?.smart_scan_enabled || false;
  const autoScanOn = status?.auto_scan_enabled || false;
  const selectedPresets = status?.auto_scan_presets || [];

  // Market state: comes from /market-state endpoint as {condition, snapshot: {mri, regime, fear_greed, ...}}
  const snapshot = marketState?.snapshot || status?.market_snapshot || {};
  const marketCondition = snapshot?.regime || marketState?.condition || status?.current_condition || 'unknown';
  const mriScore = snapshot?.mri ?? null;
  const mriLabel = snapshot?.mri_regime || '';
  const fearGreed = snapshot?.fear_greed ?? null;
  const fearGreedLabel = fearGreed != null
    ? (fearGreed < 30 ? 'Fear' : fearGreed > 70 ? 'Greed' : 'Neutral')
    : '';
  const tradeReadiness = snapshot?.readiness ?? null;
  const tradeReadinessLabel = snapshot?.readiness_label || (
    tradeReadiness != null
      ? tradeReadiness >= 60 ? 'Ready' : tradeReadiness >= 30 ? 'Caution' : 'Not Ready'
      : ''
  );
  const regimeConfidence = snapshot?.regime_confidence ?? null;

  // Pipeline counts from status.pipeline object
  const pipeline = status?.pipeline || {};
  const pipelineScan = status?.scan_count ?? '--';
  const pipelineCandidates = pipeline?.candidates_in_queue ?? '--';
  const pipelineSignals = pipeline?.active_signals ?? '--';
  const pipelineTrades = pipeline?.open_positions ?? '--';
  const todayPnl = pipeline?.today_pl ?? 0;
  const capitalUsed = status?.capital_used ?? 0;
  const maxCapital = status?.autopilot_max_capital ?? 0;
  const openPositions = pipeline?.open_positions ?? 0;

  // Active presets
  const activePresets = status?.active_presets || [];
  const presetReasoning = status?.reasoning || '';

  // Next scan countdown
  const nextScan = status?.next_scan_at || null;

  // ----- Loading / Error States -----
  if (statusLoading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-gray-400">Loading Autopilot...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 py-6 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <span>&#129302;</span> Autopilot Dashboard
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Monitor and control your automated trading pipeline
            </p>
          </div>
        </div>

        {/* Error Banner */}
        {error && (
          <div className="p-4 bg-red-900/30 border border-red-700 rounded-lg text-red-300 flex justify-between items-center">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-200 ml-4">
              Dismiss
            </button>
          </div>
        )}

        {/* ================================================================= */}
        {/* A. STATUS BANNER                                                  */}
        {/* ================================================================= */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            {/* Account Toggle */}
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Account</p>
              <ToggleGroup
                options={[
                  { value: true, label: 'Paper', activeClass: 'bg-blue-600 text-white' },
                  { value: false, label: 'Live', activeClass: 'bg-red-600 text-white' },
                ]}
                value={isPaper}
                onChange={(val) => handleAccountToggle(val)}
                disabled={togglingAccount}
              />
            </div>

            {/* Automation Level Toggle */}
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Automation Level</p>
              <ToggleGroup
                options={[
                  { value: 'signal_only', label: 'Signal Only', activeClass: 'bg-gray-600 text-white' },
                  { value: 'semi_auto', label: 'Semi-Auto', activeClass: 'bg-yellow-600 text-white' },
                  { value: 'full_auto', label: 'Full Auto', activeClass: 'bg-green-600 text-white' },
                ]}
                value={executionMode}
                onChange={handleModeToggle}
                disabled={togglingMode}
              />
            </div>

            {/* Auto-Scan Toggle */}
            <div className="flex items-center gap-3">
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Auto-Scan</p>
                <p className="text-xs text-gray-500 dark:text-gray-500">
                  {autoScanOn ? 'ON' : 'OFF'}
                  {selectedPresets.length > 0 && ` \u2022 ${selectedPresets.length} presets`}
                </p>
              </div>
              <button
                onClick={handleAutoScanToggle}
                disabled={togglingAutoScan}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  autoScanOn ? 'bg-green-600' : 'bg-gray-600'
                } ${togglingAutoScan ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    autoScanOn ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {/* Smart Scan Toggle */}
            <div className="flex items-center gap-3">
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Smart Scan</p>
                <p className="text-xs text-gray-500 dark:text-gray-500">
                  {smartScanOn ? 'ON' : 'OFF'}
                  {marketCondition !== 'unknown' && ` \u2022 ${marketCondition}`}
                </p>
              </div>
              <button
                onClick={handleSmartScanToggle}
                disabled={togglingScan}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  smartScanOn ? 'bg-blue-600' : 'bg-gray-600'
                } ${togglingScan ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    smartScanOn ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {/* Next Scan Countdown */}
            <div className="text-right">
              <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Next Scan</p>
              <p className="text-sm font-medium text-gray-300">
                {nextScan ? formatRelativeTime(nextScan) : '--'}
              </p>
            </div>
          </div>

          {/* Live mode warning bar */}
          {!isPaper && (
            <div className="mt-4 p-3 bg-red-900/30 border border-red-700 rounded-lg flex items-center gap-2">
              <span className="text-lg">{'\u26A0\uFE0F'}</span>
              <span className="text-red-300 text-sm font-medium">
                LIVE TRADING ACTIVE {executionMode === 'full_auto' && '- Full Auto enabled. Trades execute automatically with real money.'}
              </span>
            </div>
          )}
        </div>

        {/* ================================================================= */}
        {/* B. MARKET INTELLIGENCE                                            */}
        {/* ================================================================= */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <GaugeCard
            title="MRI Score"
            value={mriScore}
            label={mriLabel}
            color={scoreColor(mriScore)}
            subtext="Market Risk Index"
          />
          <GaugeCard
            title="Market Regime"
            value={marketCondition !== 'unknown' ? marketCondition.charAt(0).toUpperCase() + marketCondition.slice(1) : '--'}
            label={regimeConfidence != null ? `${regimeConfidence}% confidence` : ''}
            color={
              marketCondition === 'bullish' ? 'text-green-500' :
              marketCondition === 'bearish' ? 'text-red-500' :
              'text-yellow-500'
            }
          />
          <GaugeCard
            title="Fear & Greed"
            value={fearGreed}
            label={fearGreedLabel}
            color={scoreColor(fearGreed, true)}
            subtext="CNN Index"
          />
          <GaugeCard
            title="Trade Readiness"
            value={tradeReadiness}
            label={tradeReadinessLabel}
            color={scoreColor(tradeReadiness)}
          />
        </div>

        {/* ================================================================= */}
        {/* C. ACTIVE PRESETS + AUTO-SCAN PRESET SELECTOR                     */}
        {/* ================================================================= */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          {/* Smart Scan presets (AI-selected) */}
          {smartScanOn && (
            <div className="mb-4">
              <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
                Smart Scan Presets (AI-Selected)
              </h2>
              <div className="flex flex-wrap gap-2 mb-2">
                {activePresets.length > 0 ? activePresets.map((p) => (
                  <span
                    key={p}
                    className="px-3 py-1 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 rounded-full text-sm font-medium"
                  >
                    {p}
                  </span>
                )) : (
                  <span className="text-gray-500 dark:text-gray-400 text-sm">No presets selected yet</span>
                )}
              </div>
              {presetReasoning && (
                <p className="text-sm text-gray-500 dark:text-gray-400 italic">{presetReasoning}</p>
              )}
            </div>
          )}

          {/* Auto-Scan preset selector (manual) */}
          <div>
            <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
              Auto-Scan Presets
              {!autoScanOn && <span className="ml-2 text-xs font-normal text-gray-500">(Enable Auto-Scan to activate)</span>}
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-500 mb-3">
              Select which screening presets run automatically every 30 minutes during market hours.
              {smartScanOn && ' When Smart Scan is ON, these are overridden by AI-selected presets.'}
            </p>
            <div className="flex flex-wrap gap-2">
              {availablePresets.length > 0 ? availablePresets.map((p) => {
                const isSelected = selectedPresets.includes(p.id);
                return (
                  <button
                    key={p.id}
                    onClick={() => handlePresetToggle(p.id)}
                    disabled={savingPresets}
                    className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors border ${
                      isSelected
                        ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700'
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 border-gray-300 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600'
                    } ${savingPresets ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    {isSelected && '\u2713 '}{p.name}
                  </button>
                );
              }) : (
                <span className="text-gray-500 dark:text-gray-400 text-sm">Loading presets...</span>
              )}
            </div>
            {selectedPresets.length > 0 && (
              <p className="text-xs text-gray-500 dark:text-gray-500 mt-2">
                {selectedPresets.length} preset{selectedPresets.length !== 1 ? 's' : ''} selected: {selectedPresets.join(', ')}
              </p>
            )}
          </div>
        </div>

        {/* ================================================================= */}
        {/* D. PIPELINE STATUS                                                */}
        {/* ================================================================= */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
            Pipeline Status
          </h2>

          {/* Visual pipeline flow */}
          <div className="flex items-center justify-between mb-6 overflow-x-auto">
            {[
              { label: 'Scan', count: pipelineScan, color: 'bg-blue-500' },
              { label: 'Candidates', count: pipelineCandidates, color: 'bg-purple-500' },
              { label: 'Signals', count: pipelineSignals, color: 'bg-yellow-500' },
              { label: 'Trades', count: pipelineTrades, color: 'bg-green-500' },
            ].map((stage, i) => (
              <div key={stage.label} className="flex items-center">
                <div className="flex flex-col items-center min-w-[80px]">
                  <div className={`w-12 h-12 ${stage.color} rounded-full flex items-center justify-center text-white font-bold text-lg`}>
                    {stage.count}
                  </div>
                  <span className="text-xs text-gray-400 mt-1">{stage.label}</span>
                </div>
                {i < 3 && (
                  <div className="w-8 lg:w-16 h-0.5 bg-gray-600 mx-1 flex-shrink-0" />
                )}
              </div>
            ))}
          </div>

          {/* Stats row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">Today P&L</p>
              <p className={`text-lg font-bold ${todayPnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {todayPnl >= 0 ? '+' : ''}{fmt$(todayPnl)}
              </p>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">Capital Used</p>
              <p className="text-lg font-bold text-gray-200">{fmt$(capitalUsed)}</p>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">Max Capital</p>
              <p className="text-lg font-bold text-gray-200">{fmt$(maxCapital)}</p>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">Open Positions</p>
              <p className="text-lg font-bold text-gray-200">{openPositions}</p>
            </div>
          </div>
        </div>

        {/* ================================================================= */}
        {/* E. POSITION SIZE CALCULATOR                                       */}
        {/* ================================================================= */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setCalcOpen(!calcOpen)}
            className="w-full flex items-center justify-between p-5 text-left"
          >
            <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              Position Size Calculator
            </h2>
            <svg
              className={`w-5 h-5 text-gray-400 transform transition-transform ${calcOpen ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {calcOpen && (
            <div className="px-5 pb-5 border-t border-gray-200 dark:border-gray-700 pt-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Input fields */}
                <div className="space-y-4">
                  <h3 className="text-sm font-medium text-gray-300 mb-2">Inputs</h3>
                  {[
                    { label: 'Account Size ($)', field: 'accountSize', min: 0, step: 1000 },
                    { label: 'Risk Per Position (%)', field: 'riskPercent', min: 0, max: 100, step: 0.5 },
                    { label: 'Max Position Size ($)', field: 'maxPositionSize', min: 0, step: 500 },
                    { label: 'Symbol', field: 'symbol', type: 'text' },
                    { label: 'Entry Price ($)', field: 'entryPrice', min: 0, step: 0.01 },
                    { label: 'Stop Loss ($)', field: 'stopLoss', min: 0, step: 0.01 },
                    { label: 'Take Profit ($)', field: 'takeProfit', min: 0, step: 0.01 },
                  ].map(({ label, field, type, ...rest }) => (
                    <div key={field}>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</label>
                      <input
                        type={type || 'number'}
                        value={calc[field]}
                        onChange={(e) =>
                          updateCalc(field, type === 'text' ? e.target.value : parseFloat(e.target.value) || 0)
                        }
                        className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-gray-100 text-sm"
                        {...rest}
                      />
                    </div>
                  ))}
                </div>

                {/* Results */}
                <div className="space-y-4">
                  <h3 className="text-sm font-medium text-gray-300 mb-2">Results</h3>
                  {calcResults ? (
                    <div className="space-y-3">
                      <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 space-y-3">
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-400">Position Size</span>
                          <span className="text-sm font-bold text-white">
                            {fmt$(calcResults.positionSize)} ({calcResults.shares} shares)
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-400">Risk/Reward</span>
                          <span className={`text-sm font-bold ${calcResults.riskReward >= 1.5 ? 'text-green-500' : 'text-red-500'}`}>
                            {calcResults.riskReward > 0 ? `1:${calcResults.riskReward.toFixed(2)}` : '--'}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-400">Potential Loss</span>
                          <span className="text-sm font-bold text-red-500">
                            -{fmt$(calcResults.potentialLoss)} ({calcResults.lossPct.toFixed(2)}% of account)
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-400">Potential Profit</span>
                          <span className="text-sm font-bold text-green-500">
                            +{fmt$(calcResults.potentialProfit)} ({calcResults.profitPct.toFixed(2)}% of account)
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-400">Position % of Account</span>
                          <span className="text-sm font-bold text-gray-200">
                            {calcResults.positionPct.toFixed(1)}%
                          </span>
                        </div>
                      </div>

                      {/* Warnings */}
                      {calcResults.riskReward > 0 && calcResults.riskReward < 1.5 && (
                        <div className="p-3 bg-yellow-900/30 border border-yellow-700 rounded-lg">
                          <p className="text-sm text-yellow-300">
                            {'\u26A0\uFE0F'} Risk/Reward ratio ({calcResults.riskReward.toFixed(2)}) is below 1.5. Consider adjusting your stop loss or take profit.
                          </p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-6 text-center">
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        Enter an entry price to calculate position size
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ================================================================= */}
        {/* F. ACTIVITY FEED                                                  */}
        {/* ================================================================= */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
            Activity Feed
          </h2>

          <div
            ref={activityRef}
            className="max-h-96 overflow-y-auto space-y-2"
          >
            {activityLoading ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-2"></div>
                <p className="text-gray-500 text-sm">Loading activity...</p>
              </div>
            ) : activity.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-gray-500 dark:text-gray-400 text-sm">No recent activity</p>
              </div>
            ) : (
              activity.map((event, idx) => {
                const eventType = event.event_type || event.type || 'unknown';
                const icon = EVENT_ICONS[eventType] || '\u2139\uFE0F';
                const condition = event.market_condition || event.condition;
                const [condBg, condText] = conditionColor(condition);

                return (
                  <div
                    key={event.id || idx}
                    className="flex items-start gap-3 p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
                  >
                    <span className="text-lg flex-shrink-0 mt-0.5">{icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {formatRelativeTime(event.timestamp || event.created_at)}
                        </span>
                        {condition && (
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${condBg} ${condText}`}>
                            {condition}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-800 dark:text-gray-200 truncate">
                        {typeof event.details === 'string'
                          ? event.details
                          : event.details && typeof event.details === 'object'
                            ? (event.details.preset_summaries || []).join(' | ') ||
                              event.details.reason ||
                              event.details.error ||
                              JSON.stringify(event.details)
                            : event.message || event.description || eventType.replace(/_/g, ' ')}
                      </p>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {activity.length >= 50 && (
            <div className="mt-3 text-center">
              <button
                onClick={() => {
                  /* Could load more with offset; for now just show a message */
                }}
                className="text-sm text-blue-500 hover:text-blue-400"
              >
                Load more...
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Confirmation Dialog */}
      <ConfirmDialog
        open={!!confirmDialog}
        title={confirmDialog?.title || ''}
        message={confirmDialog?.message || ''}
        confirmLabel={confirmDialog?.confirmLabel}
        confirmClass={confirmDialog?.confirmClass}
        onConfirm={confirmDialog?.onConfirm || (() => setConfirmDialog(null))}
        onCancel={() => setConfirmDialog(null)}
      />
    </div>
  );
}
