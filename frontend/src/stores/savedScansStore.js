/**
 * Zustand store for Saved Scans state
 *
 * Manages persistent scan results across sessions:
 * - Categories/scan types with metadata
 * - Selected category display
 * - CRUD operations for saved stocks
 */
import { create } from 'zustand';
import { savedScansAPI } from '../api/savedScans';

const useSavedScansStore = create((set, get) => ({
  // State
  categories: [],
  selectedCategory: null,
  selectedCategoryStocks: [],
  scanStatus: {}, // Map of scan_type -> { has_results, stock_count, last_run_at }
  loading: false,
  error: null,

  // Actions
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),

  /**
   * Fetch all saved scan categories
   */
  fetchCategories: async () => {
    set({ loading: true, error: null });
    try {
      const data = await savedScansAPI.getCategories();
      const categories = data.categories || [];

      set({
        categories,
        loading: false,
        // Auto-select first category if none selected
        selectedCategory: get().selectedCategory || (categories.length > 0 ? categories[0].scan_type : null)
      });

      // If we have a selected category, fetch its stocks
      const selected = get().selectedCategory;
      if (selected) {
        get().fetchCategoryStocks(selected);
      }

      return categories;
    } catch (err) {
      console.error('[SavedScansStore] Error fetching categories:', err);
      set({
        loading: false,
        error: err.response?.data?.detail || err.message || 'Failed to fetch saved scans'
      });
      return [];
    }
  },

  /**
   * Fetch stocks for a specific category
   */
  fetchCategoryStocks: async (scanType) => {
    set({ loading: true, error: null, selectedCategory: scanType });
    try {
      const data = await savedScansAPI.getResults(scanType);
      set({
        selectedCategoryStocks: data.stocks || [],
        loading: false
      });
      return data;
    } catch (err) {
      console.error('[SavedScansStore] Error fetching category stocks:', err);
      set({
        loading: false,
        error: err.response?.data?.detail || err.message || 'Failed to fetch scan results'
      });
      return null;
    }
  },

  /**
   * Select a category and fetch its stocks
   */
  selectCategory: (scanType) => {
    set({ selectedCategory: scanType });
    get().fetchCategoryStocks(scanType);
  },

  /**
   * Save scan results (called after a scan completes)
   */
  saveResults: async (scanType, displayName, results) => {
    try {
      const data = await savedScansAPI.saveResults(scanType, displayName, results);
      console.log(`[SavedScansStore] Saved ${data.saved_count} results for ${scanType}`);

      // Refresh categories to update counts
      await get().fetchCategories();

      // Update scan status
      set((state) => ({
        scanStatus: {
          ...state.scanStatus,
          [scanType]: {
            has_results: true,
            stock_count: data.saved_count,
            last_run_at: new Date().toISOString()
          }
        }
      }));

      return data;
    } catch (err) {
      console.error('[SavedScansStore] Error saving results:', err);
      throw err;
    }
  },

  /**
   * Delete a category and all its stocks
   */
  deleteCategory: async (scanType) => {
    try {
      const data = await savedScansAPI.deleteCategory(scanType);
      console.log(`[SavedScansStore] Deleted category ${scanType}`);

      // Remove from local state
      set((state) => ({
        categories: state.categories.filter(c => c.scan_type !== scanType),
        selectedCategory: state.selectedCategory === scanType
          ? (state.categories.length > 1 ? state.categories.find(c => c.scan_type !== scanType)?.scan_type : null)
          : state.selectedCategory,
        selectedCategoryStocks: state.selectedCategory === scanType ? [] : state.selectedCategoryStocks,
        scanStatus: {
          ...state.scanStatus,
          [scanType]: { has_results: false, stock_count: 0, last_run_at: null }
        }
      }));

      return data;
    } catch (err) {
      console.error('[SavedScansStore] Error deleting category:', err);
      set({ error: err.response?.data?.detail || err.message || 'Failed to delete category' });
      throw err;
    }
  },

  /**
   * Delete a single stock from a category
   */
  deleteStock: async (scanType, symbol) => {
    try {
      const data = await savedScansAPI.deleteStock(scanType, symbol);
      console.log(`[SavedScansStore] Deleted ${symbol} from ${scanType}`);

      // Update local state
      set((state) => ({
        selectedCategoryStocks: state.selectedCategoryStocks.filter(s => s.symbol !== symbol),
        categories: state.categories.map(c =>
          c.scan_type === scanType
            ? { ...c, stock_count: Math.max(0, c.stock_count - 1) }
            : c
        )
      }));

      return data;
    } catch (err) {
      console.error('[SavedScansStore] Error deleting stock:', err);
      set({ error: err.response?.data?.detail || err.message || 'Failed to delete stock' });
      throw err;
    }
  },

  /**
   * Delete multiple stocks from a category at once
   */
  deleteSelectedStocks: async (scanType, symbols) => {
    try {
      const data = await savedScansAPI.deleteSelectedStocks(scanType, symbols);

      // Update local state
      const symbolSet = new Set(symbols.map(s => s.toUpperCase()));
      set((state) => ({
        selectedCategoryStocks: state.selectedCategoryStocks.filter(s => !symbolSet.has(s.symbol)),
        categories: state.categories.map(c =>
          c.scan_type === scanType
            ? { ...c, stock_count: Math.max(0, c.stock_count - data.deleted_count) }
            : c
        ),
      }));

      return data;
    } catch (err) {
      console.error('[SavedScansStore] Error bulk deleting stocks:', err);
      set({ error: err.response?.data?.detail || err.message || 'Failed to delete selected stocks' });
      throw err;
    }
  },

  /**
   * Clear all saved scans
   */
  clearAll: async () => {
    try {
      const data = await savedScansAPI.clearAll();
      console.log('[SavedScansStore] Cleared all saved scans');

      set({
        categories: [],
        selectedCategory: null,
        selectedCategoryStocks: [],
        scanStatus: {}
      });

      return data;
    } catch (err) {
      console.error('[SavedScansStore] Error clearing all scans:', err);
      set({ error: err.response?.data?.detail || err.message || 'Failed to clear saved scans' });
      throw err;
    }
  },

  /**
   * Fetch scan status for all presets (for screener indicators)
   */
  fetchScanStatus: async () => {
    try {
      const data = await savedScansAPI.checkAllScans();
      set({ scanStatus: data.scan_status || {} });
      return data.scan_status;
    } catch (err) {
      console.error('[SavedScansStore] Error fetching scan status:', err);
      return {};
    }
  },

  /**
   * Check if a specific scan type has results
   */
  hasSavedResults: (scanType) => {
    const status = get().scanStatus[scanType];
    return status?.has_results || false;
  },

  /**
   * Get metadata for a scan type
   */
  getScanMetadata: (scanType) => {
    return get().scanStatus[scanType] || { has_results: false, stock_count: 0, last_run_at: null };
  },

  /**
   * Clear error state
   */
  clearError: () => set({ error: null }),
}));

export default useSavedScansStore;
