/**
 * Login Gate — blocks app access until correct password is entered.
 * Only shows when APP_PASSWORD is set on the backend.
 */
import { useState, useEffect, useRef } from 'react';
import useAuthStore from '../stores/authStore';

export default function LoginGate({ children }) {
  const { isAuthenticated, isProtected, isChecking, error, checkAuth, login } = useAuthStore();
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef(null);

  // Check auth status on mount
  useEffect(() => {
    checkAuth();
  }, []);

  // Focus password input when login form appears
  useEffect(() => {
    if (!isChecking && isProtected && !isAuthenticated && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isChecking, isProtected, isAuthenticated]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!password.trim() || submitting) return;

    setSubmitting(true);
    await login(password);
    setSubmitting(false);
    setPassword('');
  };

  // Loading state
  if (isChecking) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-400 text-sm">Connecting to server...</p>
        </div>
      </div>
    );
  }

  // Not protected or already authenticated — render the app
  if (!isProtected || isAuthenticated) {
    return children;
  }

  // Login screen
  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center px-4">
      <div className="max-w-sm w-full">
        {/* Logo / Header */}
        <div className="text-center mb-8">
          <span className="text-5xl">📈</span>
          <h1 className="text-2xl font-bold text-white mt-4">LEAPS Trader</h1>
          <p className="text-gray-400 mt-2 text-sm">Enter password to continue</p>
        </div>

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="bg-gray-800 rounded-xl p-6 shadow-2xl border border-gray-700">
          <div className="mb-4">
            <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-2">
              Password
            </label>
            <input
              ref={inputRef}
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter app password"
              className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              autoComplete="current-password"
              disabled={submitting}
            />
          </div>

          {/* Error message */}
          {error && (
            <div className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded-lg">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !password.trim()}
            className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {submitting ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                Verifying...
              </>
            ) : (
              'Sign In'
            )}
          </button>
        </form>

        <p className="text-center text-gray-600 text-xs mt-6">
          Protected access - single user mode
        </p>
      </div>
    </div>
  );
}
