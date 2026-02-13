/**
 * Sidebar Store — manages sidebar expanded/collapsed state + mobile drawer
 * Desktop: toggles between expanded (icons+labels) and collapsed (icons only)
 * Mobile: slide-out drawer overlay, auto-closes on navigation
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const useSidebarStore = create(
  persist(
    (set, get) => ({
      // Desktop: whether sidebar shows labels (true) or just icons (false)
      isExpanded: true,

      // Mobile: whether the drawer overlay is open
      isMobileOpen: false,

      toggleExpanded: () => set({ isExpanded: !get().isExpanded }),
      setExpanded: (val) => set({ isExpanded: val }),

      openMobile: () => set({ isMobileOpen: true }),
      closeMobile: () => set({ isMobileOpen: false }),
      toggleMobile: () => set({ isMobileOpen: !get().isMobileOpen }),
    }),
    {
      name: 'leaps-sidebar', // localStorage key
      // Only persist desktop expanded state; mobile drawer always starts closed
      partialize: (state) => ({ isExpanded: state.isExpanded }),
    }
  )
);

export default useSidebarStore;
