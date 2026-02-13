/**
 * Signal Queue Page
 * Displays stocks being monitored and generated trading signals
 */
import { useEffect, useState, useMemo } from 'react';
import useSignalsStore from '../stores/signalsStore';
import Card from '../components/common/Card';
import SignalDetailModal from '../components/signals/SignalDetailModal';
import StrategyDetailModal from '../components/signals/StrategyDetailModal';
import SendToBotModal from '../components/signals/SendToBotModal';
import { stocksAPI } from '../api/stocks';
import { aiAPI } from '../api/ai';
import { getChangeColor, formatChangePercent } from '../utils/formatters';

// Tab button component
const TabButton = ({ active, onClick, children, count }) => (
  <button
    onClick={onClick}
    className={`px-4 py-2 font-medium rounded-t-lg border-b-2 transition-colors ${
      active
        ? 'border-blue-600 text-blue-600 dark:text-blue-400 bg-white dark:bg-gray-800'
        : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300'
    }`}
  >
    {children}
    {count !== undefined && count > 0 && (
      <span className={`ml-2 px-2 py-0.5 rounded-full text-xs ${
        active ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
      }`}>
        {count}
      </span>
    )}
  </button>
);

// Status badge component
const StatusBadge = ({ status }) => {
  const colors = {
    active: 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-400',
    paused: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-400',
    completed: 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300',
    expired: 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-400',
  };

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${colors[status] || colors.active}`}>
      {status}
    </span>
  );
};

// Direction badge component
const DirectionBadge = ({ direction }) => {
  const isBuy = direction === 'buy';
  return (
    <span className={`px-2 py-1 rounded text-xs font-bold ${
      isBuy ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-400' : 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-400'
    }`}>
      {isBuy ? 'BUY' : 'SELL'}
    </span>
  );
};

// Confidence score component
const ConfidenceScore = ({ score }) => {
  const color = score >= 75 ? 'text-green-600 dark:text-green-400' : score >= 50 ? 'text-yellow-600 dark:text-yellow-400' : 'text-red-600 dark:text-red-400';
  return (
    <span className={`font-bold ${color}`}>
      {score?.toFixed(0) || '-'}%
    </span>
  );
};

// Batch Analysis Modal
const BatchAnalysisModal = ({ analysis, onClose }) => {
  if (!analysis) return null;

  const getConvictionColor = (c) => {
    if (c >= 8) return 'text-green-600';
    if (c >= 6) return 'text-yellow-600';
    if (c >= 4) return 'text-orange-600';
    return 'text-red-600';
  };

  const getActionColor = (a) => {
    if (a === 'enter_now') return 'bg-green-100 text-green-700';
    if (a === 'wait') return 'bg-yellow-100 text-yellow-700';
    return 'bg-red-100 text-red-700';
  };

  const getBatchQualityColor = (q) => {
    if (q === 'excellent') return 'text-green-600';
    if (q === 'good') return 'text-blue-600';
    if (q === 'fair') return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-3xl w-full max-h-[85vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4 flex justify-between items-center">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">{'\u{1F9E0}'} AI Batch Analysis</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {analysis.total_analyzed} signals analyzed
              {analysis.cached && ' (cached)'}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
        </div>

        <div className="p-6 space-y-5">
          {/* Quality + Summary */}
          <div className="bg-indigo-50 dark:bg-indigo-900/20 rounded-lg p-4">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">Batch Quality:</span>
              <span className={`font-bold text-lg capitalize ${getBatchQualityColor(analysis.batch_quality)}`}>
                {analysis.batch_quality || 'N/A'}
              </span>
            </div>
            {analysis.summary && (
              <p className="text-gray-700 dark:text-gray-300 font-medium">{analysis.summary}</p>
            )}
            {analysis.quality_assessment && (
              <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">{analysis.quality_assessment}</p>
            )}
          </div>

          {/* Best Setup */}
          {analysis.best_setup?.symbol && (
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-green-700 dark:text-green-400 uppercase mb-2">{'\u2B50'} Best Setup</h3>
              <p className="font-bold text-green-800 dark:text-green-300 text-lg">{analysis.best_setup.symbol}</p>
              {analysis.best_setup.why_best && (
                <p className="text-green-700 dark:text-green-400 text-sm mt-1">{analysis.best_setup.why_best}</p>
              )}
              {analysis.best_setup.key_risk && (
                <p className="text-amber-700 dark:text-amber-400 text-xs mt-2">Risk: {analysis.best_setup.key_risk}</p>
              )}
            </div>
          )}

          {/* Ranked Signals */}
          {analysis.ranked_signals?.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase mb-3">Ranked Signals</h3>
              <div className="space-y-2">
                {analysis.ranked_signals.map((sig, idx) => (
                  <div key={idx} className="flex items-center gap-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                    <span className="text-lg font-bold text-gray-400 dark:text-gray-500 w-6">#{sig.rank}</span>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-gray-800 dark:text-gray-200">{sig.symbol}</span>
                        <span className={`font-bold ${getConvictionColor(sig.conviction)}`}>{sig.conviction}/10</span>
                        {sig.action && (
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${getActionColor(sig.action)}`}>
                            {sig.action === 'enter_now' ? 'Enter' : sig.action === 'wait' ? 'Wait' : 'Skip'}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                        {sig.strategy_match && <span>{sig.strategy_match} | </span>}
                        {sig.checklist_passed != null && <span>{sig.checklist_passed}/5 checks | </span>}
                        {sig.one_liner}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Signals to Skip */}
          {analysis.signals_to_skip?.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">Signals to Skip</h3>
              {analysis.signals_to_skip.map((sig, idx) => (
                <div key={idx} className="text-sm text-gray-600 dark:text-gray-400 py-1">
                  <span className="font-medium text-red-500">{sig.symbol}</span>: {sig.reason}
                </div>
              ))}
            </div>
          )}

          {/* Meta */}
          <div className="text-xs text-gray-400 text-right">
            {analysis.model && <span>Model: {analysis.model.split('/').pop()} | </span>}
            {analysis.analyzed_at && <span>{new Date(analysis.analyzed_at).toLocaleString()}</span>}
          </div>
        </div>
      </div>
    </div>
  );
};

