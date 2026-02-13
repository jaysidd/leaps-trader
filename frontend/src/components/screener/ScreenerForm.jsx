/**
 * Screener form component
 */
import { useState } from 'react';
import Button from '../common/Button';
import Card from '../common/Card';
import CriteriaForm from './CriteriaForm';

// Predefined watchlists
const PREDEFINED_LISTS = {
  'Tech Giants': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA'],
  'Semiconductors': ['NVDA', 'AMD', 'INTC', 'TSM', 'AVGO', 'QCOM', 'MU'],
  'Healthcare': ['JNJ', 'UNH', 'PFE', 'ABBV', 'TMO', 'MRK', 'LLY'],
  'Fintech': ['V', 'MA', 'PYPL', 'SQ', 'COIN', 'SOFI', 'AFRM'],
  'EV & Clean Energy': ['TSLA', 'RIVN', 'LCID', 'ENPH', 'SEDG', 'NEE'],
};

// Default moderate criteria (relaxed for current market conditions)
const DEFAULT_CRITERIA = {
  marketCapMin: 1_000_000_000,
  marketCapMax: 100_000_000_000,
  priceMin: 5,
  priceMax: 500,
  revenueGrowthMin: 10,
  earningsGrowthMin: 5,
  debtToEquityMax: 200,
  rsiMin: 25,
  rsiMax: 75,
  ivMax: 100,
  minDTE: 365,
  maxDTE: 730,
};

export default function ScreenerForm({ onSubmit, onMarketScan, loading }) {
  const [symbols, setSymbols] = useState('');
  const [topN, setTopN] = useState(15);
  const [selectedList, setSelectedList] = useState('');
  const [criteria, setCriteria] = useState(DEFAULT_CRITERIA);

  const handleSubmit = (e) => {
    e.preventDefault();

    // Parse symbols
    const symbolList = symbols
      .toUpperCase()
      .split(/[\s,;]+/)
      .map(s => s.trim())
      .filter(s => s.length > 0);

    if (symbolList.length === 0) {
      alert('Please enter at least one stock symbol');
      return;
    }

    onSubmit(symbolList, topN, criteria);
  };

  const handleSelectList = (listName) => {
    setSelectedList(listName);
    const listSymbols = PREDEFINED_LISTS[listName];
    setSymbols(listSymbols.join(', '));
  };

  return (
    <div className="space-y-6">
      {/* Criteria Form */}
      <CriteriaForm
        onCriteriaChange={setCriteria}
        initialCriteria={criteria}
      />

      {/* Stock Selection Form */}
      <Card title="🔍 Screen for 5x LEAPS Opportunities">
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Predefined Lists */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Quick Start: Select a Watchlist
            </label>
            <div className="flex flex-wrap gap-2">
              {Object.keys(PREDEFINED_LISTS).map((listName) => (
                <button
                  key={listName}
                  type="button"
                  onClick={() => handleSelectList(listName)}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    selectedList === listName
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {listName}
                </button>
              ))}
            </div>
          </div>

          {/* Stock Symbols Input */}
          <div>
            <label htmlFor="symbols" className="block text-sm font-medium text-gray-700 mb-2">
              Stock Symbols (comma or space separated)
            </label>
            <textarea
              id="symbols"
              rows={4}
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              placeholder="Enter stock symbols (e.g., AAPL, MSFT, GOOGL, NVDA, TSLA)"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              disabled={loading}
            />
            <p className="mt-1 text-sm text-gray-500">
              Example: AAPL, MSFT, GOOGL or AAPL MSFT GOOGL
            </p>
          </div>

          {/* Top N Results */}
          <div>
            <label htmlFor="topN" className="block text-sm font-medium text-gray-700 mb-2">
              Number of Top Results
            </label>
            <input
              id="topN"
              type="number"
              min={1}
              max={100}
              value={topN}
              onChange={(e) => setTopN(parseInt(e.target.value))}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              disabled={loading}
            />
          </div>

          {/* Submit Buttons */}
          <div className="flex flex-col gap-3">
            <div className="flex gap-3">
              <Button
                type="submit"
                variant="primary"
                size="lg"
                loading={loading}
                className="flex-1"
              >
                {loading ? 'Screening...' : 'Screen Selected Stocks'}
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="lg"
                onClick={() => {
                  setSymbols('');
                  setSelectedList('');
                }}
                disabled={loading}
              >
                Clear
              </Button>
            </div>
            {onMarketScan && (
              <Button
                type="button"
                variant="primary"
                size="lg"
                loading={loading}
                onClick={() => onMarketScan(criteria)}
                className="w-full bg-gradient-to-r from-green-600 to-teal-600 hover:from-green-700 hover:to-teal-700"
              >
                {loading ? 'Scanning...' : '🌐 Market Scan with These Criteria (No symbols needed)'}
              </Button>
            )}
          </div>
        </form>
      </Card>
    </div>
  );
}
