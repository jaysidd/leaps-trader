/**
 * useFullAutoLock — Centralized hook for Full Auto lockdown state.
 *
 * Reads bot store (status + config) and returns lockdown flags.
 * When execution_mode === 'full_auto', most mutation UI is disabled
 * so the user can't interfere with the automated pipeline.
 */
import useBotStore from '../stores/botStore';

export default function useFullAutoLock() {
  const config = useBotStore((s) => s.config);
  const status = useBotStore((s) => s.status);

  // Either status (polled every 10s) or config (fetched on demand) can tell us the mode
  const executionMode =
    status?.execution_mode || config?.execution_mode || 'signal_only';
  const botRunning = status?.status === 'running' || status?.status === 'paused';

  const isFullAuto = executionMode === 'full_auto';

  return {
    /** True when execution_mode is full_auto */
    isFullAuto,
    /** True when any lockdown is active (same as isFullAuto for now) */
    isLocked: isFullAuto,
    /** Lock screener scan triggers */
    lockScreener: isFullAuto,
    /** Lock manual trade buttons (Trade / SendToBot) */
    lockManualTrades: isFullAuto,
    /** Lock trading parameter changes — only when bot is also running */
    lockTradingParams: isFullAuto && botRunning,
    /** Lock Paper/Live account toggle */
    lockAccountToggle: isFullAuto && botRunning,
  };
}
