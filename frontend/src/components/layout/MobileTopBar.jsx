/**
 * Mobile Top Bar — compact header shown only on mobile (<768px).
 * Contains hamburger menu button, app title, and dark mode toggle.
 */
import useSidebarStore from '../../stores/sidebarStore';
import useThemeStore from '../../stores/themeStore';

export default function MobileTopBar() {
  const openMobile = useSidebarStore(s => s.openMobile);
  const darkMode = useThemeStore(s => s.darkMode);
  const toggleDarkMode = useThemeStore(s => s.toggleDarkMode);

  return (
    <div className="md:hidden fixed top-0 left-0 right-0 h-12 bg-gray-800 text-white flex items-center justify-between px-3 z-30 shadow-lg">
      {/* Hamburger button */}
      <button
        onClick={openMobile}
        className="p-2 -ml-1 rounded-lg hover:bg-gray-700 transition-colors"
        aria-label="Open navigation menu"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* App title */}
      <div className="flex items-center gap-2">
        <span className="text-lg">📈</span>
        <span className="font-bold text-sm">LEAPS Trader</span>
      </div>

      {/* Dark mode toggle */}
      <button
        onClick={toggleDarkMode}
        className="p-2 -mr-1 rounded-lg hover:bg-gray-700 transition-colors"
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
  );
}
