/**
 * Auth Store — password + optional TOTP 2FA gate for app access
 * Stores session token in localStorage for persistence across refreshes
 */
import { create } from 'zustand';
import { API_BASE_URL } from '../api/axios';

const TOKEN_KEY = 'leaps_auth_token';

const useAuthStore = create((set, get) => ({
  // State
  isAuthenticated: false,
  isProtected: null,    // null = checking, true = password required, false = open
  totpEnabled: false,   // whether 2FA is configured on the server
  needsTotp: false,     // password verified, waiting for TOTP code
  isChecking: true,
  error: null,

  // Temp storage for password during 2FA flow
  _pendingPassword: null,

  /**
   * Check if the backend has password protection / 2FA enabled.
   * Also validates any existing stored token.
   */
  checkAuth: async () => {
    set({ isChecking: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/auth/check`);
      const data = await res.json();

      if (!data.protected) {
        // No password required — let everyone in
        set({ isAuthenticated: true, isProtected: false, totpEnabled: false, isChecking: false });
        return;
      }

      // Password is required — check if we have a valid stored token
      set({ isProtected: true, totpEnabled: !!data.totp_enabled });
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
   * Attempt login with password (+ optional TOTP code)
   */
  login: async (password, totpCode = null) => {
    set({ error: null });
    try {
      const body = { password };
      if (totpCode) {
        body.totp_code = totpCode;
      }

      const res = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Login failed' }));
        set({ error: err.detail || 'Incorrect password' });
        return false;
      }

      const data = await res.json();

      // Backend says password is correct but needs TOTP code
      if (data.requires_totp && !data.success) {
        set({ needsTotp: true, _pendingPassword: password, error: null });
        return false;
      }

      if (data.success && data.token) {
        localStorage.setItem(TOKEN_KEY, data.token);
        set({ isAuthenticated: true, needsTotp: false, _pendingPassword: null, error: null });
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
   * Submit TOTP code (second step of 2FA login)
   */
  submitTotp: async (totpCode) => {
    const { _pendingPassword, login } = get();
    if (!_pendingPassword) {
      set({ error: 'Session expired. Please enter your password again.', needsTotp: false });
      return false;
    }
    return login(_pendingPassword, totpCode);
  },

  /**
   * Go back from TOTP step to password step
   */
  cancelTotp: () => {
    set({ needsTotp: false, _pendingPassword: null, error: null });
  },

  /**
   * Log out and clear stored token
   */
  logout: () => {
    localStorage.removeItem(TOKEN_KEY);
    set({ isAuthenticated: false, needsTotp: false, _pendingPassword: null, error: null });
  },

  /**
   * Get the current token (for API calls)
   */
  getToken: () => localStorage.getItem(TOKEN_KEY) || '',
}));

export default useAuthStore;
