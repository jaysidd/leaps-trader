/**
 * Login Gate — blocks app access until correct password (+ optional 2FA) is entered.
 * Only shows when APP_PASSWORD is set on the backend.
 */
import { useState, useEffect, useRef } from 'react';
import useAuthStore from '../stores/authStore';

export default function LoginGate({ children }) {
  const {
    isAuthenticated, isProtected, totpEnabled, needsTotp,
    isChecking, error, checkAuth, login, submitTotp, cancelTotp
  } = useAuthStore();

  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef(null);
  const totpRef = useRef(null);

  // Check auth status on mount
  useEffect(() => {
    checkAuth();
  }, []);

  // Focus appropriate input when view changes
  useEffect(() => {
    if (!isChecking && isProtected && !isAuthenticated) {
      if (needsTotp && totpRef.current) {
        totpRef.current.focus();
      } else if (inputRef.current) {
        inputRef.current.focus();
      }
    }
  }, [isChecking, isProtected, isAuthenticated, needsTotp]);

  const handlePasswordSubmit = async (e) => {
    e.preventDefault();
    if (!password.trim() || submitting) return;

    setSubmitting(true);
    await login(password);
    setSubmitting(false);
    // Don't clear password — it may be needed for TOTP step
  };

  const handleTotpSubmit = async (e) => {
    e.preventDefault();
    if (!totpCode.trim() || submitting) return;

    setSubmitting(true);
    const success = await submitTotp(totpCode);
    setSubmitting(false);
    if (!success) {
      setTotpCode('');
    }
  };

  const handleBack = () => {
    cancelTotp();
    setPassword('');
    setTotpCode('');
  };

  // Auto-submit TOTP when 6 digits entered
  useEffect(() => {
    if (needsTotp && totpCode.length === 6 && !submitting) {
      handleTotpSubmit({ preventDefault: () => {} });
    }
  }, [totpCode, needsTotp]);

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

  // TOTP code entry (step 2)
  if (needsTotp) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center px-4">
        <div className="max-w-sm w-full">
          <div className="text-center mb-8">
            <span className="text-5xl">🔐</span>
            <h1 className="text-2xl font-bold text-white mt-4">Two-Factor Authentication</h1>
            <p className="text-gray-400 mt-2 text-sm">Enter the 6-digit code from your authenticator app</p>
          </div>

          <form onSubmit={handleTotpSubmit} className="bg-gray-800 rounded-xl p-6 shadow-2xl border border-gray-700">
            <div className="mb-4">
              <label htmlFor="totp" className="block text-sm font-medium text-gray-300 mb-2">
                Authentication Code
              </label>
              <input
                ref={totpRef}
                id="totp"
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000"
                className="w-full px-4 py-4 bg-gray-700 border border-gray-600 rounded-lg text-white text-center text-2xl tracking-[0.5em] font-mono placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                autoComplete="one-time-code"
                disabled={submitting}
              />
            </div>

            {error && (
              <div className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded-lg">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || totpCode.length !== 6}
              className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  Verifying...
                </>
              ) : (
                'Verify Code'
              )}
            </button>

            <button
              type="button"
              onClick={handleBack}
              className="w-full mt-3 py-2 px-4 text-gray-400 hover:text-white text-sm transition-colors"
            >
              Back to password
            </button>
          </form>

          <p className="text-center text-gray-600 text-xs mt-6">
            Open your authenticator app (Google Authenticator, Authy) for the code
          </p>
        </div>
      </div>
    );
  }

  // Password entry (step 1)
  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center px-4">
      <div className="max-w-sm w-full">
        {/* Logo / Header */}
        <div className="text-center mb-8">
          <span className="text-5xl">📈</span>
          <h1 className="text-2xl font-bold text-white mt-4">LEAPS Trader</h1>
          <p className="text-gray-400 mt-2 text-sm">
            {totpEnabled ? 'Enter password to continue (2FA enabled)' : 'Enter password to continue'}
          </p>
        </div>

        {/* Login Form */}
        <form onSubmit={handlePasswordSubmit} className="bg-gray-800 rounded-xl p-6 shadow-2xl border border-gray-700">
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
              totpEnabled ? 'Continue' : 'Sign In'
            )}
          </button>
        </form>

        <p className="text-center text-gray-600 text-xs mt-6">
          {totpEnabled ? 'Password + 2FA protected' : 'Protected access - single user mode'}
        </p>
      </div>
    </div>
  );
}
