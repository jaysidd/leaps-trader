/**
 * FullAutoBanner — Reusable amber/yellow lockdown banner for Full Auto mode.
 *
 * Shows a lock icon, custom message, and link to the Autopilot page (exit hatch).
 * Use variant="info" on the Autopilot page itself for a green "active" banner.
 */
import { Link } from 'react-router-dom';

export default function FullAutoBanner({ message, variant = 'warning' }) {
  const isInfo = variant === 'info';

  return (
    <div
      className={`flex items-center gap-3 px-4 py-3 rounded-lg border text-sm font-medium ${
        isInfo
          ? 'bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-700 text-green-800 dark:text-green-300'
          : 'bg-amber-50 dark:bg-amber-900/20 border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-300'
      }`}
    >
      <svg
        className={`w-5 h-5 flex-shrink-0 ${isInfo ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 15v.01M12 12V8m0 13a9 9 0 110-18 9 9 0 010 18z"
        />
      </svg>
      <span className="flex-1">
        {message || 'Full Auto mode is active. Manual actions are locked.'}
      </span>
      {!isInfo && (
        <Link
          to="/autopilot"
          className="flex-shrink-0 px-3 py-1 rounded-md text-xs font-semibold bg-amber-200 dark:bg-amber-800 text-amber-900 dark:text-amber-100 hover:bg-amber-300 dark:hover:bg-amber-700 transition-colors"
        >
          Go to Autopilot
        </Link>
      )}
    </div>
  );
}
