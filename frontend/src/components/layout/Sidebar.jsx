/**
 * Sidebar — collapsible left navigation panel.
 *
 * Desktop (≥768px): Fixed left sidebar, toggleable between expanded (icons+labels)
 *   and collapsed (icons only). Width: 240px expanded, 64px collapsed.
 * Mobile (<768px): Slide-out drawer with backdrop overlay.
 *   Always 240px wide. Auto-closes on nav click.
 */
import { useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import useSidebarStore from '../../stores/sidebarStore';
import useThemeStore from '../../stores/themeStore';
import useScreenerStore from '../../stores/screenerStore';
import useSignalsStore from '../../stores/signalsStore';

// ── Navigation structure ────────────────────────────────────────────────────

const NAV_SECTIONS = [
  {
    label: 'Dashboard',
    items: [
      { to: '/command-center', icon: '🎯', label: 'Command Center' },
    ],
  },
  {
    label: 'Trading',
    items: [
      { to: '/screener', icon: '🔍', label: 'Screener', badge: 'screener' },
      { to: '/saved-scans', icon: '📋', label: 'Saved Scans' },
      { to: '/signals', icon: '🔔', label: 'Signals', badge: 'signals' },
      { to: '/autopilot', icon: '🤖', label: 'Autopilot' },
    ],
  },
  {
    label: 'Analysis',
    items: [
      { to: '/portfolio', icon: '💼', label: 'Portfolio' },
      { to: '/macro-intelligence', icon: '🧠', label: 'Macro Intel' },
      { to: '/heatmap', icon: '🗺️', label: 'Heat Map' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { to: '/trade-journal', icon: '📒', label: 'Journal' },
      { to: '/bot-performance', icon: '📊', label: 'Bot Stats' },
      { to: '/backtesting', icon: '🔬', label: 'Backtest' },
      { to: '/health', icon: '🏥', label: 'Health' },
      { to: '/logs', icon: '📜', label: 'Logs' },
    ],
  },
];

const SETTINGS_ITEM = { to: '/settings', icon: '⚙️', label: 'Settings' };


// ── Badge sub-component ─────────────────────────────────────────────────────

function NavBadge({ type }) {
  const loading = useScreenerStore(s => s.loading);
  const resultsCount = useScreenerStore(s => s.results?.length || 0);
  const unreadCount = useSignalsStore(s => s.unreadCount);

  if (type === 'screener') {
    if (loading) {
      return (
        <span className="absolute top-1 right-1 flex h-3 w-3">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500" />
        </span>
      );
    }
    if (resultsCount > 0) {
      return (
        <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-green-500 text-[9px] font-bold text-white">
          {resultsCount > 99 ? '99+' : resultsCount}
        </span>
      );
    }
  }

  if (type === 'signals' && unreadCount > 0) {
    return (
      <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white animate-pulse">
        {unreadCount > 99 ? '99+' : unreadCount}
      </span>
    );
  }

  return null;
}


// ── Main Sidebar ────────────────────────────────────────────────────────────

export default function Sidebar() {
  const isExpanded = useSidebarStore(s => s.isExpanded);
  const isMobileOpen = useSidebarStore(s => s.isMobileOpen);
  const closeMobile = useSidebarStore(s => s.closeMobile);
  const toggleExpanded = useSidebarStore(s => s.toggleExpanded);
  const darkMode = useThemeStore(s => s.darkMode);
  const toggleDarkMode = useThemeStore(s => s.toggleDarkMode);
  const location = useLocation();

  // Signal polling (migrated from old Navigation component)
  const startPolling = useSignalsStore(s => s.startPolling);
  const stopPolling = useSignalsStore(s => s.stopPolling);

  useEffect(() => {
    startPolling(30000);
    return () => stopPolling();
  }, []);

  // Close mobile drawer on route change
  useEffect(() => {
    closeMobile();
  }, [location.pathname]);

  // Scan progress for expanded sidebar
  const loading = useScreenerStore(s => s.loading);
  const scanProgress = useScreenerStore(s => s.scanProgress);

  // Nav link classes
  const linkClass = (isActive) => {
    const base = 'relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors';
    if (isActive) {
      return `${base} bg-gray-900 text-white`;
    }
    return `${base} text-gray-300 hover:bg-gray-700 hover:text-white`;
  };

  // Collapsed link classes (icon only)
  const collapsedLinkClass = (isActive) => {
    const base = 'relative flex items-center justify-center w-10 h-10 rounded-lg transition-colors mx-auto';
    if (isActive) {
      return `${base} bg-gray-900 text-white`;
    }
    return `${base} text-gray-300 hover:bg-gray-700 hover:text-white`;
  };

  return (
    <>
      {/* Mobile backdrop overlay */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden transition-opacity"
          onClick={closeMobile}
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={[
          'fixed top-0 left-0 h-full bg-gray-800 text-white z-40',
          'flex flex-col',
          'transition-all duration-300 ease-in-out',
          'overflow-hidden',
          // Mobile: slide in/out
          isMobileOpen ? 'translate-x-0' : '-translate-x-full',
          // Desktop: always visible
          'md:translate-x-0',
          // Width: mobile always 240px, desktop depends on expanded state
          'w-60',
          isExpanded ? 'md:w-60' : 'md:w-16',
        ].join(' ')}
      >
        {/* ── Logo area ──────────────────────────────────────────────── */}
        <div className={`flex items-center h-14 border-b border-gray-700 shrink-0 ${isExpanded ? 'px-4 gap-3' : 'justify-center px-2 md:px-0'}`}>
          <NavLink to="/command-center" className="flex items-center gap-2 hover:opacity-80 transition-opacity overflow-hidden">
            <span className="text-xl shrink-0">📈</span>
            <span className={`font-bold text-lg whitespace-nowrap transition-opacity duration-200 ${isExpanded ? 'opacity-100' : 'md:opacity-0 md:w-0'}`}>
              LEAPS Trader
            </span>
          </NavLink>

          {/* Mobile close button */}
          <button
            onClick={closeMobile}
            className="md:hidden ml-auto p-1.5 rounded-lg hover:bg-gray-700 transition-colors"
            aria-label="Close menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* ── Scan progress (expanded only) ──────────────────────── */}
        {loading && scanProgress && isExpanded && (
          <div className="px-4 py-2 border-b border-gray-700 shrink-0">
            <div className="flex items-center gap-2 text-xs text-blue-300">
              <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse shrink-0" />
              <span className="truncate">
                Scanning: {scanProgress.processed}/{scanProgress.total}
                {scanProgress.passed > 0 && ` · ${scanProgress.passed} found`}
              </span>
            </div>
          </div>
        )}

        {/* ── Navigation sections ────────────────────────────────── */}
        <nav className="flex-1 overflow-y-auto overflow-x-hidden py-3 px-2 space-y-4">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label}>
              {/* Section header */}
              <div className={`px-2 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 whitespace-nowrap transition-opacity duration-200 ${isExpanded ? 'opacity-100' : 'md:opacity-0 md:h-0 md:mb-0 md:overflow-hidden'}`}>
                {section.label}
              </div>

              {/* Section items */}
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      isExpanded ? linkClass(isActive) : collapsedLinkClass(isActive)
                    }
                    title={!isExpanded ? item.label : undefined}
                  >
                    <span className={`text-lg shrink-0 ${isExpanded ? '' : 'mx-auto'}`}>{item.icon}</span>
                    {isExpanded && (
                      <span className="whitespace-nowrap overflow-hidden">{item.label}</span>
                    )}
                    {item.badge && <NavBadge type={item.badge} />}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* ── Bottom area: Settings, Dark Mode, Collapse ─────────── */}
        <div className="border-t border-gray-700 shrink-0">
          {/* Settings link */}
          <div className="px-2 py-2">
            <NavLink
              to={SETTINGS_ITEM.to}
              className={({ isActive }) =>
                isExpanded ? linkClass(isActive) : collapsedLinkClass(isActive)
              }
              title={!isExpanded ? SETTINGS_ITEM.label : undefined}
            >
              <span className={`text-lg shrink-0 ${isExpanded ? '' : 'mx-auto'}`}>{SETTINGS_ITEM.icon}</span>
              {isExpanded && (
                <span className="whitespace-nowrap overflow-hidden">{SETTINGS_ITEM.label}</span>
              )}
            </NavLink>
          </div>

          {/* Dark mode toggle */}
          <div className="px-2 pb-2">
            <button
              onClick={toggleDarkMode}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-gray-300 hover:bg-gray-700 hover:text-white transition-colors ${isExpanded ? '' : 'justify-center'}`}
              title={darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            >
              {darkMode ? (
                <svg className="w-5 h-5 text-yellow-400 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"
                    clipRule="evenodd"
                  />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-gray-400 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
                </svg>
              )}
              {isExpanded && (
                <span className="whitespace-nowrap">{darkMode ? 'Light Mode' : 'Dark Mode'}</span>
              )}
            </button>
          </div>

          {/* Desktop collapse/expand toggle */}
          <div className="hidden md:block px-2 pb-2">
            <button
              onClick={toggleExpanded}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
              title={isExpanded ? 'Collapse sidebar' : 'Expand sidebar'}
            >
              <svg
                className={`w-5 h-5 shrink-0 transition-transform duration-300 ${isExpanded ? '' : 'rotate-180'} ${isExpanded ? '' : 'mx-auto'}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7" />
              </svg>
              {isExpanded && (
                <span className="whitespace-nowrap">Collapse</span>
              )}
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
