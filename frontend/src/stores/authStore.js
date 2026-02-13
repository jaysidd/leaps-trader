/**
 * Auth Store — simple password gate for app access
 * Stores session token in localStorage for persistence across refreshes
 */
import { create } from 'zustand';
import { API_BASE_URL } from '../api/axios';

const TOKEN_KEY = 'leaps_auth_token';

const useAuthStore = create((set, get) => ({
  // State
  isAuthenticated: false,
  isProtected: null,    // null = checking, true = password required, false = open
  isChecking: true,
  error: null,

  /**
   * Check if the backend has password protection enabled.
   * Also validates any existing stored token.
   */
  checkAuth: async () => {
    set({ isChecking: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/auth/check`);
      const data = await res.json();

      if (!data.protected) {
        // No password required — let everyone in
        set({ isAuthenticated: true, isProtected: false, isChecking: false });
        return;
      }

      // Password is required — check if we have a valid stored token
      set({ isProtected: true });
      const storedToken = localStorage.getItem(TOKEN_KEY);
      if (storedToken) {
        // Validate token by making a test API call
        const testRes = await fetch(`${API_BASE_URL}/api/v1/settings/all`, {
          headers: { 'X-App-Token': storedToken },
        });
        if (testRes.ok) {
          set({ isAuthenticated: true, isChecking: false });
          return;
        }
        // Token expired or invalid — clear it
        localStorage.removeItem(TOKEN_KEY);
      }

      set({ isAuthenticated: false, isChecking: false });
    } catch (err) {
      console.error('Auth check failed:', err);
      // If backend is unreachable, let user see the app (will get API errors)
      set({ isAuthenticated: true, isProtected: false, isChecking: false });
    }
  },

  /**
   * Attempt login with password
   */
  login: async (password) => {
    set({ error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Login failed' }));
        set({ error: err.detail || 'Incorrect password' });
        return false;
      }

      const data = await res.json();
      if (data.success && data.token) {
        localStorage.setItem(TOKEN_KEY, data.token);
        set({ isAuthenticated: true, error: null });
        return true;
      }

      set({ error: 'Unexpected response' });
      return false;
    } catch (err) {
      console.error('Login error:', err);
      set({ error: 'Cannot connect to server' });
      return false;
    }
  },

  /**
   * Log out and clear stored token
   */
  logout: () => {
    localStorage.removeItem(TOKEN_KEY);
    set({ isAuthenticated: false, error: null });
  },

  /**
   * Get the current token (for API calls)
   */
  getToken: () => localStorage.getItem(TOKEN_KEY) || '',
}));

export default useAuthStore;
