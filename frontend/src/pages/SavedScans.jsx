/**
 * Saved Scans Page
 * Displays persisted screening results with sidebar navigation
 *
 * Layout:
 * - Left sidebar: List of saved scan categories
 * - Right main area: Stocks from selected category
 */
import { useEffect, useState } from 'react';
import useSavedScansStore from '../stores/savedScansStore';
import useSignalsStore from '../stores/signalsStore';
import Card from '../components/common/Card';
import StockDetail from '../components/screener/StockDetail';
import { stocksAPI } from '../api/stocks';
import { scanProcessingAPI } from '../api/scanProcessing';
import { getChangeColor, formatChangePercent } from '../utils/formatters';

// Format date for display
const formatDate = (dateString) => {
  if (!dateString) return 'Never';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
};

// Format large numbers
const formatNumber = (num, decimals = 2) => {
  if (num === null || num === undefined) return '-';
  if (Math.abs(num) >= 1e12) return (num / 1e12).toFixed(decimals) + 'T';
  if (Math.abs(num) >= 1e9) return (num / 1e9).toFixed(decimals) + 'B';
  if (Math.abs(num) >= 1e6) return (num / 1e6).toFixed(decimals) + 'M';
  if (Math.abs(num) >= 1e3) return (num / 1e3).toFixed(decimals) + 'K';
  return num.toFixed(decimals);
};

