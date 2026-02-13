/**
 * Main App component with routing
 */
import { useEffect, Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';

// Lazy-loaded page components (route-level code splitting)
const Screener = lazy(() => import('./pages/Screener'));
const Settings = lazy(() => import('./pages/Settings'));
const CommandCenter = lazy(() => import('./pages/CommandCenter'));
const SignalQueue = lazy(() => import('./pages/SignalQueue'));
const HeatMap = lazy(() => import('./pages/HeatMap'));
const SavedScans = lazy(() => import('./pages/SavedScans'));
const Portfolio = lazy(() => import('./pages/Portfolio'));
const MacroIntelligence = lazy(() => import('./pages/MacroIntelligence'));
const TradeJournal = lazy(() => import('./pages/TradeJournal'));
const BotPerformance = lazy(() => import('./pages/BotPerformance'));
const Backtesting = lazy(() => import('./pages/Backtesting'));
const Autopilot = lazy(() => import('./pages/Autopilot'));

// Layout components (always loaded)
import ErrorBoundary from './components/ErrorBoundary';
import BotStatusBar from './components/bot/BotStatusBar';
import { NewsTicker } from './components/command-center';
import useScreenerStore from './stores/screenerStore';
import useSignalsStore from './stores/signalsStore';
import useThemeStore from './stores/themeStore';

function Navigation() {
  // Get scan status from store to show indicator (individual selectors to avoid unnecessary re-renders)
  const loading = useScreenerStore(state => state.loading);
  const scanProgress = useScreenerStore(state => state.scanProgress);
  const results = useScreenerStore(state => state.results);
  const unreadCount = useSignalsStore(state => state.unreadCount);
  const startPolling = useSignalsStore(state => state.startPolling);
  const stopPolling = useSignalsStore(state => state.stopPolling);
  const darkMode = useThemeStore(state => state.darkMode);
  const toggleDarkMode = useThemeStore(state => state.toggleDarkMode);

  // Start polling for unread signals on mount
  useEffect(() => {
    startPolling(30000); // Poll every 30 seconds
    return () => stopPolling();
  }, []);

  return (
    <nav className="bg-gray-800 text-white shadow-lg">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between h-14">
          {/* Logo/Brand */}
          <NavLink to="/command-center" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <span className="text-xl">📈</span>
            <span className="font-bold text-lg">LEAPS Trader</span>
          </NavLink>

          {/* Navigation Links */}
          <div className="flex items-center space-x-1">
            <NavLink
              to="/command-center"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">🎯</span>
              Command Center
            </NavLink>
            <NavLink
              to="/screener"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors relative ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">🔍</span>
              Screener
              {/* Scan status indicator */}
              {loading && (
                <span className="absolute -top-1 -right-1 flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
                </span>
              )}
              {!loading && results.length > 0 && (
                <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-green-500 text-[10px] font-bold">
                  {results.length > 99 ? '99+' : results.length}
                </span>
              )}
            </NavLink>
            <NavLink
              to="/saved-scans"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">📋</span>
              Saved Scans
            </NavLink>
            <NavLink
              to="/signals"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors relative ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">🔔</span>
              Signals
              {/* Unread signals badge */}
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold animate-pulse">
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              )}
            </NavLink>
            <NavLink
              to="/portfolio"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">💼</span>
              Portfolio
            </NavLink>
            <NavLink
              to="/macro-intelligence"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">🧠</span>
              Macro Intel
            </NavLink>
            <NavLink
              to="/heatmap"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">🗺️</span>
              Heat Map
            </NavLink>
            <NavLink
              to="/trade-journal"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">📒</span>
              Journal
            </NavLink>
            <NavLink
              to="/bot-performance"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">📊</span>
              Bot Stats
            </NavLink>
            <NavLink
              to="/autopilot"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">🤖</span>
              Autopilot
            </NavLink>
            <NavLink
              to="/backtesting"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">🔬</span>
              Backtest
            </NavLink>
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <span className="mr-1">⚙️</span>
              Settings
            </NavLink>
          </div>

          {/* Right side: Scan Progress + Dark Mode Toggle */}
          <div className="flex items-center gap-4">
            {/* Scan Progress Mini-indicator */}
            {loading && scanProgress && (
              <div className="hidden md:flex items-center gap-2 text-sm text-blue-300">
                <div className="animate-pulse">
                  <div className="w-2 h-2 bg-blue-400 rounded-full"></div>
                </div>
                <span>
                  Scanning: {scanProgress.processed}/{scanProgress.total}
                  {scanProgress.passed > 0 && ` • ${scanProgress.passed} found`}
                </span>
              </div>
            )}

            {/* Dark Mode Toggle */}
            <button
              onClick={toggleDarkMode}
              className="p-2 rounded-lg hover:bg-gray-700 transition-colors"
              title={darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            >
              {darkMode ? (
                <svg className="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"
                    clipRule="evenodd"
                  />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}

function App() {
  const initializeTheme = useThemeStore(state => state.initializeTheme);

  // Initialize theme on app load
  useEffect(() => {
    initializeTheme();
  }, []);

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors duration-200">
        <Navigation />
        {/* Bot Status Bar — visible when bot is running */}
        <BotStatusBar />
        {/* Global News Ticker - appears on all pages */}
        <NewsTicker speed={45} pauseOnHover={true} showSource={true} maxItems={15} />
        <ErrorBoundary>
          <Suspense fallback={<div className="flex items-center justify-center h-screen"><div className="text-gray-400">Loading...</div></div>}>
            {/* ┌──────────────────────────────────────────────────────────┐
                │ DOC UPDATE: Adding/removing a route here? Also update:   │
                │   ARCHITECTURE.md → "Frontend Pages" table + Changelog   │
                │   .claude/CLAUDE.md → "Key Entry Points" if major page   │
                └──────────────────────────────────────────────────────────┘ */}
            <Routes>
              <Route path="/" element={<ErrorBoundary><CommandCenter /></ErrorBoundary>} />
              <Route path="/command-center" element={<ErrorBoundary><CommandCenter /></ErrorBoundary>} />
              <Route path="/screener" element={<ErrorBoundary><Screener /></ErrorBoundary>} />
              <Route path="/saved-scans" element={<ErrorBoundary><SavedScans /></ErrorBoundary>} />
              <Route path="/signals" element={<ErrorBoundary><SignalQueue /></ErrorBoundary>} />
              <Route path="/portfolio" element={<ErrorBoundary><Portfolio /></ErrorBoundary>} />
              <Route path="/macro-intelligence" element={<ErrorBoundary><MacroIntelligence /></ErrorBoundary>} />
              <Route path="/heatmap" element={<ErrorBoundary><HeatMap /></ErrorBoundary>} />
              <Route path="/trade-journal" element={<ErrorBoundary><TradeJournal /></ErrorBoundary>} />
              <Route path="/bot-performance" element={<ErrorBoundary><BotPerformance /></ErrorBoundary>} />
              <Route path="/autopilot" element={<ErrorBoundary><Autopilot /></ErrorBoundary>} />
              <Route path="/backtesting" element={<ErrorBoundary><Backtesting /></ErrorBoundary>} />
              <Route path="/settings" element={<ErrorBoundary><Settings /></ErrorBoundary>} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </div>
    </BrowserRouter>
  );
}

export default App;
