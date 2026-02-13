/**
 * BotStatusBar — persistent status strip shown when bot is active
 * Shows: bot status, daily P&L, open positions, circuit breaker level
 */
import { useEffect } from 'react';
import useBotStore from '../../stores/botStore';

const STATUS_COLORS = {
  running: 'bg-green-500',
  paused: 'bg-yellow-500',
  halted: 'bg-red-500',
  stopped: 'bg-gray-400',
};

const CB_LABELS = {
  none: null,
  warning: { text: 'CB: WARNING', color: 'text-yellow-300' },
  paused: { text: 'CB: PAUSED', color: 'text-orange-300' },
  halted: { text: 'CB: HALTED', color: 'text-red-300' },
};

export default function BotStatusBar() {
  const status = useBotStore(state => state.status);
  const fetchStatus = useBotStore(state => state.fetchStatus);
  const startPolling = useBotStore(state => state.startPolling);
  const stopPolling = useBotStore(state => state.stopPolling);
  const emergencyStop = useBotStore(state => state.emergencyStop);

  useEffect(() => {
    fetchStatus();
    // Only start polling if bot might be active
    const checkAndPoll = async () => {
      const currentStatus = useBotStore.getState().status;
      if (currentStatus && currentStatus.status !== 'stopped') {
        startPolling(10000);
      }
    };
    checkAndPoll();
    return () => stopPolling();
  }, []);

  // Don't show if bot is stopped
  if (!status || status.status === 'stopped') return null;

  const pl = status.daily_pl || 0;
  const plPct = status.daily_pl_pct || 0;
  const plColor = pl >= 0 ? 'text-green-300' : 'text-red-300';
  const cb = CB_LABELS[status.circuit_breaker] || null;

  return (
    <div className="bg-gray-800 dark:bg-gray-900 text-white text-sm px-4 py-2 flex items-center justify-between border-b border-gray-700">
      <div className="flex items-center gap-4">
        {/* Status dot */}
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${STATUS_COLORS[status.status] || 'bg-gray-400'} ${status.status === 'running' ? 'animate-pulse' : ''}`} />
          <span className="font-medium">{status.status?.toUpperCase()}</span>
          <span className="text-gray-400">|</span>
          <span className="text-gray-400">{status.paper_mode ? 'PAPER' : 'LIVE'}</span>
          <span className="text-gray-400">|</span>
          <span className="text-gray-400">{status.execution_mode?.replace('_', ' ').toUpperCase()}</span>
        </div>

        {/* Circuit breaker */}
        {cb && (
          <>
            <span className="text-gray-400">|</span>
            <span className={`font-bold ${cb.color}`}>{cb.text}</span>
          </>
        )}
      </div>

      <div className="flex items-center gap-6">
        {/* Daily P&L */}
        <div className="flex items-center gap-1">
          <span className="text-gray-400">P&L:</span>
          <span className={`font-mono font-medium ${plColor}`}>
            ${pl >= 0 ? '+' : ''}{pl.toFixed(2)} ({plPct >= 0 ? '+' : ''}{plPct.toFixed(1)}%)
          </span>
        </div>

        {/* Trades */}
        <div className="flex items-center gap-1">
          <span className="text-gray-400">Trades:</span>
          <span className="font-mono">{status.daily_trades}</span>
          <span className="text-gray-500 text-xs">
            ({status.daily_wins}W / {status.daily_losses}L)
          </span>
        </div>

        {/* Positions */}
        <div className="flex items-center gap-1">
          <span className="text-gray-400">Positions:</span>
          <span className="font-mono">{status.open_positions}</span>
          {(status.open_stocks > 0 || status.open_options > 0) && (
            <span className="text-gray-500 text-xs">
              ({status.open_stocks}S / {status.open_options}O)
            </span>
          )}
        </div>

        {/* Equity */}
        <div className="flex items-center gap-1">
          <span className="text-gray-400">Equity:</span>
          <span className="font-mono">${(status.equity || 0).toLocaleString()}</span>
        </div>

        {/* Emergency Stop Button */}
        <button
          onClick={() => {
            if (window.confirm('EMERGENCY STOP: Cancel all orders and close all positions?')) {
              emergencyStop(true);
            }
          }}
          className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white text-xs font-bold rounded transition-colors"
        >
          KILL SWITCH
        </button>
      </div>
    </div>
  );
}