export default function SignalQueue() {
  const [activeTab, setActiveTab] = useState('queue');
  const [selectedSignal, setSelectedSignal] = useState(null);
  const [batchAnalysis, setBatchAnalysis] = useState(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState(null);
  const [selectedSignalIds, setSelectedSignalIds] = useState(new Set());
  const [strategyDetailStrategy, setStrategyDetailStrategy] = useState(null);
  const [sendToBotSignal, setSendToBotSignal] = useState(null);

  const [selectedQueueIds, setSelectedQueueIds] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

  const queueItems = useSignalsStore(state => state.queueItems);
  const queueLoading = useSignalsStore(state => state.queueLoading);
  const queueStats = useSignalsStore(state => state.queueStats);
  const signals = useSignalsStore(state => state.signals);
  const signalsLoading = useSignalsStore(state => state.signalsLoading);
  const unreadCount = useSignalsStore(state => state.unreadCount);
  const fetchQueue = useSignalsStore(state => state.fetchQueue);
  const fetchSignals = useSignalsStore(state => state.fetchSignals);
  const removeFromQueue = useSignalsStore(state => state.removeFromQueue);
  const removeMultipleFromQueue = useSignalsStore(state => state.removeMultipleFromQueue);
  const pauseQueueItem = useSignalsStore(state => state.pauseQueueItem);
  const resumeQueueItem = useSignalsStore(state => state.resumeQueueItem);
  const markSignalRead = useSignalsStore(state => state.markSignalRead);
  const markAllSignalsRead = useSignalsStore(state => state.markAllSignalsRead);
  const deleteSignal = useSignalsStore(state => state.deleteSignal);
  const deleteMultipleSignals = useSignalsStore(state => state.deleteMultipleSignals);
  const clearQueue = useSignalsStore(state => state.clearQueue);
  const clearSignals = useSignalsStore(state => state.clearSignals);
  const startPolling = useSignalsStore(state => state.startPolling);
  const stopPolling = useSignalsStore(state => state.stopPolling);

  // Load data on mount
  useEffect(() => {
    fetchQueue();
    fetchSignals();
    startPolling(30000); // Poll every 30 seconds

    return () => {
      stopPolling();
    };
  }, []);

  // Collect unique symbols for batch quotes
  const allSymbols = useMemo(() => {
    const syms = new Set();
    queueItems.forEach((item) => syms.add(item.symbol));
    signals.forEach((sig) => syms.add(sig.symbol));
    return [...syms];
  }, [queueItems, signals]);

  // Fetch live quotes for all symbols
  const [liveQuotes, setLiveQuotes] = useState({});

  useEffect(() => {
    if (allSymbols.length === 0) return;
    stocksAPI.getBatchQuotes(allSymbols)
      .then(data => setLiveQuotes(data.quotes || {}))
      .catch(() => setLiveQuotes({}));
  }, [allSymbols]);

  // Get active signals for batch analysis (top 5 by confidence — used when no manual selection)
  const activeSignals = useMemo(() => {
    return [...signals]
      .filter(s => s.status === 'active')
      .sort((a, b) => (b.confidence_score || 0) - (a.confidence_score || 0))
      .slice(0, 5);
  }, [signals]);

  // Determine which signals to analyze: manual selection takes priority (capped at 5), else top 5
  const signalsToAnalyze = useMemo(() => {
    if (selectedSignalIds.size > 0) {
      return signals
        .filter(s => selectedSignalIds.has(s.id))
        .sort((a, b) => (b.confidence_score || 0) - (a.confidence_score || 0))
        .slice(0, 5);
    }
    return activeSignals;
  }, [signals, selectedSignalIds, activeSignals]);

  // Toggle signal selection (no limit — used for both analysis and bulk delete)
  const toggleSignalSelection = (signalId) => {
    setSelectedSignalIds(prev => {
      const next = new Set(prev);
      if (next.has(signalId)) {
        next.delete(signalId);
      } else {
        next.add(signalId);
      }
      return next;
    });
  };

  // Select/deselect all visible deduped signals
  const toggleSelectAll = () => {
    if (selectedSignalIds.size > 0) {
      setSelectedSignalIds(new Set());
    } else {
      setSelectedSignalIds(new Set(dedupedSignals.map(s => s.id)));
    }
  };

  // Deduplicated signals — keep only the latest signal per symbol+direction combo
  const dedupedSignals = useMemo(() => {
    const seen = new Map();
    // signals are already sorted by generated_at desc from the API
    for (const sig of signals) {
      const key = `${sig.symbol}_${sig.direction}_${sig.timeframe}`;
      if (!seen.has(key)) {
        seen.set(key, sig);
      }
    }
    return [...seen.values()];
  }, [signals]);

  // Toggle queue item selection
  const toggleQueueSelection = (itemId) => {
    setSelectedQueueIds(prev => {
      const next = new Set(prev);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  };

  // Select/deselect all queue items
  const toggleSelectAllQueue = () => {
    if (selectedQueueIds.size > 0) {
      setSelectedQueueIds(new Set());
    } else {
      setSelectedQueueIds(new Set(queueItems.map(item => item.id)));
    }
  };

  // Bulk delete selected queue items
  const handleBulkDeleteQueue = async () => {
    if (selectedQueueIds.size === 0) return;
    const count = selectedQueueIds.size;
    if (!window.confirm(`Remove ${count} item${count > 1 ? 's' : ''} from Signal Queue?`)) return;
    try {
      setBulkDeleting(true);
      await removeMultipleFromQueue([...selectedQueueIds]);
      setSelectedQueueIds(new Set());
    } catch (err) {
      console.error('Bulk queue delete error:', err);
    } finally {
      setBulkDeleting(false);
    }
  };

  // Clear all queue items
  const handleClearQueue = async () => {
    if (!window.confirm(`Remove ALL ${queueItems.length} items from Signal Queue?`)) return;
    try {
      setBulkDeleting(true);
      await clearQueue();
      setSelectedQueueIds(new Set());
    } catch (err) {
      console.error('Clear queue error:', err);
    } finally {
      setBulkDeleting(false);
    }
  };

  // Bulk delete selected signals
  const handleBulkDeleteSignals = async () => {
    if (selectedSignalIds.size === 0) return;
    const count = selectedSignalIds.size;
    if (!window.confirm(`Delete ${count} selected signal${count > 1 ? 's' : ''}?`)) return;
    try {
      setBulkDeleting(true);
      await deleteMultipleSignals([...selectedSignalIds]);
      setSelectedSignalIds(new Set());
    } catch (err) {
      console.error('Bulk signal delete error:', err);
    } finally {
      setBulkDeleting(false);
    }
  };

  // Clear all signals
  const handleClearSignals = async () => {
    if (!window.confirm(`Delete ALL ${signals.length} trading signals? This cannot be undone.`)) return;
    try {
      setBulkDeleting(true);
      await clearSignals();
      setSelectedSignalIds(new Set());
    } catch (err) {
      console.error('Clear signals error:', err);
    } finally {
      setBulkDeleting(false);
    }
  };

  // Batch analysis handler — uses manually selected signals or auto top-5
  const handleBatchAnalysis = async () => {
    if (signalsToAnalyze.length === 0) return;
    try {
      setBatchLoading(true);
      setBatchError(null);
      const signalIds = signalsToAnalyze.map(s => s.id);
      const data = await aiAPI.analyzeSignalBatch(signalIds);
      setBatchAnalysis(data);
    } catch (err) {
      console.error('Batch analysis error:', err);
      const detail = err.response?.data?.detail;
      setBatchError(detail || err.message || 'Failed to run batch analysis');
    } finally {
      setBatchLoading(false);
    }
  };

  // Handle signal click
  const handleSignalClick = async (signal) => {
    setSelectedSignal(signal);
    if (!signal.is_read) {
      await markSignalRead(signal.id);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-800 dark:text-white">Signal Processing</h1>
        <div className="flex gap-3 items-center">
          {unreadCount > 0 && (
            <button
              onClick={markAllSignalsRead}
              className="text-sm text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
            >
              Mark all as read
            </button>
          )}
          {selectedSignalIds.size > 0 && (
            <button
              onClick={() => setSelectedSignalIds(new Set())}
              className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
            >
              Clear selection ({selectedSignalIds.size})
            </button>
          )}
          <button
            onClick={handleBatchAnalysis}
            disabled={batchLoading || signalsToAnalyze.length === 0}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              batchLoading || signalsToAnalyze.length === 0
                ? 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'
                : selectedSignalIds.size > 0
                  ? 'bg-purple-600 text-white hover:bg-purple-700'
                  : 'bg-indigo-600 text-white hover:bg-indigo-700'
            }`}
            title={
              signalsToAnalyze.length === 0
                ? 'No signals to analyze'
                : selectedSignalIds.size > 0
                  ? `Analyze ${selectedSignalIds.size} selected signal(s)`
                  : `Analyze top ${activeSignals.length} active signals`
            }
          >
            {batchLoading ? (
              <>
                <span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full"></span>
                <span>Analyzing...</span>
              </>
            ) : (
              <>
                <span>{'\u{1F9E0}'}</span>
                <span>
                  {selectedSignalIds.size > 0
                    ? `Analyze ${Math.min(selectedSignalIds.size, 5)} ${selectedSignalIds.size > 5 ? '(of ' + selectedSignalIds.size + ')' : 'Selected'}`
                    : `Analyze Top ${activeSignals.length > 0 ? activeSignals.length : ''} Signals`
                  }
                </span>
              </>
            )}
          </button>
        </div>
        {batchError && (
          <div className="text-sm text-red-600 dark:text-red-400 mt-1">
            {batchError}
            <button onClick={() => setBatchError(null)} className="ml-2 underline text-xs">dismiss</button>
          </div>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <div className="text-center">
            <div className="text-3xl font-bold text-blue-600 dark:text-blue-400">{queueStats.active}</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Active Monitoring</div>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <div className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">{queueStats.paused}</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Paused</div>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <div className="text-3xl font-bold text-green-600 dark:text-green-400">{signals.length}</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Total Signals</div>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <div className="text-3xl font-bold text-red-600 dark:text-red-400">{unreadCount}</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Unread</div>
          </div>
        </Card>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <div className="flex gap-4">
          <TabButton
            active={activeTab === 'queue'}
            onClick={() => setActiveTab('queue')}
            count={queueStats.active}
          >
            Signal Queue
          </TabButton>
          <TabButton
            active={activeTab === 'signals'}
            onClick={() => setActiveTab('signals')}
            count={unreadCount}
          >
            Trading Signals
          </TabButton>
        </div>
      </div>

      {/* Queue Tab */}
      {activeTab === 'queue' && (
        <Card>
          {queueLoading ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">Loading queue...</div>
          ) : queueItems.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <p className="mb-2">No stocks in signal queue</p>
              <p className="text-sm">
                Go to Screener, run a scan, and select stocks to add to signal processing.
              </p>
            </div>
          ) : (
            <div>
              {/* Bulk action bar for queue */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50">
                <div className="flex items-center gap-3">
                  {selectedQueueIds.size > 0 && (
                    <>
                      <span className="text-sm text-gray-600 dark:text-gray-400">
                        {selectedQueueIds.size} selected
                      </span>
                      <button
                        onClick={handleBulkDeleteQueue}
                        disabled={bulkDeleting}
                        className="px-3 py-1.5 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
                      >
                        {bulkDeleting ? 'Removing...' : `Remove ${selectedQueueIds.size} Selected`}
                      </button>
                      <button
                        onClick={() => setSelectedQueueIds(new Set())}
                        className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
                      >
                        Clear selection
                      </button>
                    </>
                  )}
                </div>
                <button
                  onClick={handleClearQueue}
                  disabled={bulkDeleting}
                  className="px-3 py-1.5 border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 text-sm rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors"
                >
                  Remove All ({queueItems.length})
                </button>
              </div>
              <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-700/50">
                  <tr>
                    <th className="px-2 py-3 text-center w-10">
                      <input
                        type="checkbox"
                        checked={selectedQueueIds.size > 0 && selectedQueueIds.size === queueItems.length}
                        onChange={toggleSelectAllQueue}
                        className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 cursor-pointer"
                        title={selectedQueueIds.size > 0 ? 'Clear all selections' : 'Select all'}
                      />
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Symbol</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Name</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Price</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">% Chg</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Timeframe</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Strategy</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Conf.</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Source</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Checked</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Signals</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {queueItems.map((item) => (
                    <tr key={item.id} className={`hover:bg-gray-50 dark:hover:bg-gray-700/50 ${
                      selectedQueueIds.has(item.id) ? 'bg-indigo-50 dark:bg-indigo-900/20' : ''
                    }`}>
                      <td className="px-2 py-4 text-center w-10">
                        <input
                          type="checkbox"
                          checked={selectedQueueIds.has(item.id)}
                          onChange={() => toggleQueueSelection(item.id)}
                          className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 cursor-pointer"
                        />
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap font-bold text-blue-600 dark:text-blue-400">
                        {item.symbol}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                        {item.name || '-'}
                      </td>
                      <td className={`px-4 py-4 whitespace-nowrap text-sm font-medium ${getChangeColor(liveQuotes[item.symbol]?.change_percent)}`}>
                        {liveQuotes[item.symbol]?.current_price ? `$${liveQuotes[item.symbol].current_price.toFixed(2)}` : '--'}
                      </td>
                      <td className={`px-4 py-4 whitespace-nowrap text-sm font-medium ${getChangeColor(liveQuotes[item.symbol]?.change_percent)}`}>
                        {formatChangePercent(liveQuotes[item.symbol]?.change_percent)}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm">
                        <span className="px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded text-xs font-medium text-gray-700 dark:text-gray-300">
                          {item.timeframe}
                        </span>
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                        {(item.strategy || 'auto').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap">
                        <StatusBadge status={item.status} />
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm">
                        {item.confidence_level && (
                          <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                            item.confidence_level === 'HIGH'
                              ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400'
                              : item.confidence_level === 'MEDIUM'
                              ? 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-400'
                              : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                          }`}>
                            {item.confidence_level}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-xs text-gray-500 dark:text-gray-400">
                        {item.source === 'auto_process' ? 'Auto' : item.source === 'auto_scan' ? 'Sched' : item.source === 'ai_review' ? 'AI' : item.source || '-'}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                        {item.times_checked}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                        {item.signals_generated}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap">
                        <div className="flex gap-2">
                          {item.status === 'active' ? (
                            <button
                              onClick={() => pauseQueueItem(item.id)}
                              className="text-yellow-600 dark:text-yellow-400 hover:text-yellow-800 dark:hover:text-yellow-300 text-sm"
                            >
                              Pause
                            </button>
                          ) : (
                            <button
                              onClick={() => resumeQueueItem(item.id)}
                              className="text-green-600 dark:text-green-400 hover:text-green-800 dark:hover:text-green-300 text-sm"
                            >
                              Resume
                            </button>
                          )}
                          <button
                            onClick={() => removeFromQueue(item.id)}
                            className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 text-sm"
                          >
                            Remove
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            </div>
          )}
        </Card>
      )}

      {/* Signals Tab */}
      {activeTab === 'signals' && (
        <Card>
          {signalsLoading ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">Loading signals...</div>
          ) : signals.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <p className="mb-2">No trading signals yet</p>
              <p className="text-sm">
                Signals will appear here when conditions are met for stocks in your queue.
              </p>
            </div>
          ) : (
            <div>
              {/* Bulk action bar for signals */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50">
                <div className="flex items-center gap-3">
                  {selectedSignalIds.size > 0 && (
                    <>
                      <span className="text-sm text-gray-600 dark:text-gray-400">
                        {selectedSignalIds.size} selected
                      </span>
                      <button
                        onClick={handleBulkDeleteSignals}
                        disabled={bulkDeleting}
                        className="px-3 py-1.5 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
                      >
                        {bulkDeleting ? 'Deleting...' : `Delete ${selectedSignalIds.size} Selected`}
                      </button>
                      <button
                        onClick={() => setSelectedSignalIds(new Set())}
                        className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
                      >
                        Clear selection
                      </button>
                    </>
                  )}
                  {dedupedSignals.length < signals.length && (
                    <span className="text-xs text-amber-600 dark:text-amber-400">
                      Showing {dedupedSignals.length} unique (hiding {signals.length - dedupedSignals.length} older duplicates)
                    </span>
                  )}
                </div>
                <button
                  onClick={handleClearSignals}
                  disabled={bulkDeleting}
                  className="px-3 py-1.5 border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 text-sm rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors"
                >
                  Delete All ({signals.length})
                </button>
              </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-700/50">
                  <tr>
                    <th className="px-2 py-3 text-center w-10">
                      <input
                        type="checkbox"
                        checked={selectedSignalIds.size > 0 && selectedSignalIds.size === dedupedSignals.length}
                        ref={el => { if (el) el.indeterminate = selectedSignalIds.size > 0 && selectedSignalIds.size < dedupedSignals.length; }}
                        onChange={toggleSelectAll}
                        className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 cursor-pointer"
                        title={selectedSignalIds.size > 0 ? 'Clear all selections' : 'Select all signals'}
                      />
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Symbol</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Price</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">% Chg</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Direction</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Strategy</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Confidence</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Entry</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Stop</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Target</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">R:R</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Valid.</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Time</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {dedupedSignals.map((signal) => (
                    <tr
                      key={signal.id}
                      className={`hover:bg-gray-50 dark:hover:bg-gray-700/50 ${
                        selectedSignalIds.has(signal.id)
                          ? 'bg-indigo-50 dark:bg-indigo-900/20'
                          : !signal.is_read
                            ? 'bg-blue-50 dark:bg-blue-900/20'
                            : ''
                      }`}
                    >
                      <td className="px-2 py-4 text-center w-10">
                        <input
                          type="checkbox"
                          checked={selectedSignalIds.has(signal.id)}
                          onChange={() => toggleSignalSelection(signal.id)}
                          className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 cursor-pointer"
                          title="Select signal"
                        />
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap">
                        <div className="font-bold text-blue-600 dark:text-blue-400">{signal.symbol}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">{signal.timeframe}</div>
                      </td>
                      <td className={`px-4 py-4 whitespace-nowrap text-sm font-medium ${getChangeColor(liveQuotes[signal.symbol]?.change_percent)}`}>
                        {liveQuotes[signal.symbol]?.current_price ? `$${liveQuotes[signal.symbol].current_price.toFixed(2)}` : '--'}
                      </td>
                      <td className={`px-4 py-4 whitespace-nowrap text-sm font-medium ${getChangeColor(liveQuotes[signal.symbol]?.change_percent)}`}>
                        {formatChangePercent(liveQuotes[signal.symbol]?.change_percent)}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap">
                        <DirectionBadge direction={signal.direction} />
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm">
                        <button
                          onClick={(e) => { e.stopPropagation(); setStrategyDetailStrategy(signal.strategy); }}
                          className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 hover:underline font-medium cursor-pointer"
                          title="Click to view strategy details"
                        >
                          {signal.strategy?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                        </button>
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap">
                        <ConfidenceScore score={signal.confidence_score} />
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300">
                        ${signal.entry_price?.toFixed(2) || '-'}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm text-red-600 dark:text-red-400">
                        ${signal.stop_loss?.toFixed(2) || '-'}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm text-green-600 dark:text-green-400">
                        ${signal.target_1?.toFixed(2) || '-'}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-sm font-medium text-gray-700 dark:text-gray-300">
                        {signal.risk_reward_ratio?.toFixed(1) || '-'}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-xs">
                        {signal.validation_status && (
                          <span className={`px-1.5 py-0.5 rounded font-medium ${
                            signal.validation_status === 'validated'
                              ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400'
                              : signal.validation_status === 'rejected'
                              ? 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400'
                              : 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-400'
                          }`}>
                            {signal.validation_status === 'validated' ? 'OK' : signal.validation_status === 'rejected' ? 'Rej' : 'Pend'}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-xs text-gray-500 dark:text-gray-400">
                        {signal.generated_at
                          ? new Date(signal.generated_at).toLocaleTimeString()
                          : '-'}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap">
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleSignalClick(signal)}
                            className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 text-sm"
                          >
                            Details
                          </button>
                          {!signal.trade_executed ? (
                            <button
                              onClick={() => setSendToBotSignal(signal)}
                              className="text-green-600 dark:text-green-400 hover:text-green-800 dark:hover:text-green-300 text-sm font-medium"
                            >
                              Trade
                            </button>
                          ) : (
                            <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 px-2 py-0.5 rounded font-medium">
                              Executed
                            </span>
                          )}
                          <button
                            onClick={() => deleteSignal(signal.id)}
                            className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 text-sm"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            </div>
          )}
        </Card>
      )}

      {/* Signal Detail Modal */}
      {selectedSignal && (
        <SignalDetailModal
          signal={selectedSignal}
          onClose={() => setSelectedSignal(null)}
        />
      )}

      {/* Batch Analysis Modal */}
      {batchAnalysis && (
        <BatchAnalysisModal
          analysis={batchAnalysis}
          onClose={() => setBatchAnalysis(null)}
        />
      )}

      {/* Strategy Detail Modal */}
      {strategyDetailStrategy && (
        <StrategyDetailModal
          strategy={strategyDetailStrategy}
          onClose={() => setStrategyDetailStrategy(null)}
        />
      )}

      {/* Send to Bot Modal */}
      {sendToBotSignal && (
        <SendToBotModal
          signal={sendToBotSignal}
          onClose={() => setSendToBotSignal(null)}
          onSuccess={() => {
            setSendToBotSignal(null);
            fetchSignals();  // Refresh to show trade_executed = true
          }}
        />
      )}
    </div>
  );
}
