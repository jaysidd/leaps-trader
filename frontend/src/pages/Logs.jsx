/**
 * Logs Viewer — real-time application logs from the Redis ring buffer.
 *
 * Features:
 *   - Auto-refresh every 5 seconds (toggleable)
 *   - Level filter (ALL, ERROR, WARNING, INFO, DEBUG)
 *   - Free-text search
 *   - Module filter
 *   - Color-coded log entries
 *   - Monospace font, dark theme
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import apiClient from '../api/axios';

// ── Level color map ──────────────────────────────────────────────────────────

const LEVEL_COLORS = {
  ERROR: 'text-red-400 bg-red-900/20 border-red-800',
  WARNING: 'text-yellow-400 bg-yellow-900/20 border-yellow-800',
  INFO: 'text-gray-200 bg-gray-800/50 border-gray-700',
  DEBUG: 'text-gray-500 bg-gray-800/30 border-gray-700',
  SUCCESS: 'text-green-400 bg-green-900/20 border-green-800',
};

const LEVEL_BADGE = {
  ERROR: 'bg-red-600 text-white',
  WARNING: 'bg-yellow-600 text-white',
  INFO: 'bg-blue-600 text-white',
  DEBUG: 'bg-gray-600 text-gray-300',
  SUCCESS: 'bg-green-600 text-white',
};

export default function Logs() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [level, setLevel] = useState('');
  const [search, setSearch] = useState('');
  const [module, setModule] = useState('');
  const [limit, setLimit] = useState(200);
  const scrollRef = useRef(null);
  const [followTail, setFollowTail] = useState(true);

  const fetchLogs = useCallback(async () => {
    try {
      const params = { limit };
      if (level) params.level = level;
      if (search) params.search = search;
      if (module) params.module = module;

      const resp = await apiClient.get('/api/v1/logs', { params });
      setLogs(resp.data?.logs || []);
      setError(null);
    } catch (err) {
      if (loading) {
        setError('Failed to load logs: ' + (err.message || 'Unknown error'));
      }
    } finally {
      setLoading(false);
    }
  }, [level, search, module, limit, loading]);

  // Initial fetch
  useEffect(() => {
    fetchLogs();
  }, [level, search, module, limit]);

  // Auto-refresh polling
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchLogs, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchLogs]);

  // Auto-scroll to bottom when following tail
  useEffect(() => {
    if (followTail && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, followTail]);

  // Debounced search input
  const [searchInput, setSearchInput] = useState('');
  const [moduleInput, setModuleInput] = useState('');

  useEffect(() => {
    const timeout = setTimeout(() => setSearch(searchInput), 300);
    return () => clearTimeout(timeout);
  }, [searchInput]);

  useEffect(() => {
    const timeout = setTimeout(() => setModule(moduleInput), 300);
    return () => clearTimeout(timeout);
  }, [moduleInput]);

  // Level counts
  const levelCounts = logs.reduce((acc, l) => {
    acc[l.level] = (acc[l.level] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 py-6 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <span>{'\uD83D\uDCDC'}</span> Application Logs
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Real-time logs from the backend (Redis ring buffer, last {limit} entries)
            </p>
          </div>

          {/* Auto-refresh toggle */}
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500 dark:text-gray-400">Auto-refresh</span>
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                autoRefresh ? 'bg-green-600' : 'bg-gray-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  autoRefresh ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
            <button
              onClick={fetchLogs}
              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors"
            >
              Refresh
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Filters */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex flex-wrap gap-3 items-end">
            {/* Level filter */}
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Level</label>
              <select
                value={level}
                onChange={(e) => setLevel(e.target.value)}
                className="px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100"
              >
                <option value="">ALL</option>
                <option value="ERROR">ERROR</option>
                <option value="WARNING">WARNING</option>
                <option value="INFO">INFO</option>
                <option value="DEBUG">DEBUG</option>
              </select>
            </div>

            {/* Search */}
            <div className="flex-1 min-w-[200px]">
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Search</label>
              <input
                type="text"
                placeholder="Search log messages..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400"
              />
            </div>

            {/* Module filter */}
            <div className="min-w-[150px]">
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Module</label>
              <input
                type="text"
                placeholder="e.g. main, screener"
                value={moduleInput}
                onChange={(e) => setModuleInput(e.target.value)}
                className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400"
              />
            </div>

            {/* Limit */}
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Limit</label>
              <select
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-900 dark:text-gray-100"
              >
                <option value={100}>100</option>
                <option value={200}>200</option>
                <option value={500}>500</option>
                <option value={1000}>1000</option>
              </select>
            </div>

            {/* Follow tail toggle */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setFollowTail(!followTail)}
                className={`px-3 py-2 text-sm rounded-lg transition-colors border ${
                  followTail
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-gray-700 text-gray-400 border-gray-600 hover:bg-gray-600'
                }`}
              >
                {followTail ? '\u2193 Follow' : '\u2193 Follow'}
              </button>
            </div>
          </div>

          {/* Level summary badges */}
          <div className="flex flex-wrap gap-2 mt-3">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {logs.length} entries
            </span>
            {Object.entries(levelCounts).map(([lvl, count]) => (
              <span
                key={lvl}
                className={`px-2 py-0.5 rounded-full text-xs font-medium ${LEVEL_BADGE[lvl] || 'bg-gray-600 text-gray-300'}`}
              >
                {lvl}: {count}
              </span>
            ))}
          </div>
        </div>

        {/* Log entries */}
        <div
          ref={scrollRef}
          className="bg-gray-950 rounded-xl border border-gray-700 overflow-hidden"
          style={{ maxHeight: 'calc(100vh - 340px)', overflowY: 'auto' }}
        >
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mr-3" />
              <span className="text-gray-400">Loading logs...</span>
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 text-sm">No log entries found</p>
              <p className="text-gray-600 text-xs mt-1">Logs appear after the backend starts writing to Redis</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-800/50">
              {logs.map((entry, idx) => {
                const levelColor = LEVEL_COLORS[entry.level] || LEVEL_COLORS.INFO;
                return (
                  <div
                    key={idx}
                    className={`px-4 py-2 font-mono text-xs border-l-2 hover:bg-gray-900/50 transition-colors ${levelColor}`}
                  >
                    <div className="flex items-start gap-3">
                      {/* Timestamp */}
                      <span className="text-gray-500 shrink-0 whitespace-nowrap">
                        {entry.ts}
                      </span>

                      {/* Level badge */}
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${LEVEL_BADGE[entry.level] || 'bg-gray-600 text-gray-300'}`}>
                        {entry.level?.padEnd(7) || 'UNKNOWN'}
                      </span>

                      {/* Module */}
                      <span className="text-purple-400 shrink-0 min-w-[80px]">
                        {entry.module || '?'}
                      </span>

                      {/* Message */}
                      <span className="text-gray-200 break-all flex-1">
                        {entry.msg}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
