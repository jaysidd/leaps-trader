/**
 * Results table component
 */
import { useState, useMemo } from 'react';
import Card from '../common/Card';
import { formatLargeNumber, formatCurrency, formatScore, getScoreColor, formatPercent, getChangeColor, formatChangePercent } from '../../utils/formatters';
import useSignalsStore from '../../stores/signalsStore';

// IV Rank badge component
const IVRankBadge = ({ ivRank }) => {
  if (ivRank === undefined || ivRank === null) {
    return <span className="text-gray-400 text-sm">N/A</span>;
  }

  let color = 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300';
  let label = 'Normal';

  if (ivRank < 30) {
    color = 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
    label = 'Low';
  } else if (ivRank > 70) {
    color = 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300';
    label = 'High';
  }

  return (
    <div className="flex flex-col items-start">
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${color}`}>
        {ivRank.toFixed(0)}%
      </span>
      <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
    </div>
  );
};

// Strategy suggestion badge based on IV rank and score
const StrategyBadge = ({ ivRank, score }) => {
  let strategy = 'Long Call';
  let color = 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300';
  let icon = '📈';

  if (ivRank !== undefined && ivRank !== null) {
    if (ivRank < 30 && score >= 70) {
      strategy = 'LEAPS';
      color = 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
      icon = '🎯';
    } else if (ivRank > 50) {
      strategy = 'Spread';
      color = 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300';
      icon = '📊';
    }
  }

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${color}`}>
      <span>{icon}</span>
      <span>{strategy}</span>
    </span>
  );
};