// Category item in sidebar
const CategoryItem = ({ category, isSelected, onClick, onDelete }) => {
  const [showConfirm, setShowConfirm] = useState(false);

  return (
    <div
      className={`group p-3 rounded-lg cursor-pointer transition-colors ${
        isSelected
          ? 'bg-blue-100 dark:bg-blue-900/40 border-l-4 border-blue-600 dark:border-blue-400'
          : 'hover:bg-gray-100 dark:hover:bg-gray-700/50'
      }`}
      onClick={() => onClick(category.scan_type)}
    >
      <div className="flex justify-between items-start">
        <div className="flex-1 min-w-0">
          <h3 className={`font-medium truncate ${
            isSelected ? 'text-blue-700 dark:text-blue-300' : 'text-gray-800 dark:text-gray-200'
          }`}>
            {category.display_name || category.scan_type}
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            {category.stock_count} stocks
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500">
            {formatDate(category.last_run_at)}
          </p>
        </div>

        {/* Delete button */}
        <div className="ml-2">
          {showConfirm ? (
            <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
              <button
                onClick={() => {
                  onDelete(category.scan_type);
                  setShowConfirm(false);
                }}
                className="text-xs text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 px-1"
              >
                Yes
              </button>
              <button
                onClick={() => setShowConfirm(false)}
                className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 px-1"
              >
                No
              </button>
            </div>
          ) : (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowConfirm(true);
              }}
              className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 dark:text-gray-500 dark:hover:text-red-400 transition-opacity"
              title="Delete category"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

// Stock row in results table
const StockRow = ({ stock, liveQuote, onDelete, onViewDetails, isSelected, onToggleSelect }) => {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Extract data from stock_data if available
  const stockData = stock.stock_data || {};
  const indicators = stockData.technical_indicators || {};

  // Build stock object for detail view
  const handleViewDetails = () => {
    // Merge saved stock data with stock_data for full detail view
    const detailStock = {
      ...stockData,
      symbol: stock.symbol,
      name: stock.company_name || stockData.company_name || stockData.name,
      current_price: stock.current_price || stockData.current_price,
      market_cap: stock.market_cap || stockData.market_cap,
      score: stock.score || stockData.composite_score,
      composite_score: stock.score || stockData.composite_score,
      iv_rank: stock.iv_rank || stockData.iv_rank,
    };
    onViewDetails(detailStock);
  };

  return (
    <tr className={`hover:bg-gray-50 dark:hover:bg-gray-700/50 ${isSelected ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
      <td className="px-4 py-4 whitespace-nowrap">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggleSelect(stock.symbol)}
          className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600 dark:bg-gray-700"
        />
      </td>
      <td className="px-4 py-4 whitespace-nowrap">
        <button
          onClick={handleViewDetails}
          className="text-left group"
        >
          <div className="font-bold text-blue-600 dark:text-blue-400 group-hover:text-blue-800 dark:group-hover:text-blue-300 group-hover:underline cursor-pointer">
            {stock.symbol}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-[150px]">
            {stock.company_name || stockData.company_name || stockData.name || '-'}
          </div>
        </button>
      </td>
      <td className="px-4 py-4 whitespace-nowrap text-sm">
        <span className={`font-medium ${
          (stock.score || stockData.composite_score) >= 70
            ? 'text-green-600 dark:text-green-400'
            : (stock.score || stockData.composite_score) >= 50
            ? 'text-yellow-600 dark:text-yellow-400'
            : 'text-red-600 dark:text-red-400'
        }`}>
          {(stock.score || stockData.composite_score)?.toFixed(1) || '-'}
        </span>
      </td>
      <td className={`px-4 py-4 whitespace-nowrap text-sm font-medium ${getChangeColor(liveQuote?.change_percent)}`}>
        ${(liveQuote?.current_price || stock.current_price || stockData.current_price)?.toFixed(2) || '-'}
      </td>
      <td className={`px-4 py-4 whitespace-nowrap text-sm font-medium ${getChangeColor(liveQuote?.change_percent)}`}>
        {formatChangePercent(liveQuote?.change_percent)}
      </td>
      <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
        {formatNumber(stock.market_cap || stockData.market_cap, 1)}
      </td>
      <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
        {(stock.iv_rank || stockData.iv_rank)?.toFixed(1) || '-'}%
      </td>
      <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
        {(indicators.rsi || stockData.rsi)?.toFixed(1) || '-'}
      </td>
      <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
        {formatDate(stock.scanned_at)}
      </td>
      <td className="px-4 py-4 whitespace-nowrap">
        {showDeleteConfirm ? (
          <div className="flex gap-2">
            <button
              onClick={() => {
                onDelete(stock.symbol);
                setShowDeleteConfirm(false);
              }}
              className="text-xs text-red-600 dark:text-red-400 hover:text-red-800"
            >
              Delete
            </button>
            <button
              onClick={() => setShowDeleteConfirm(false)}
              className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="text-gray-400 hover:text-red-500 dark:text-gray-500 dark:hover:text-red-400"
            title="Remove stock"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </td>
    </tr>
  );
};

export default function SavedScans() {
  const {
    categories,
    selectedCategory,
    selectedCategoryStocks,
    loading,
    error,
    fetchCategories,
    selectCategory,
    deleteCategory,
    deleteStock,
    deleteSelectedStocks,
    clearAll,
    clearError,
  } = useSavedScansStore();

  const { addToQueue } = useSignalsStore();

  const [showClearAllConfirm, setShowClearAllConfirm] = useState(false);
  const [showDeleteSelectedConfirm, setShowDeleteSelectedConfirm] = useState(false);
  const [selectedStock, setSelectedStock] = useState(null);

  // Signal processing state
  const [selectedStocks, setSelectedStocks] = useState(new Set());
  const [signalTimeframe, setSignalTimeframe] = useState('5m');
  const [addingToQueue, setAddingToQueue] = useState(false);
  const [addSuccess, setAddSuccess] = useState(null);
  const [liveQuotes, setLiveQuotes] = useState({});

  // Auto-process state
  const [autoProcessing, setAutoProcessing] = useState(false);
  const [autoProcessResults, setAutoProcessResults] = useState(null);
  const [showSkipped, setShowSkipped] = useState(false);

  // Load categories on mount
  useEffect(() => {
    fetchCategories();
  }, []);

  // Clear selection when category changes
  useEffect(() => {
    setSelectedStocks(new Set());
  }, [selectedCategory]);

  // Fetch live quotes for current category stocks
  useEffect(() => {
    if (selectedCategoryStocks.length === 0) {
      setLiveQuotes({});
      return;
    }
    const symbols = selectedCategoryStocks.map(s => s.symbol);
    stocksAPI.getBatchQuotes(symbols)
      .then(data => setLiveQuotes(data.quotes || {}))
      .catch(() => setLiveQuotes({}));
  }, [selectedCategoryStocks]);

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

  // Select all stocks
  const selectAllStocks = () => {
    const allSymbols = selectedCategoryStocks.map((s) => s.symbol);
    setSelectedStocks(new Set(allSymbols));
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
      setTimeout(() => setAddSuccess(null), 3000);
    } finally {
      setAddingToQueue(false);
    }
  };

  // Get current category metadata
  const currentCategory = categories.find(c => c.scan_type === selectedCategory);

  // Handle delete stock
  const handleDeleteStock = async (symbol) => {
    if (selectedCategory) {
      await deleteStock(selectedCategory, symbol);
    }
  };

  // Handle clear all
  const handleClearAll = async () => {
    await clearAll();
    setShowClearAllConfirm(false);
  };

  // Handle delete selected stocks
  const handleDeleteSelected = async () => {
    if (selectedCategory && selectedStocks.size > 0) {
      await deleteSelectedStocks(selectedCategory, Array.from(selectedStocks));
      setSelectedStocks(new Set());
      setShowDeleteSelectedConfirm(false);
    }
  };

  // Handle auto-process scan
  const handleAutoProcess = async () => {
    if (!selectedCategory) return;
    setAutoProcessing(true);
    setAutoProcessResults(null);
    try {
      const results = await scanProcessingAPI.processScan(selectedCategory);
      setAutoProcessResults(results);
      setAddSuccess(`Auto-processed: ${results.stats.auto_queued_count} queued, ${results.stats.review_count} need review`);
      setTimeout(() => setAddSuccess(null), 5000);
    } catch (err) {
      console.error('Auto-process error:', err);
      setAddSuccess('Failed to auto-process scan');
      setTimeout(() => setAddSuccess(null), 3000);
    } finally {
      setAutoProcessing(false);
    }
  };

  // Handle queue reviewed stocks from AI review results
  const handleQueueReviewed = async (stocks) => {
    try {
      const payload = stocks.map(s => ({
        symbol: s.symbol,
        timeframes: s.timeframes || [],
        strategy: 'auto',
        confidence_level: 'MEDIUM',
        reasoning: s.reasoning || 'Manually approved from review',
      }));
      const result = await scanProcessingAPI.queueReviewed(payload);
      setAddSuccess(`Queued ${result.added_count} reviewed stocks`);
      setTimeout(() => setAddSuccess(null), 3000);
    } catch (err) {
      console.error('Queue reviewed error:', err);
      setAddSuccess('Failed to queue reviewed stocks');
      setTimeout(() => setAddSuccess(null), 3000);
    }
  };

  return (
    <div className="flex gap-6 h-[calc(100vh-120px)]">
      {/* Left Sidebar - Categories */}
      <div className="w-72 flex-shrink-0">
        <Card className="h-full flex flex-col">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-bold text-gray-800 dark:text-white">Saved Scans</h2>
            {categories.length > 0 && (
              showClearAllConfirm ? (
                <div className="flex gap-1">
                  <button
                    onClick={handleClearAll}
                    className="text-xs text-red-600 dark:text-red-400 hover:text-red-800 px-2 py-1"
                  >
                    Confirm Clear All
                  </button>
                  <button
                    onClick={() => setShowClearAllConfirm(false)}
                    className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 px-2 py-1"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowClearAllConfirm(true)}
                  className="text-xs text-gray-500 dark:text-gray-400 hover:text-red-500 dark:hover:text-red-400"
                  title="Clear all saved scans"
                >
                  Clear All
                </button>
              )
            )}
          </div>

          {error && (
            <div className="mb-4 p-2 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 rounded text-sm">
              {error}
              <button onClick={clearError} className="ml-2 underline">Dismiss</button>
            </div>
          )}

          {/* Categories list */}
          <div className="flex-1 overflow-y-auto space-y-1">
            {loading && categories.length === 0 ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                Loading...
              </div>
            ) : categories.length === 0 ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <svg className="w-12 h-12 mx-auto mb-3 text-gray-300 dark:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
                <p className="mb-2">No saved scans yet</p>
                <p className="text-xs">
                  Run scans from the Screener page to see them here.
                </p>
              </div>
            ) : (
              categories.map((category) => (
                <CategoryItem
                  key={category.scan_type}
                  category={category}
                  isSelected={selectedCategory === category.scan_type}
                  onClick={selectCategory}
                  onDelete={deleteCategory}
                />
              ))
            )}
          </div>

          {/* Summary footer */}
          {categories.length > 0 && (
            <div className="pt-4 border-t border-gray-200 dark:border-gray-700 mt-4">
              <div className="text-xs text-gray-500 dark:text-gray-400">
                <span className="font-medium">{categories.length}</span> scan{categories.length !== 1 ? 's' : ''} saved
                {' '}|{' '}
                <span className="font-medium">
                  {categories.reduce((sum, c) => sum + (c.stock_count || 0), 0)}
                </span> total stocks
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* Right Main Area - Stock Results */}
      <div className="flex-1 min-w-0">
        <Card className="h-full flex flex-col">
          {/* Header */}
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2 className="text-xl font-bold text-gray-800 dark:text-white">
                {currentCategory?.display_name || selectedCategory || 'Select a Scan'}
              </h2>
              {currentCategory && (
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Last updated: {formatDate(currentCategory.last_run_at)}
                </p>
              )}
            </div>
            {selectedCategoryStocks.length > 0 && (
              <div className="flex items-center gap-3">
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  {selectedCategoryStocks.length} stock{selectedCategoryStocks.length !== 1 ? 's' : ''}
                </div>
                <button
                  onClick={handleAutoProcess}
                  disabled={autoProcessing}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 dark:bg-purple-700 dark:hover:bg-purple-600 text-white text-sm font-medium rounded-lg disabled:opacity-50 transition-colors"
                  title="Run StrategySelector on all stocks — auto-queue HIGH confidence, flag MEDIUM for review"
                >
                  {autoProcessing ? 'Processing...' : 'Auto-Process Scan'}
                </button>
              </div>
            )}
          </div>

          {/* Auto-Process Results Panel */}
          {autoProcessResults && (
            <div className="mb-4 space-y-3">
              {/* Stats bar */}
              <div className="flex items-center gap-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-sm">
                <span className="font-medium text-gray-700 dark:text-gray-300">
                  Strategy Selection Results:
                </span>
                <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400 rounded">
                  {autoProcessResults.stats.auto_queued_count} Auto-Queued
                </span>
                <span className="px-2 py-0.5 bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-400 rounded">
                  {autoProcessResults.stats.review_count} Need Review
                </span>
                <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-600 text-gray-600 dark:text-gray-300 rounded">
                  {autoProcessResults.stats.skipped_count} Skipped
                </span>
                <button
                  onClick={() => setAutoProcessResults(null)}
                  className="ml-auto text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  Dismiss
                </button>
              </div>

              {/* Auto-Queued (GREEN) */}
              {autoProcessResults.auto_queued.length > 0 && (
                <div className="border border-green-200 dark:border-green-800 rounded-lg overflow-hidden">
                  <div className="bg-green-50 dark:bg-green-900/30 px-4 py-2 font-medium text-green-700 dark:text-green-400 text-sm">
                    Auto-Queued to Signal Processing ({autoProcessResults.auto_queued.length})
                  </div>
                  <div className="divide-y divide-green-100 dark:divide-green-800/50">
                    {autoProcessResults.auto_queued.map((stock) => (
                      <div key={stock.symbol} className="px-4 py-2 flex items-center gap-3 text-sm">
                        <span className="font-bold text-green-700 dark:text-green-400 w-16">{stock.symbol}</span>
                        <span className="text-gray-600 dark:text-gray-400">Score: {stock.score?.toFixed(1)}</span>
                        <div className="flex gap-1">
                          {stock.timeframes.map(tf => (
                            <span key={tf} className="px-1.5 py-0.5 bg-green-100 dark:bg-green-800 text-green-700 dark:text-green-300 rounded text-xs font-medium">
                              {tf}
                            </span>
                          ))}
                        </div>
                        <span className="text-gray-500 dark:text-gray-400 text-xs truncate flex-1">{stock.reasoning}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Review Needed (YELLOW) */}
              {autoProcessResults.review_needed.length > 0 && (
                <div className="border border-yellow-200 dark:border-yellow-800 rounded-lg overflow-hidden">
                  <div className="bg-yellow-50 dark:bg-yellow-900/30 px-4 py-2 flex items-center justify-between">
                    <span className="font-medium text-yellow-700 dark:text-yellow-400 text-sm">
                      Needs Review ({autoProcessResults.review_needed.length})
                    </span>
                    <button
                      onClick={() => handleQueueReviewed(autoProcessResults.review_needed)}
                      className="px-3 py-1 bg-yellow-600 hover:bg-yellow-700 text-white text-xs font-medium rounded"
                    >
                      Queue All Reviewed
                    </button>
                  </div>
                  <div className="divide-y divide-yellow-100 dark:divide-yellow-800/50">
                    {autoProcessResults.review_needed.map((stock) => (
                      <div key={stock.symbol} className="px-4 py-2 flex items-center gap-3 text-sm">
                        <span className="font-bold text-yellow-700 dark:text-yellow-400 w-16">{stock.symbol}</span>
                        <span className="text-gray-600 dark:text-gray-400">Score: {stock.score?.toFixed(1)}</span>
                        <div className="flex gap-1">
                          {(stock.timeframes || []).map(tf => (
                            <span key={tf} className="px-1.5 py-0.5 bg-yellow-100 dark:bg-yellow-800 text-yellow-700 dark:text-yellow-300 rounded text-xs font-medium">
                              {tf}
                            </span>
                          ))}
                        </div>
                        {stock.edge_cases?.length > 0 && (
                          <span className="text-yellow-600 dark:text-yellow-400 text-xs truncate flex-1">
                            {stock.edge_cases[0]}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Skipped (GRAY — collapsible) */}
              {autoProcessResults.skipped.length > 0 && (
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                  <button
                    onClick={() => setShowSkipped(!showSkipped)}
                    className="w-full bg-gray-50 dark:bg-gray-700/50 px-4 py-2 flex items-center justify-between text-sm"
                  >
                    <span className="font-medium text-gray-500 dark:text-gray-400">
                      Skipped ({autoProcessResults.skipped.length})
                    </span>
                    <svg className={`w-4 h-4 text-gray-400 transition-transform ${showSkipped ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                  {showSkipped && (
                    <div className="divide-y divide-gray-100 dark:divide-gray-700/50">
                      {autoProcessResults.skipped.map((stock) => (
                        <div key={stock.symbol} className="px-4 py-2 flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
                          <span className="font-medium w-16">{stock.symbol}</span>
                          <span>Score: {stock.score?.toFixed(1)}</span>
                          <span className="text-xs truncate flex-1">{stock.reasoning}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Results table */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                Loading stocks...
              </div>
            ) : !selectedCategory ? (
              <div className="text-center py-16 text-gray-500 dark:text-gray-400">
                <svg className="w-16 h-16 mx-auto mb-4 text-gray-300 dark:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                </svg>
                <p>Select a scan category from the sidebar</p>
              </div>
            ) : selectedCategoryStocks.length === 0 ? (
              <div className="text-center py-16 text-gray-500 dark:text-gray-400">
                <svg className="w-16 h-16 mx-auto mb-4 text-gray-300 dark:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                </svg>
                <p>No stocks in this scan</p>
                <p className="text-sm mt-1">Run this scan again from the Screener</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                {/* Selection controls */}
                <div className="flex items-center gap-4 mb-4 pb-4 border-b border-gray-200 dark:border-gray-700">
                  <button
                    onClick={selectAllStocks}
                    className="text-sm text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
                  >
                    Select All ({selectedCategoryStocks.length})
                  </button>
                  {selectedStocks.size > 0 && (
                    <>
                      <button
                        onClick={clearSelection}
                        className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
                      >
                        Clear Selection
                      </button>
                      <span className="text-sm text-gray-500 dark:text-gray-400">
                        {selectedStocks.size} selected
                      </span>
                      <span className="text-gray-300 dark:text-gray-600">|</span>
                      {showDeleteSelectedConfirm ? (
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-red-600 dark:text-red-400">
                            Delete {selectedStocks.size} stock{selectedStocks.size > 1 ? 's' : ''}?
                          </span>
                          <button
                            onClick={handleDeleteSelected}
                            className="text-sm font-medium text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 px-2 py-0.5 rounded bg-red-50 dark:bg-red-900/30"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setShowDeleteSelectedConfirm(false)}
                            className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setShowDeleteSelectedConfirm(true)}
                          className="text-sm text-red-500 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 font-medium"
                        >
                          Delete Selected
                        </button>
                      )}
                    </>
                  )}
                </div>
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-700/50 sticky top-0">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase w-10">
                        <input
                          type="checkbox"
                          checked={selectedStocks.size === selectedCategoryStocks.length && selectedCategoryStocks.length > 0}
                          onChange={() => {
                            if (selectedStocks.size === selectedCategoryStocks.length) {
                              clearSelection();
                            } else {
                              selectAllStocks();
                            }
                          }}
                          className="h-4 w-4 text-blue-600 rounded border-gray-300 dark:border-gray-600 dark:bg-gray-700"
                        />
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Symbol</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Score</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Price</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">% Chg</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Mkt Cap</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">IV Rank</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">RSI</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Scanned</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase"></th>
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                    {selectedCategoryStocks.map((stock) => (
                      <StockRow
                        key={stock.id || stock.symbol}
                        stock={stock}
                        liveQuote={liveQuotes[stock.symbol]}
                        onDelete={handleDeleteStock}
                        onViewDetails={setSelectedStock}
                        isSelected={selectedStocks.has(stock.symbol)}
                        onToggleSelect={toggleStockSelection}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Stock Detail Modal */}
      {selectedStock && (
        <StockDetail
          stock={selectedStock}
          onClose={() => setSelectedStock(null)}
        />
      )}

      {/* Success Message */}
      {addSuccess && (
        <div className="fixed top-20 left-1/2 transform -translate-x-1/2 z-50">
          <div className={`px-6 py-3 rounded-lg shadow-lg ${
            addSuccess.includes('Failed')
              ? 'bg-red-100 dark:bg-red-900/80 text-red-700 dark:text-red-200 border border-red-400 dark:border-red-600'
              : 'bg-green-100 dark:bg-green-900/80 text-green-700 dark:text-green-200 border border-green-400 dark:border-green-600'
          }`}>
            {addSuccess}
          </div>
        </div>
      )}

      {/* Floating Action Bar - shown when stocks are selected */}
      {selectedStocks.size > 0 && (
        <div className="fixed bottom-4 left-1/2 transform -translate-x-1/2 z-50">
          <div className="bg-blue-600 dark:bg-blue-700 text-white px-6 py-3 rounded-lg shadow-lg flex items-center gap-4">
            <span className="font-medium">
              {selectedStocks.size} stock{selectedStocks.size > 1 ? 's' : ''} selected
            </span>
            <select
              value={signalTimeframe}
              onChange={(e) => setSignalTimeframe(e.target.value)}
              className="bg-blue-500 dark:bg-blue-600 text-white px-2 py-1 rounded text-sm border border-blue-400 dark:border-blue-500"
            >
              <option value="5m">5m (Day Trade)</option>
              <option value="15m">15m (Intraday Swing)</option>
              <option value="1h">1H (Swing)</option>
              <option value="1d">1D (Multi-Day)</option>
            </select>
            <button
              onClick={handleAddToSignalQueue}
              disabled={addingToQueue}
              className="bg-green-500 hover:bg-green-600 dark:bg-green-600 dark:hover:bg-green-500 px-4 py-1 rounded font-medium disabled:opacity-50"
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
    </div>
  );
}
