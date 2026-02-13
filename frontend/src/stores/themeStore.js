/**
 * Theme Store - Manages dark/light mode for the app
 *
 * @typedef {Object} ThemeState
 * @property {boolean} darkMode - Whether dark mode is active
 * @property {() => void} toggleDarkMode - Toggle between dark/light mode
 * @property {(enabled: boolean) => void} setDarkMode - Set dark mode directly
 * @property {() => void} initializeTheme - Apply theme class on app load
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/** @type {import('zustand').UseBoundStore<import('zustand').StoreApi<ThemeState>>} */
const useThemeStore = create(
  persist(
    (set, get) => ({
      /** @type {boolean} */
      darkMode: true,

      /** Toggle dark mode */
      toggleDarkMode: () => {
        const newMode = !get().darkMode;
        set({ darkMode: newMode });

        // Update document class for Tailwind dark mode
        if (newMode) {
          document.documentElement.classList.add('dark');
        } else {
          document.documentElement.classList.remove('dark');
        }
      },

      // Set dark mode directly
      setDarkMode: (enabled) => {
        set({ darkMode: enabled });

        if (enabled) {
          document.documentElement.classList.add('dark');
        } else {
          document.documentElement.classList.remove('dark');
        }
      },

      // Initialize theme on app load
      initializeTheme: () => {
        const { darkMode } = get();
        if (darkMode) {
          document.documentElement.classList.add('dark');
        } else {
          document.documentElement.classList.remove('dark');
        }
      },
    }),
    {
      name: 'leaps-theme', // localStorage key
      partialize: (state) => ({ darkMode: state.darkMode }),
    }
  )
);

export default useThemeStore;
