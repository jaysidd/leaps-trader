/**
 * Custom screening criteria form with sliders
 */
import { useState, useEffect } from 'react';

export default function CriteriaForm({ onCriteriaChange, initialCriteria }) {
  const [criteria, setCriteria] = useState(initialCriteria);

  // Sync with parent when initialCriteria changes
  useEffect(() => {
    if (initialCriteria) {
      setCriteria(initialCriteria);
    }
  }, [initialCriteria]);

  const handleChange = (field, value) => {
    const newCriteria = { ...criteria, [field]: value };
    setCriteria(newCriteria);
    onCriteriaChange(newCriteria);
  };

  const formatMarketCap = (value) => {
    if (value >= 1_000_000_000) {
      return `$${(value / 1_000_000_000).toFixed(1)}B`;
    }
    return `$${(value / 1_000_000).toFixed(0)}M`;
  };

  return (
    <div className="space-y-6">
      {/* Market Cap */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Market Cap Range
        </label>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-gray-600">Min: {formatMarketCap(criteria.marketCapMin)}</label>
            <input
              type="range"
              min="100000000"
              max="100000000000"
              step="100000000"
              value={criteria.marketCapMin}
              onChange={(e) => handleChange('marketCapMin', parseInt(e.target.value))}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-xs text-gray-600">Max: {formatMarketCap(criteria.marketCapMax)}</label>
            <input
              type="range"
              min="1000000000"
              max="500000000000"
              step="1000000000"
              value={criteria.marketCapMax}
              onChange={(e) => handleChange('marketCapMax', parseInt(e.target.value))}
              className="w-full"
            />
          </div>
        </div>
      </div>

      {/* Stock Price Range */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Stock Price Range: ${criteria.priceMin || 5} - ${criteria.priceMax || 500}
        </label>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-gray-600">Min: ${criteria.priceMin || 5}</label>
            <input
              type="range"
              min="1"
              max="100"
              step="1"
              value={criteria.priceMin || 5}
              onChange={(e) => handleChange('priceMin', parseInt(e.target.value))}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-xs text-gray-600">Max: ${criteria.priceMax || 500}</label>
            <input
              type="range"
              min="50"
              max="1000"
              step="10"
              value={criteria.priceMax || 500}
              onChange={(e) => handleChange('priceMax', parseInt(e.target.value))}
              className="w-full"
            />
          </div>
        </div>
      </div>

      {/* Revenue Growth */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Min Revenue Growth (YoY): {criteria.revenueGrowthMin}%
        </label>
        <input
          type="range"
          min="0"
          max="100"
          step="5"
          value={criteria.revenueGrowthMin}
          onChange={(e) => handleChange('revenueGrowthMin', parseInt(e.target.value))}
          className="w-full"
        />
      </div>

      {/* Earnings Growth */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Min Earnings Growth (YoY): {criteria.earningsGrowthMin}%
        </label>
        <input
          type="range"
          min="0"
          max="100"
          step="5"
          value={criteria.earningsGrowthMin}
          onChange={(e) => handleChange('earningsGrowthMin', parseInt(e.target.value))}
          className="w-full"
        />
      </div>

      {/* Debt to Equity */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Max Debt-to-Equity: {criteria.debtToEquityMax}%
        </label>
        <input
          type="range"
          min="0"
          max="300"
          step="10"
          value={criteria.debtToEquityMax}
          onChange={(e) => handleChange('debtToEquityMax', parseInt(e.target.value))}
          className="w-full"
        />
      </div>

      {/* RSI Range */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          RSI Range: {criteria.rsiMin} - {criteria.rsiMax}
        </label>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-gray-600">Min</label>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={criteria.rsiMin}
              onChange={(e) => handleChange('rsiMin', parseInt(e.target.value))}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-xs text-gray-600">Max</label>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={criteria.rsiMax}
              onChange={(e) => handleChange('rsiMax', parseInt(e.target.value))}
              className="w-full"
            />
          </div>
        </div>
      </div>

      {/* Implied Volatility */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Max Implied Volatility: {criteria.ivMax}%
        </label>
        <input
          type="range"
          min="20"
          max="150"
          step="5"
          value={criteria.ivMax}
          onChange={(e) => handleChange('ivMax', parseInt(e.target.value))}
          className="w-full"
        />
      </div>

      {/* LEAPS Days to Expiration */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          LEAPS Days to Expiration: {criteria.minDTE} - {criteria.maxDTE} days
        </label>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-gray-600">Min</label>
            <input
              type="range"
              min="180"
              max="730"
              step="30"
              value={criteria.minDTE}
              onChange={(e) => handleChange('minDTE', parseInt(e.target.value))}
              className="w-full"
            />
          </div>
          <div>
            <label className="text-xs text-gray-600">Max</label>
            <input
              type="range"
              min="365"
              max="1095"
              step="30"
              value={criteria.maxDTE}
              onChange={(e) => handleChange('maxDTE', parseInt(e.target.value))}
              className="w-full"
            />
          </div>
        </div>
      </div>

      {/* Current Criteria Summary */}
      <div className="p-4 bg-gray-50 rounded-lg">
        <h4 className="font-semibold text-sm text-gray-700 mb-2">Active Criteria:</h4>
        <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
          <div>• Market Cap: {formatMarketCap(criteria.marketCapMin)} - {formatMarketCap(criteria.marketCapMax)}</div>
          <div>• Stock Price: ${criteria.priceMin || 5} - ${criteria.priceMax || 500}</div>
          <div>• Revenue Growth: &gt;{criteria.revenueGrowthMin}%</div>
          <div>• Earnings Growth: &gt;{criteria.earningsGrowthMin}%</div>
          <div>• Debt/Equity: &lt;{criteria.debtToEquityMax}%</div>
          <div>• RSI: {criteria.rsiMin}-{criteria.rsiMax}</div>
          <div>• Max IV: &lt;{criteria.ivMax}%</div>
        </div>
      </div>
    </div>
  );
}
