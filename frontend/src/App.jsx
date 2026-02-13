/**
 * Main App component with routing
 *
 * Layout: Fixed left sidebar + scrollable main content area.
 * Mobile: Hamburger top bar + slide-out drawer.
 */
import { useEffect, Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

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
const Logs = lazy(() => import('./pages/Logs'));
const Health = lazy(() => import('./pages/Health'));

// Layout components (always loaded)
import ErrorBoundary from './components/ErrorBoundary';
import LoginGate from './components/LoginGate';
import Sidebar from './components/layout/Sidebar';
import MobileTopBar from './components/layout/MobileTopBar';
import BotStatusBar from './components/bot/BotStatusBar';
import { NewsTicker } from './components/command-center';
import useSidebarStore from './stores/sidebarStore';
import useThemeStore from './stores/themeStore';

function App() {
  const initializeTheme = useThemeStore(state => state.initializeTheme);
  const isExpanded = useSidebarStore(state => state.isExpanded);

  // Initialize theme on app load
  useEffect(() => {
    initializeTheme();
  }, []);

  return (
    <LoginGate>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-100 dark:bg-gray-900 transition-colors duration-200">
          {/* Fixed left sidebar (desktop: always visible, mobile: drawer) */}
          <Sidebar />

          {/* Mobile top bar — hamburger + title + dark toggle */}
          <MobileTopBar />

          {/* Main content area — offset by sidebar width */}
          <main
            className={[
              'min-h-screen transition-all duration-300 ease-in-out',
              // Mobile: top padding for MobileTopBar (h-12 = 48px), no left margin
              'pt-12 md:pt-0',
              // Desktop: left margin matches sidebar width
              isExpanded ? 'md:ml-60' : 'md:ml-16',
            ].join(' ')}
          >
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
                  <Route path="/logs" element={<ErrorBoundary><Logs /></ErrorBoundary>} />
                  <Route path="/health" element={<ErrorBoundary><Health /></ErrorBoundary>} />
                  <Route path="/settings" element={<ErrorBoundary><Settings /></ErrorBoundary>} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          </main>
        </div>
      </BrowserRouter>
    </LoginGate>
  );
}

export default App;