export default function ResultsTable({ results, onSelectStock }) {
  const [sortConfig, setSortConfig] = useState({ key: 'score', direction: 'desc' });
  const [selectedStocks, setSelectedStocks] = useState(new Set());
  const [signalTimeframe, setSignalTimeframe] = useState('5m');
  const [addingToQueue, setAddingToQueue] = useState(false);
  const [addSuccess, setAddSuccess] = useState(null);

  const { addToQueue } = useSignalsStore();

  // Toggle stock selection
  const toggleStockSelection = (symbol) => {
    setSelectedStocks((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(symbol)) {
        newSet.delete(symbol);
      } else {
        newSet.add(symbol);
      }
      return newSet;
    });
  };

  // Select all passed stocks
  const selectAllPassed = () => {
    const passedSymbols = results.filter((r) => r.passed_all).map((r) => r.symbol);
    setSelectedStocks(new Set(passedSymbols));
  };

  // Clear selection
  const clearSelection = () => {
    setSelectedStocks(new Set());
  };

  // Add selected to signal queue
  const handleAddToSignalQueue = async () => {
    if (selectedStocks.size === 0) return;

    setAddingToQueue(true);
    setAddSuccess(null);

    try {
      const symbols = Array.from(selectedStocks);
      const result = await addToQueue(symbols, signalTimeframe, 'auto');
      setAddSuccess(`Added ${result.added_count} stocks to signal processing`);
      setSelectedStocks(new Set());
      // Clear success message after 3 seconds
      setTimeout(() => setAddSuccess(null), 3000);
    } catch (error) {
      console.error('Error adding to queue:', error);
      setAddSuccess('Failed to add stocks to queue');
    } finally {
      setAddingToQueue(false);
    }
  };

  // Sort results
  const sortedResults = useMemo(() => {
    const sorted = [...results];
    sorted.sort((a, b) => {
      const aValue = a[sortConfig.key] ?? 0;
      const bValue = b[sortConfig.key] ?? 0;

      if (sortConfig.direction === 'asc') {
        return aValue > bValue ? 1 : -1;
      } else {
        return aValue < bValue ? 1 : -1;
      }
    });
    return sorted;
  }, [results, sortConfig]);

  const handleSort = (key) => {
    setSortConfig((prev) => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  };

  const SortIcon = ({ column }) => {
    if (sortConfig.key !== column) {
      return <span className="text-gray-400">↕</span>;
    }
    return sortConfig.direction === 'asc' ? <span>↑</span> : <span>↓</span>;
  };

  // Filter only stocks that passed all filters
  const passedStocks = sortedResults.filter(r => r.passed_all);
  const failedStocks = sortedResults.filter(r => !r.passed_all);

  // Show "Matched Presets" column when any result has matched_preset_names (scan-all mode)
  const showMatchedPresets = results.some(r => r.matched_preset_names && r.matched_preset_names.length > 0);

  if (results.length === 0) {
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Floating Action Bar - shown when stocks are selected */}
      {selectedStocks.size > 0 && (
        <div className="fixed bottom-4 left-1/2 transform -translate-x-1/2 z-50">
          <div className="bg-blue-600 text-white px-6 py-3 rounded-lg shadow-lg flex items-center gap-4">
            <span className="font-medium">
              {selectedStocks.size} stock{selectedStocks.size > 1 ? 's' : ''} selected
            </span>
            <select
              value={signalTimeframe}
              onChange={(e) => setSignalTimeframe(e.target.value)}
              className="bg-blue-500 text-white px-2 py-1 rounded text-sm border border-blue-400"
            >
              <option value="5m">5m (Day Trade)</option>
              <option value="15m">15m (Intraday Swing)</option>
              <option value="1h">1H (Swing)</option>
              <option value="1d">1D (Multi-Day)</option>
            </select>
            <button
              onClick={handleAddToSignalQueue}
              disabled={addingToQueue}
              className="bg-green-500 hover:bg-green-600 px-4 py-1 rounded font-medium disabled:opacity-50"
            >
              {addingToQueue ? 'Adding...' : 'Add to Signal Processing'}
            </button>
            <button
              onClick={clearSelection}
              className="text-blue-200 hover:text-white text-sm"
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {/* Success Message */}
      {addSuccess && (
        <div className="bg-green-100 dark:bg-green-900/30 border border-green-400 dark:border-green-700 text-green-700 dark:text-green-300 px-4 py-3 rounded">
          {addSuccess}
        </div>
      )}

      {/* Summary */}
      <Card>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-3xl font-bold text-gray-800 dark:text-white">{results.length}</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Total Screened</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-green-600 dark:text-green-400">{passedStocks.length}</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Passed All Filters</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-red-600 dark:text-red-400">{failedStocks.length}</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Failed</div>
          </div>
        </div>
      </Card>

      {/* Passed Stocks */}
      {passedStocks.length > 0 && (
        <Card title="✅ Top LEAPS Candidates">
          {/* Selection controls */}
          <div className="flex items-center gap-4 mb-4 pb-4 border-b dark:border-gray-700">
            <button
              onClick={selectAllPassed}
              className="text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
            >
              Select All ({passedStocks.length})
            </button>
            {selectedStocks.size > 0 && (
              <button
                onClick={clearSelection}
                className="text-sm text-gray-600 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200"
              >
                Clear Selection
              </button>
            )}
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {selectedStocks.size > 0 && `${selectedStocks.size} selected`}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700/50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider w-10">
                    <input
                      type="checkbox"
                      checked={selectedStocks.size === passedStocks.length && passedStocks.length > 0}
                      onChange={() => {
                        if (selectedStocks.size === passedStocks.length) {
                          clearSelection();
                        } else {
                          selectAllPassed();
                        }
                      }}
                      className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600"
                    />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                    onClick={() => handleSort('symbol')}
                  >
                    Symbol <SortIcon column="symbol" />
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Name
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                    onClick={() => handleSort('score')}
                  >
                    Score <SortIcon column="score" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                    onClick={() => handleSort('current_price')}
                  >
                    Price <SortIcon column="current_price" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                    onClick={() => handleSort('price_change_percent')}
                  >
                    % Chg <SortIcon column="price_change_percent" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                    onClick={() => handleSort('market_cap')}
                  >
                    Market Cap <SortIcon column="market_cap" />
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Sector
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    IV Rank
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Strategy
                  </th>
                  {showMatchedPresets && (
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Matched Presets
                    </th>
                  )}
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {passedStocks.map((result, index) => (
                  <tr
                    key={result.symbol}
                    className={`hover:bg-gray-50 dark:hover:bg-gray-700 ${index % 2 === 0 ? 'bg-white dark:bg-gray-800' : 'bg-gray-50 dark:bg-gray-800/50'} ${
                      selectedStocks.has(result.symbol) ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                    }`}
                  >
                    <td className="px-4 py-4 whitespace-nowrap">
                      <input
                        type="checkbox"
                        checked={selectedStocks.has(result.symbol)}
                        onChange={() => toggleStockSelection(result.symbol)}
                        className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600"
                      />
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="font-bold text-blue-600 dark:text-blue-400">{result.symbol}</div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-900 dark:text-gray-200">{result.name || 'N/A'}</div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className={`text-lg font-bold ${getScoreColor(result.score)}`}>
                        {formatScore(result.score)}
                      </div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className={`text-sm font-medium ${getChangeColor(result.price_change_percent)}`}>
                        {formatCurrency(result.current_price)}
                      </div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className={`text-sm font-medium ${getChangeColor(result.price_change_percent)}`}>
                        {formatChangePercent(result.price_change_percent)}
                      </div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-900 dark:text-gray-200">
                        {formatLargeNumber(result.market_cap)}
                      </div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-600 dark:text-gray-400">{result.sector || 'N/A'}</div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <IVRankBadge ivRank={result.iv_rank} />
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <StrategyBadge ivRank={result.iv_rank} score={result.score} />
                    </td>
                    {showMatchedPresets && (
                      <td className="px-4 py-4">
                        <div className="flex flex-wrap gap-1 max-w-xs">
                          {(result.matched_preset_names || []).map((name) => (
                            <span
                              key={name}
                              className="inline-block px-1.5 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300"
                            >
                              {name}
                            </span>
                          ))}
                        </div>
                      </td>
                    )}
                    <td className="px-4 py-4 whitespace-nowrap">
                      <button
                        onClick={() => onSelectStock(result)}
                        className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium text-sm"
                      >
                        View Details →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Failed Stocks */}
      {failedStocks.length > 0 && (
        <Card title="❌ Stocks That Failed Screening">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700/50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Symbol
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Failed At
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Stages Passed
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {failedStocks.map((result, index) => (
                  <tr
                    key={result.symbol}
                    className={`hover:bg-gray-50 dark:hover:bg-gray-700 ${index % 2 === 0 ? 'bg-white dark:bg-gray-800' : 'bg-gray-50 dark:bg-gray-800/50'}`}
                  >
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="font-medium text-gray-700 dark:text-gray-300">{result.symbol}</div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-600 dark:text-gray-400">{result.name || 'N/A'}</div>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <span className="px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
                        {result.failed_at?.replace('_', ' ') || 'Unknown'}
                      </span>
                    </td>
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="text-sm text-gray-600 dark:text-gray-400">
                        {result.passed_stages?.join(', ') || 'None'}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
