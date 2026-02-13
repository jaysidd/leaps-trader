/**
 * Health Dashboard — real-time system health monitoring.
 *
 * Features:
 *   - Overall status banner (healthy / degraded / critical)
 *   - Dependency health cards (DB, Redis, Alpaca, Scheduler)
 *   - Scheduler jobs table with overdue detection
 *   - Auto-scan and Trading Bot health panels
 *   - Auto-refresh every 15 seconds (toggleable)
 *   - Force-check button for manual refresh
 */
import { useState, useEffect, useCallback } from 'react';
import apiClient from '../api/axios';

// ── Status styling ───────────────────────────────────────────────────────────

const STATUS_STYLES = {
  healthy:  { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400', dot: 'bg-green-500', border: 'border-green-300 dark:border-green-700' },
  degraded: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-400', dot: 'bg-yellow-500 animate-pulse', border: 'border-yellow-300 dark:border-yellow-700' },
  critical: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400', dot: 'bg-red-500 animate-pulse', border: 'border-red-300 dark:border-red-700' },
  unknown:  { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-500 dark:text-gray-400', dot: 'bg-gray-500', border: 'border-gray-300 dark:border-gray-600' },
};

const JOB_LABELS = {
  alert_checker: 'Alert Checker',
  signal_checker: 'Signal Checker',
  mri_calculator: 'MRI Calculator',
  market_snapshot_capture: 'Market Snapshots',
  catalyst_calculator: 'Catalyst Calculator',
  position_monitor: 'Position Monitor',
  bot_daily_reset: 'Bot Daily Reset',
  bot_health_check: 'Bot Health Check',
  auto_scan: 'Auto Scan',
  health_alert: 'Health Alert',
};

const JOB_INTERVALS = {
  alert_checker: '5 min',
  signal_checker: '5 min',
  mri_calculator: '15 min',
  market_snapshot_capture: '30 min',
  catalyst_calculator: '60 min',
  position_monitor: '1 min',
  bot_daily_reset: '9:30 ET',
  bot_health_check: '5 min',
  auto_scan: '30 min',
  health_alert: '10 min',
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatRelativeTime(isoStr) {
  if (!isoStr) return '—';
  try {
    const date = new Date(isoStr + (isoStr.endsWith('Z') ? '' : 'Z'));
    const now = new Date();
    const diffSec = Math.floor((now - date) / 1000);

    if (diffSec < 0) return 'just now';
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  } catch {
    return '—';
  }
}

function formatUptime(seconds) {
  if (!seconds || seconds <= 0) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function formatDuration(sec) {
  if (sec == null) return '—';
  if (sec < 1) return `${(sec * 1000).toFixed(0)}ms`;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  return `${(sec / 60).toFixed(1)}m`;
}

// ── Status Dot ───────────────────────────────────────────────────────────────

function StatusDot({ ok, className = '' }) {
  return (
    <span className={`inline-block w-3 h-3 rounded-full ${ok ? 'bg-green-500' : 'bg-red-500 animate-pulse'} ${className}`} />
  );
}

// ── Dependency Card ──────────────────────────────────────────────────────────

function DepCard({ name, info }) {
  const ok = info?.ok;
  const icon = {
    database: '🗄️',
    redis: '⚡',
    alpaca: '🦙',
    scheduler: '⏰',
  }[name] || '📦';

  return (
    <div className={`rounded-xl border p-4 ${ok ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20' : 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20'}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <span className="font-medium text-gray-900 dark:text-gray-100 capitalize">{name}</span>
        </div>
        <StatusDot ok={ok} />
      </div>
      {info?.latency_ms != null && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Latency: <span className={info.latency_ms > 1000 ? 'text-yellow-500' : 'text-green-500'}>{info.latency_ms.toFixed(0)}ms</span>
        </p>
      )}
      {info?.job_count != null && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Jobs: {info.job_count} {info.running ? '(running)' : '(stopped)'}
        </p>
      )}
      {info?.market_open != null && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Market: {info.market_open ? '🟢 Open' : '🔴 Closed'}
        </p>
      )}
      {info?.error && (
        <p className="text-xs text-red-500 mt-1 truncate" title={info.error}>
          {info.error}
        </p>
      )}
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function Health() {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [forceLoading, setForceLoading] = useState(false);

  const fetchDashboard = useCallback(async () => {
    try {
      const resp = await apiClient.get('/api/v1/health/dashboard');
      setDashboard(resp.data);
      setError(null);
    } catch (err) {
      if (loading) {
        setError('Failed to load health data: ' + (err.message || 'Unknown error'));
      }
    } finally {
      setLoading(false);
    }
  }, [loading]);

  const forceCheck = useCallback(async () => {
    setForceLoading(true);
    try {
      const resp = await apiClient.post('/api/v1/health/check');
      setDashboard(resp.data);
      setError(null);
    } catch (err) {
      setError('Force check failed: ' + (err.message || 'Unknown error'));
    } finally {
      setForceLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchDashboard();
  }, []);

  // Auto-refresh polling
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchDashboard, 15000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchDashboard]);

  // Derived values
  const overall = dashboard?.overall_status || 'unknown';
  const style = STATUS_STYLES[overall] || STATUS_STYLES.unknown;
  const deps = dashboard?.dependencies || {};
  const jobs = dashboard?.scheduler_jobs || {};
  const autoScan = dashboard?.auto_scan || {};
  const bot = dashboard?.trading_bot || {};
  const telegram = dashboard?.telegram || {};

  // Sort jobs: overdue first, then errored, then by name
  const sortedJobs = Object.entries(jobs).sort(([, a], [, b]) => {
    if (a?.is_overdue && !b?.is_overdue) return -1;
    if (!a?.is_overdue && b?.is_overdue) return 1;
    if (a?.last_status === 'error' && b?.last_status !== 'error') return -1;
    if (a?.last_status !== 'error' && b?.last_status === 'error') return 1;
    return 0;
  });

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 py-6 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">

        {/* ── A. Overall Status Banner ──────────────────────────────── */}
        <div className={`rounded-xl border p-5 ${style.bg} ${style.border}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <span className={`inline-block w-4 h-4 rounded-full ${style.dot}`} />
              <div>
                <h1 className={`text-2xl font-bold ${style.text}`}>
                  System {overall.charAt(0).toUpperCase() + overall.slice(1)}
                </h1>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                  Uptime: {formatUptime(dashboard?.uptime_seconds)}
                  {dashboard?.checked_at && ` · Last check: ${formatRelativeTime(dashboard.checked_at)}`}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-500 dark:text-gray-400">Auto-refresh</span>
              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  autoRefresh ? 'bg-green-600' : 'bg-gray-600'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    autoRefresh ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
              <button
                onClick={forceCheck}
                disabled={forceLoading}
                className={`px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors ${forceLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                {forceLoading ? 'Checking...' : 'Force Check'}
              </button>
            </div>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mr-3" />
            <span className="text-gray-400">Loading health data...</span>
          </div>
        ) : (
          <>
            {/* ── B. Dependencies Grid ──────────────────────────────── */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {['database', 'redis', 'alpaca', 'scheduler'].map((name) => (
                <DepCard key={name} name={name} info={deps[name]} />
              ))}
            </div>

            {/* ── C. Scheduler Jobs Table ───────────────────────────── */}
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  Scheduler Jobs ({Object.keys(jobs).length})
                </h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 dark:bg-gray-700/50 text-gray-500 dark:text-gray-400 text-xs uppercase">
                      <th className="px-4 py-2 text-left">Job</th>
                      <th className="px-4 py-2 text-left">Interval</th>
                      <th className="px-4 py-2 text-left">Last Run</th>
                      <th className="px-4 py-2 text-left">Duration</th>
                      <th className="px-4 py-2 text-center">Status</th>
                      <th className="px-4 py-2 text-center">Runs</th>
                      <th className="px-4 py-2 text-center">Errors</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
                    {sortedJobs.map(([jobId, job]) => {
                      const isOverdue = job?.is_overdue;
                      const isError = job?.last_status === 'error';
                      const rowBg = isOverdue
                        ? 'bg-yellow-50 dark:bg-yellow-900/10'
                        : isError
                        ? 'bg-red-50 dark:bg-red-900/10'
                        : '';

                      return (
                        <tr key={jobId} className={`${rowBg} hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors`}>
                          <td className="px-4 py-2.5 text-gray-900 dark:text-gray-100 font-medium">
                            {JOB_LABELS[jobId] || jobId}
                          </td>
                          <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400">
                            {JOB_INTERVALS[jobId] || '—'}
                          </td>
                          <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400">
                            {formatRelativeTime(job?.last_run)}
                          </td>
                          <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400">
                            {formatDuration(job?.last_duration_sec)}
                          </td>
                          <td className="px-4 py-2.5 text-center">
                            {isOverdue ? (
                              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-200 dark:bg-yellow-800 text-yellow-800 dark:text-yellow-200">
                                OVERDUE
                              </span>
                            ) : job?.last_status === 'ok' ? (
                              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200">
                                OK
                              </span>
                            ) : job?.last_status === 'error' ? (
                              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-200 dark:bg-red-800 text-red-800 dark:text-red-200">
                                ERROR
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300">
                                {job?.last_status?.toUpperCase() || 'PENDING'}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-2.5 text-center text-gray-500 dark:text-gray-400">
                            {job?.success_count || 0}
                          </td>
                          <td className="px-4 py-2.5 text-center">
                            <span className={job?.error_count > 0 ? 'text-red-500 font-medium' : 'text-gray-500 dark:text-gray-400'}>
                              {job?.error_count || 0}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* ── D & E. Auto-Scan + Trading Bot Cards ─────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

              {/* Auto-Scan Health */}
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
                  🔍 Auto-Scan Health
                </h2>
                <div className="space-y-2.5">
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Enabled</span>
                    <span className={`text-sm font-medium ${autoScan.enabled ? 'text-green-500' : 'text-gray-500'}`}>
                      {autoScan.enabled ? '✓ ON' : '✗ OFF'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Smart Scan</span>
                    <span className={`text-sm font-medium ${autoScan.smart_scan_enabled ? 'text-blue-500' : 'text-gray-500'}`}>
                      {autoScan.smart_scan_enabled ? '✓ ON' : '✗ OFF'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Presets</span>
                    <span className="text-sm text-gray-900 dark:text-gray-100">
                      {autoScan.presets?.length > 0 ? autoScan.presets.join(', ') : '—'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Last Run</span>
                    <span className="text-sm text-gray-900 dark:text-gray-100">
                      {formatRelativeTime(autoScan.last_run)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Last Duration</span>
                    <span className="text-sm text-gray-900 dark:text-gray-100">
                      {formatDuration(autoScan.last_duration_sec)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Last Status</span>
                    <span className={`text-sm font-medium ${
                      autoScan.last_status === 'ok' ? 'text-green-500' :
                      autoScan.last_status === 'error' ? 'text-red-500' : 'text-gray-500'
                    }`}>
                      {autoScan.last_status?.toUpperCase() || 'UNKNOWN'}
                    </span>
                  </div>
                  {autoScan.is_overdue && (
                    <div className="mt-2 px-3 py-1.5 bg-yellow-100 dark:bg-yellow-900/30 border border-yellow-300 dark:border-yellow-700 rounded-lg text-yellow-700 dark:text-yellow-300 text-xs">
                      ⚠️ Auto-scan is overdue
                    </div>
                  )}
                </div>
              </div>

              {/* Trading Bot Health */}
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
                <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
                  🤖 Trading Bot Health
                </h2>
                <div className="space-y-2.5">
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Status</span>
                    <span className={`text-sm font-medium ${
                      bot.status === 'running' ? 'text-green-500' :
                      bot.status === 'paused' ? 'text-yellow-500' :
                      bot.status === 'halted' ? 'text-red-500' : 'text-gray-500'
                    }`}>
                      {bot.status?.toUpperCase() || 'UNKNOWN'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Circuit Breaker</span>
                    <span className={`text-sm font-medium ${
                      bot.circuit_breaker === 'none' ? 'text-green-500' :
                      bot.circuit_breaker === 'warning' ? 'text-yellow-500' : 'text-red-500'
                    }`}>
                      {bot.circuit_breaker || 'none'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Consecutive Errors</span>
                    <span className={`text-sm font-medium ${
                      bot.consecutive_errors >= 3 ? 'text-red-500' : 'text-gray-900 dark:text-gray-100'
                    }`}>
                      {bot.consecutive_errors || 0}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Open Positions</span>
                    <span className="text-sm text-gray-900 dark:text-gray-100">
                      {bot.open_positions || 0}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400">Last Health Check</span>
                    <span className="text-sm text-gray-900 dark:text-gray-100">
                      {formatRelativeTime(bot.last_health_check)}
                    </span>
                  </div>
                  {bot.last_error && (
                    <div className="mt-2 px-3 py-1.5 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-700 rounded-lg text-red-700 dark:text-red-300 text-xs truncate" title={bot.last_error}>
                      ❌ {bot.last_error}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* ── F. Telegram Status ───────────────────────────────── */}
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center gap-4">
                <span className="text-lg">📬</span>
                <div className="flex-1">
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Telegram Alerts</span>
                  <span className="ml-3 text-xs text-gray-500 dark:text-gray-400">
                    {telegram.configured
                      ? telegram.running
                        ? `✓ Running (${telegram.allowed_users || 0} users)`
                        : '⚠️ Configured but not running'
                      : '✗ Not configured'}
                  </span>
                </div>
                <StatusDot ok={telegram.running} />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
