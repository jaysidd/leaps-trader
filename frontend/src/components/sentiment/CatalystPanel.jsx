/**
 * CatalystPanel Component
 *
 * Displays upcoming catalysts for a stock:
 * - Earnings dates with countdown
 * - Dividend dates
 * - Risk assessment
 * - Trading recommendations
 */
import React, { useState, useEffect } from 'react';
import { sentimentAPI } from '../../api/sentiment';

const getRiskColor = (level) => {
  switch (level?.toLowerCase()) {
    case 'low': return 'text-green-600 bg-green-50';
    case 'normal': return 'text-blue-600 bg-blue-50';
    case 'elevated': return 'text-yellow-600 bg-yellow-50';
    case 'high': return 'text-red-600 bg-red-50';
    default: return 'text-gray-600 bg-gray-50';
  }
};

const getImpactIcon = (impact) => {
  switch (impact?.toLowerCase()) {
    case 'high': return '🔴';
    case 'medium': return '🟡';
    case 'low': return '🟢';
    default: return '⚪';
  }
};

const formatDate = (dateString) => {
  if (!dateString) return 'Unknown';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
};

const DaysCountdown = ({ days }) => {
  if (days === null || days === undefined) return null;

  let color = 'text-gray-600';
  let urgency = '';

  if (days <= 0) {
    return <span className="text-green-600 font-medium">Today/Past</span>;
  } else if (days <= 7) {
    color = 'text-red-600';
    urgency = '⚠️ ';
  } else if (days <= 14) {
    color = 'text-yellow-600';
  } else if (days <= 30) {
    color = 'text-blue-600';
  }

  return (
    <span className={`font-medium ${color}`}>
      {urgency}{days} day{days !== 1 ? 's' : ''}
    </span>
  );
};

export const CatalystPanel = ({
  symbol,
  initialData = null,
  showRecommendation = true,
  compact = false,
  className = ''
}) => {
  const [catalysts, setCatalysts] = useState(initialData);
  const [loading, setLoading] = useState(!initialData);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!initialData && symbol) {
      loadCatalysts();
    }
  }, [symbol]);

  const loadCatalysts = async () => {
    try {
      setLoading(true);
      const data = await sentimentAPI.getCatalysts(symbol);
      setCatalysts(data);
    } catch (err) {
      setError('Failed to load catalysts');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className={`animate-pulse p-4 bg-gray-50 rounded-lg ${className}`}>
        <div className="h-4 bg-gray-200 rounded w-1/3 mb-2"></div>
        <div className="h-3 bg-gray-200 rounded w-2/3"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`p-4 bg-red-50 text-red-600 rounded-lg ${className}`}>
        {error}
      </div>
    );
  }

  if (!catalysts) return null;

  const riskColors = getRiskColor(catalysts.risk_level);

  if (compact) {
    return (
      <div className={`flex items-center gap-3 text-sm ${className}`}>
        {catalysts.days_to_earnings !== null && (
          <div className="flex items-center gap-1">
            <span>📅</span>
            <span className="text-gray-500">Earnings:</span>
            <DaysCountdown days={catalysts.days_to_earnings} />
          </div>
        )}
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${riskColors}`}>
          {catalysts.risk_level?.toUpperCase() || 'UNKNOWN'} Risk
        </span>
      </div>
    );
  }

  return (
    <div className={`bg-white border rounded-lg shadow-sm overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
        <h3 className="font-semibold text-gray-900 flex items-center gap-2">
          📅 Catalyst Calendar
          <span className="text-sm text-gray-500">({symbol})</span>
        </h3>
        <span className={`px-2 py-1 rounded text-xs font-medium ${riskColors}`}>
          {catalysts.risk_level?.toUpperCase() || 'UNKNOWN'} Risk
        </span>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Key Dates */}
        <div className="grid grid-cols-2 gap-4">
          {/* Earnings */}
          <div className="p-3 bg-gray-50 rounded-lg">
            <div className="text-xs text-gray-500 uppercase tracking-wide">
              Next Earnings
            </div>
            <div className="mt-1">
              <div className="text-lg font-semibold">
                {formatDate(catalysts.next_earnings_date)}
              </div>
              <div className="text-sm">
                <DaysCountdown days={catalysts.days_to_earnings} />
              </div>
            </div>
          </div>

          {/* Dividend */}
          {catalysts.next_dividend_date && (
            <div className="p-3 bg-gray-50 rounded-lg">
              <div className="text-xs text-gray-500 uppercase tracking-wide">
                Ex-Dividend
              </div>
              <div className="mt-1">
                <div className="text-lg font-semibold">
                  {formatDate(catalysts.next_dividend_date)}
                </div>
                <div className="text-sm">
                  <DaysCountdown days={catalysts.days_to_dividend} />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Catalyst Score */}
        <div className="flex items-center gap-3">
          <div className="text-sm text-gray-600">Timing Score:</div>
          <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all ${
                catalysts.catalyst_score >= 60 ? 'bg-green-500' :
                catalysts.catalyst_score >= 40 ? 'bg-yellow-500' : 'bg-red-500'
              }`}
              style={{ width: `${catalysts.catalyst_score}%` }}
            />
          </div>
          <div className="text-sm font-medium w-8">
            {catalysts.catalyst_score?.toFixed(0)}
          </div>
        </div>

        {/* Recommendation */}
        {showRecommendation && catalysts.recommendation && (
          <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="text-xs text-blue-600 uppercase tracking-wide mb-1">
              Recommendation
            </div>
            <div className="text-sm text-blue-800">
              {catalysts.recommendation}
            </div>
          </div>
        )}

        {/* Catalysts List */}
        {catalysts.catalysts?.length > 0 && (
          <div className="space-y-2">
            <div className="text-xs text-gray-500 uppercase tracking-wide">
              Upcoming Events
            </div>
            {catalysts.catalysts.map((catalyst, idx) => (
              <div
                key={idx}
                className="flex items-center gap-3 p-2 bg-gray-50 rounded"
              >
                <span>{getImpactIcon(catalyst.impact)}</span>
                <div className="flex-1">
                  <div className="text-sm font-medium">{catalyst.description}</div>
                  <div className="text-xs text-gray-500">
                    {formatDate(catalyst.date)} • {catalyst.type}
                  </div>
                </div>
                {catalyst.expected_move_pct && (
                  <span className="text-xs text-gray-600">
                    ±{catalyst.expected_move_pct.toFixed(1)}%
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * Inline earnings countdown for use in tables/cards
 */
export const EarningsCountdown = ({ daysToEarnings, className = '' }) => {
  if (daysToEarnings === null || daysToEarnings === undefined) {
    return <span className={`text-gray-400 ${className}`}>—</span>;
  }

  return (
    <span className={className}>
      <DaysCountdown days={daysToEarnings} />
    </span>
  );
};

export default CatalystPanel;
