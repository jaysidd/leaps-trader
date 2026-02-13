/**
 * AI Insights Panel - Expandable AI analysis for stocks
 */
import { useState } from 'react';
import { aiAPI } from '../../api/ai';

export default function AIInsightsPanel({ symbol, stockData }) {
  const [expanded, setExpanded] = useState(false);
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchInsights = async () => {
    if (insights) {
      setExpanded(!expanded);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await aiAPI.getStockInsights(symbol, true);
      setInsights(data);
      setExpanded(true);
    } catch (err) {
      console.error(`Failed to fetch AI insights for ${symbol}:`, err);
      setError(err.response?.data?.detail || err.message || 'Failed to load AI insights');
    } finally {
      setLoading(false);
    }
  };

  const getConvictionColor = (conviction) => {
    if (conviction >= 8) return 'text-green-600 bg-green-100';
    if (conviction >= 6) return 'text-yellow-600 bg-yellow-100';
    if (conviction >= 4) return 'text-orange-600 bg-orange-100';
    return 'text-red-600 bg-red-100';
  };

  const formatAnalysis = (text) => {
    if (!text) return null;

    // Split by common markdown patterns and format
    return text.split('\n').map((line, i) => {
      // Bold headers
      if (line.startsWith('**') && line.endsWith('**')) {
        return (
          <h4 key={i} className="font-bold text-gray-800 mt-3 mb-1">
            {line.replace(/\*\*/g, '')}
          </h4>
        );
      }
      // Bullet points
      if (line.startsWith('•') || line.startsWith('-')) {
        return (
          <li key={i} className="ml-4 text-gray-700 text-sm">
            {line.replace(/^[•-]\s*/, '')}
          </li>
        );
      }
      // Regular text
      if (line.trim()) {
        return (
          <p key={i} className="text-gray-700 text-sm">
            {line}
          </p>
        );
      }
      return null;
    });
  };

  return (
    <div className="border-t border-gray-100">
      {/* Toggle Button */}
      <button
        onClick={fetchInsights}
        disabled={loading}
        className="w-full px-4 py-2 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-lg">🤖</span>
          <span className="text-sm font-medium text-gray-700">
            AI Insights
          </span>
          {insights && (
            <span className={`text-xs font-bold px-2 py-0.5 rounded ${getConvictionColor(insights.ai_conviction)}`}>
              {insights.ai_conviction}/10
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {loading && (
            <svg className="animate-spin h-4 w-4 text-blue-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          )}
          <svg
            className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* Error State */}
      {error && (
        <div className="px-4 py-3 bg-red-50 text-red-700 text-sm">
          {error}
          <button
            onClick={() => { setError(null); setInsights(null); }}
            className="ml-2 text-red-600 underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Expanded Content */}
      {expanded && insights && (
        <div className="px-4 py-3 bg-gray-50 space-y-4">
          {/* AI Analysis */}
          <div className="bg-white rounded-lg p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-gray-800">AI Analysis</h3>
              <span className={`text-sm font-bold px-2 py-1 rounded ${getConvictionColor(insights.ai_conviction)}`}>
                Conviction: {insights.ai_conviction}/10
              </span>
            </div>
            <div className="prose prose-sm max-w-none">
              {formatAnalysis(insights.ai_analysis)}
            </div>
          </div>

          {/* Strategy Recommendation */}
          {insights.strategy_recommendation && (
            <div className="bg-blue-50 rounded-lg p-4">
              <h3 className="font-semibold text-blue-800 mb-2 flex items-center gap-2">
                <span>📊</span> Strategy Recommendation
              </h3>
              <div className="text-blue-900 text-sm whitespace-pre-wrap">
                {insights.strategy_recommendation}
              </div>
              {insights.market_regime && (
                <div className="mt-2 text-xs text-blue-600">
                  Market Regime: {insights.market_regime.toUpperCase()}
                </div>
              )}
            </div>
          )}

          {/* Stock Summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div className="bg-white rounded p-2">
              <div className="text-gray-500 text-xs">Price</div>
              <div className="font-semibold">${insights.current_price?.toFixed(2) || 'N/A'}</div>
            </div>
            <div className="bg-white rounded p-2">
              <div className="text-gray-500 text-xs">Sector</div>
              <div className="font-semibold">{insights.sector || 'N/A'}</div>
            </div>
            <div className="bg-white rounded p-2">
              <div className="text-gray-500 text-xs">Score</div>
              <div className="font-semibold">{insights.composite_score?.toFixed(0) || 'N/A'}/100</div>
            </div>
            <div className="bg-white rounded p-2">
              <div className="text-gray-500 text-xs">Screening</div>
              <div className={`font-semibold ${insights.passed_screening ? 'text-green-600' : 'text-red-600'}`}>
                {insights.passed_screening ? 'PASSED' : 'FAILED'}
              </div>
            </div>
          </div>

          {/* Model Info */}
          <div className="text-xs text-gray-400 text-right">
            Powered by {insights.model_used || 'Claude AI'}
          </div>
        </div>
      )}
    </div>
  );
}
