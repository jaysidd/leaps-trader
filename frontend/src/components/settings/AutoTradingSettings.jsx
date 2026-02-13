/**
 * AutoTradingSettings — Bot configuration tab in Settings page
 *
 * Sections: Execution Mode, Per-Trade Limits, Daily Limits, Exit Rules,
 * Signal Filters, Circuit Breakers, Options Settings
 */
import { useState, useEffect } from 'react';
import useBotStore from '../../stores/botStore';

const EXECUTION_MODES = [
  { value: 'signal_only', label: 'Signal Only', desc: 'Generate signals for dashboard + Telegram. No auto-trading.' },
  { value: 'semi_auto', label: 'Semi-Auto', desc: 'Signal fires → you get notified → one-click approve → bot executes.' },
  { value: 'full_auto', label: 'Full Auto', desc: 'Signal fires → risk check → size → execute → monitor → exit. Zero human input.' },
];

const SIZING_MODES = [
  { value: 'fixed_dollar', label: 'Fixed Dollar', desc: 'Use a fixed $ amount per trade' },
  { value: 'pct_portfolio', label: '% of Portfolio', desc: 'Use a percentage of total equity' },
  { value: 'risk_based', label: 'Risk-Based', desc: '$ risk / stop distance = position size' },
];

export default function AutoTradingSettings() {
  const { config, fetchConfig, updateConfig, status, fetchStatus } = useBotStore();
  const [localConfig, setLocalConfig] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    fetchConfig();
    fetchStatus();
  }, []);

  useEffect(() => {
    if (config) {
      setLocalConfig({ ...config });
    }
  }, [config]);

  const handleChange = (field, value) => {
    setLocalConfig(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      // Only send changed fields
      const changes = {};
      for (const [key, val] of Object.entries(localConfig)) {
        if (config[key] !== val && key !== 'id' && key !== 'created_at' && key !== 'updated_at') {
          changes[key] = val;
        }
      }
      if (Object.keys(changes).length > 0) {
        await updateConfig(changes);
      }
      setSaved(true);
      setHasChanges(false);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  if (!localConfig) {
    return <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>;
  }

  const isLiveMode = !localConfig.paper_mode;
  const isAutoMode = localConfig.execution_mode === 'full_auto';

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Auto Trading Configuration</h2>
          <p className="text-gray-600 dark:text-gray-400 mt-1">Configure automated trading behavior and safety limits</p>
        </div>
        {status && (
          <div className={`px-3 py-1 rounded-full text-sm font-medium ${
            status.status === 'running' ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' :
            status.status === 'paused' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400' :
            'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
          }`}>
            Bot: {status.status?.toUpperCase()}
          </div>
        )}
      </div>

      {/* Live Mode Warning */}
      {isLiveMode && (
        <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-700 rounded-lg">
          <p className="text-red-800 dark:text-red-400 font-medium">WARNING: Live trading is enabled. Real money is at risk.</p>
        </div>
      )}

      {/* Full Auto Warning */}
      {isAutoMode && (
        <div className="p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700 rounded-lg">
          <p className="text-amber-800 dark:text-amber-400 font-medium">Full Auto mode: Trades execute without human approval.</p>
        </div>
      )}

      {/* ── Section 1: Execution Mode ──────────────────────── */}
      <Section title="Execution Mode" icon="*">
        <div className="space-y-3">
          {EXECUTION_MODES.map(mode => (
            <label key={mode.value} className={`flex items-start p-3 rounded-lg border cursor-pointer transition-colors ${
              localConfig.execution_mode === mode.value
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-500'
                : 'border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500'
            }`}>
              <input
                type="radio"
                name="execution_mode"
                value={mode.value}
                checked={localConfig.execution_mode === mode.value}
                onChange={() => handleChange('execution_mode', mode.value)}
                className="mt-1 mr-3"
              />
              <div>
                <span className="font-medium text-gray-900 dark:text-white">{mode.label}</span>
                <p className="text-sm text-gray-500 dark:text-gray-400">{mode.desc}</p>
              </div>
            </label>
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <div>
            <span className="font-medium text-gray-900 dark:text-white">Paper Mode</span>
            <p className="text-sm text-gray-500 dark:text-gray-400">Use paper trading (simulated). Disable for real money.</p>
          </div>
          <Toggle
            checked={localConfig.paper_mode}
            onChange={(v) => handleChange('paper_mode', v)}
          />
        </div>
      </Section>

      {/* ── Section 2: Per-Trade Limits ────────────────────── */}
      <Section title="Per-Trade Limits" icon="$">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <NumberInput label="Max $ Per Stock Trade" value={localConfig.max_per_stock_trade} onChange={v => handleChange('max_per_stock_trade', v)} min={10} step={50} prefix="$" />
          <NumberInput label="Max $ Per Options Trade" value={localConfig.max_per_options_trade} onChange={v => handleChange('max_per_options_trade', v)} min={10} step={50} prefix="$" />
        </div>

        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Sizing Mode</label>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {SIZING_MODES.map(mode => (
              <label key={mode.value} className={`flex flex-col p-3 rounded-lg border cursor-pointer text-center transition-colors ${
                localConfig.sizing_mode === mode.value
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-200 dark:border-gray-600 hover:border-gray-300'
              }`}>
                <input type="radio" name="sizing_mode" value={mode.value} checked={localConfig.sizing_mode === mode.value} onChange={() => handleChange('sizing_mode', mode.value)} className="sr-only" />
                <span className="font-medium text-gray-900 dark:text-white text-sm">{mode.label}</span>
                <span className="text-xs text-gray-500 dark:text-gray-400 mt-1">{mode.desc}</span>
              </label>
            ))}
          </div>
        </div>

        {localConfig.sizing_mode === 'risk_based' && (
          <div className="mt-4">
            <NumberInput label="Risk % Per Trade" value={localConfig.risk_pct_per_trade} onChange={v => handleChange('risk_pct_per_trade', v)} min={0.1} max={10} step={0.1} suffix="%" />
          </div>
        )}
      </Section>

      {/* ── Section 3: Daily Limits ────────────────────────── */}
      <Section title="Daily Limits" icon="!">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <NumberInput label="Max Daily Loss" value={localConfig.max_daily_loss} onChange={v => handleChange('max_daily_loss', v)} min={50} step={50} prefix="$" />
          <NumberInput label="Max Trades Per Day" value={localConfig.max_trades_per_day} onChange={v => handleChange('max_trades_per_day', v)} min={1} max={100} step={1} />
          <NumberInput label="Max Concurrent Positions" value={localConfig.max_concurrent_positions} onChange={v => handleChange('max_concurrent_positions', v)} min={1} max={50} step={1} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <NumberInput label="Max % per Position (of equity)" value={localConfig.max_portfolio_allocation_pct} onChange={v => handleChange('max_portfolio_allocation_pct', v)} min={1} max={100} step={1} suffix="%" />
          <NumberInput label="Max Total Invested %" value={localConfig.max_total_invested_pct} onChange={v => handleChange('max_total_invested_pct', v)} min={10} max={100} step={5} suffix="%" />
        </div>
      </Section>

      {/* ── Section 4: Exit Rules ──────────────────────────── */}
      <Section title="Exit Rules" icon="X">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <NumberInput label="Default Take Profit %" value={localConfig.default_take_profit_pct} onChange={v => handleChange('default_take_profit_pct', v)} min={1} max={500} step={1} suffix="%" />
          <NumberInput label="Default Stop Loss %" value={localConfig.default_stop_loss_pct} onChange={v => handleChange('default_stop_loss_pct', v)} min={1} max={100} step={1} suffix="%" />
        </div>

        <div className="mt-4 flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <div>
            <span className="font-medium text-gray-900 dark:text-white">Trailing Stop</span>
            <p className="text-sm text-gray-500 dark:text-gray-400">Automatically trail price with a stop loss</p>
          </div>
          <Toggle checked={localConfig.trailing_stop_enabled} onChange={v => handleChange('trailing_stop_enabled', v)} />
        </div>
        {localConfig.trailing_stop_enabled && (
          <div className="mt-2">
            <NumberInput label="Trailing Stop %" value={localConfig.trailing_stop_pct} onChange={v => handleChange('trailing_stop_pct', v)} min={0.5} max={50} step={0.5} suffix="%" />
          </div>
        )}

        <div className="mt-4 flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <div>
            <span className="font-medium text-gray-900 dark:text-white">Close Positions at EOD</span>
            <p className="text-sm text-gray-500 dark:text-gray-400">Close all positions before market close</p>
          </div>
          <Toggle checked={localConfig.close_positions_eod} onChange={v => handleChange('close_positions_eod', v)} />
        </div>

        <div className="mt-4">
          <NumberInput label="LEAPS Roll Alert (DTE)" value={localConfig.leaps_roll_alert_dte} onChange={v => handleChange('leaps_roll_alert_dte', v)} min={10} max={180} step={5} suffix=" days" />
        </div>
      </Section>

      {/* ── Section 5: Signal Filters ──────────────────────── */}
      <Section title="Signal Filters" icon="#">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <NumberInput label="Min Confidence to Execute" value={localConfig.min_confidence_to_execute} onChange={v => handleChange('min_confidence_to_execute', v)} min={0} max={100} step={5} suffix="%" />
          <NumberInput label="Min AI Conviction (0-10)" value={localConfig.min_ai_conviction} onChange={v => handleChange('min_ai_conviction', v)} min={0} max={10} step={0.5} />
        </div>
        <div className="mt-4 flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <div>
            <span className="font-medium text-gray-900 dark:text-white">Require AI Analysis</span>
            <p className="text-sm text-gray-500 dark:text-gray-400">Only execute signals that have AI deep analysis</p>
          </div>
          <Toggle checked={localConfig.require_ai_analysis} onChange={v => handleChange('require_ai_analysis', v)} />
        </div>
      </Section>

      {/* ── Section 6: Circuit Breakers ────────────────────── */}
      <Section title="Circuit Breakers" icon="!">
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Daily drawdown thresholds that trigger automatic safety measures.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <NumberInput label="Warning Level %" value={localConfig.circuit_breaker_warn_pct} onChange={v => handleChange('circuit_breaker_warn_pct', v)} min={1} max={50} step={0.5} suffix="%" />
          <NumberInput label="Pause Level %" value={localConfig.circuit_breaker_pause_pct} onChange={v => handleChange('circuit_breaker_pause_pct', v)} min={1} max={50} step={0.5} suffix="%" />
          <NumberInput label="Halt Level %" value={localConfig.circuit_breaker_halt_pct} onChange={v => handleChange('circuit_breaker_halt_pct', v)} min={1} max={50} step={0.5} suffix="%" />
        </div>
      </Section>

      {/* ── Section 7: Options Settings ────────────────────── */}
      <Section title="Options-Specific Settings" icon="O">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <NumberInput label="Max Bid-Ask Spread %" value={localConfig.max_bid_ask_spread_pct} onChange={v => handleChange('max_bid_ask_spread_pct', v)} min={0.5} max={50} step={0.5} suffix="%" />
          <NumberInput label="Min Open Interest" value={localConfig.min_option_open_interest} onChange={v => handleChange('min_option_open_interest', v)} min={0} max={10000} step={10} />
          <NumberInput label="Min Volume" value={localConfig.min_option_volume} onChange={v => handleChange('min_option_volume', v)} min={0} max={10000} step={10} />
        </div>
      </Section>

      {/* ── Save Button ────────────────────────────────────── */}
      {(hasChanges || error || saved) && (
        <div className="flex items-center justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
          <div>
            {error && <span className="text-red-500 text-sm">{error}</span>}
            {saved && <span className="text-green-500 text-sm">Configuration saved!</span>}
          </div>
          <div className="flex gap-3">
            {hasChanges && (
              <button
                onClick={() => { setLocalConfig({ ...config }); setHasChanges(false); }}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                Cancel
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={!hasChanges || saving}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Saving...' : 'Save Configuration'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Helper Components ────────────────────────────────────────

function Section({ title, icon, children }) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-5">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
        <span className="w-6 h-6 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded text-center text-sm leading-6 font-bold">{icon}</span>
        {title}
      </h3>
      {children}
    </div>
  );
}

function NumberInput({ label, value, onChange, min, max, step, prefix, suffix }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{label}</label>
      <div className="flex items-center">
        {prefix && <span className="text-gray-500 dark:text-gray-400 mr-2 text-sm">{prefix}</span>}
        <input
          type="number"
          value={value ?? ''}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          min={min}
          max={max}
          step={step}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
        />
        {suffix && <span className="text-gray-500 dark:text-gray-400 ml-2 text-sm whitespace-nowrap">{suffix}</span>}
      </div>
    </div>
  );
}

function Toggle({ checked, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        checked ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
      }`}
    >
      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
        checked ? 'translate-x-6' : 'translate-x-1'
      }`} />
    </button>
  );
}
