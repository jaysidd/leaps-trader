/**
 * Axios configuration with request deduplication
 */
import axios from 'axios';

function getApiBaseUrl() {
  // Build-time env var (set in Railway frontend service)
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  // Runtime: if running on Railway/production, use the backend domain
  if (typeof window !== 'undefined' && !window.location.hostname.includes('localhost')) {
    return 'https://leaps-trader-backend-production.up.railway.app';
  }
  // Local development fallback
  return 'http://localhost:8000';
}
export const API_BASE_URL = getApiBaseUrl();

// WebSocket URL — derive from API base (https → wss, http → ws)
export const WS_BASE_URL = import.meta.env.VITE_WS_URL ||
  API_BASE_URL.replace(/^http/, 'ws');

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 120000, // 2 minutes for screening requests
});

// Request interceptor
apiClient.interceptors.request.use(
  (config) => {
    console.log('API Request:', config.method?.toUpperCase(), config.url);
    return config;
  },
  (error) => {
    console.error('Request interceptor error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // Don't log cancelled requests as errors
    if (axios.isCancel(error)) {
      return Promise.reject(error);
    }
    console.error('API Error:', {
      message: error.message,
      status: error.response?.status,
      url: error.config?.url,
    });
    return Promise.reject(error);
  }
);

/**
 * Map of in-flight AbortControllers keyed by request identifier.
 * When a new request is made to the same endpoint, the previous one
 * is automatically cancelled to prevent stale data overwrites.
 * @type {Map<string, AbortController>}
 */
const _inflightControllers = new Map();

/**
 * Generate a dedup key from method + URL path.
 * @param {string} method - HTTP method
 * @param {string} url - Request URL
 * @returns {string}
 */
function _dedupKey(method, url) {
  return `${method.toUpperCase()}:${url}`;
}

/**
 * Create a cancellable request that auto-cancels any previous in-flight
 * request to the same endpoint. This prevents stale response races.
 *
 * @param {'get'|'post'|'put'|'patch'|'delete'} method
 * @param {string} url - API endpoint path
 * @param {object} [options] - Axios request config (data, params, etc.)
 * @returns {Promise} - Axios response promise
 *
 * @example
 *   // Second call auto-cancels the first if still in-flight
 *   cancellableRequest('get', '/api/v1/signals');
 *   cancellableRequest('get', '/api/v1/signals'); // cancels previous
 */
export function cancellableRequest(method, url, options = {}) {
  const key = _dedupKey(method, url);

  // Cancel previous in-flight request to this endpoint
  if (_inflightControllers.has(key)) {
    _inflightControllers.get(key).abort();
  }

  // Create new controller for this request
  const controller = new AbortController();
  _inflightControllers.set(key, controller);

  const config = {
    ...options,
    signal: controller.signal,
  };

  const promise = method === 'get' || method === 'delete'
    ? apiClient[method](url, config)
    : apiClient[method](url, options.data, config);

  // Clean up when request completes (success or error)
  return promise.finally(() => {
    // Only remove if this controller is still the current one
    if (_inflightControllers.get(key) === controller) {
      _inflightControllers.delete(key);
    }
  });
}

/**
 * Create a standalone AbortController for manual cancellation.
 * Useful for component unmount cleanup in React.
 *
 * @returns {{ controller: AbortController, signal: AbortSignal }}
 *
 * @example
 *   const { controller, signal } = createAbortController();
 *   apiClient.get('/api/v1/data', { signal });
 *   // On cleanup:
 *   controller.abort();
 */
export function createAbortController() {
  const controller = new AbortController();
  return { controller, signal: controller.signal };
}

export default apiClient;
