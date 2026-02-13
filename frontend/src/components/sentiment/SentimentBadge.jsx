/**
 * SentimentBadge Component
 *
 * Displays a compact sentiment indicator with score and label.
 * Can be used in stock cards and tables.
 */
import React from 'react';

const getSentimentColor = (score) => {
  if (score >= 65) return { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-300' };
  if (score >= 50) return { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-300' };
  if (score >= 35) return { bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-300' };
  return { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-300' };
};

const getSentimentEmoji = (label) => {
  switch (label?.toLowerCase()) {
    case 'bullish': return '🟢';
    case 'bearish': return '🔴';
    default: return '🟡';
  }
};

export const SentimentBadge = ({
  score,
  label = 'neutral',
  showScore = true,
  size = 'md',
  className = ''
}) => {
  const colors = getSentimentColor(score);
  const emoji = getSentimentEmoji(label);

  const sizeClasses = {
    sm: 'text-xs px-1.5 py-0.5',
    md: 'text-sm px-2 py-1',
    lg: 'text-base px-3 py-1.5'
  };

  return (
    <span
      className={`
        inline-flex items-center gap-1 rounded-full font-medium border
        ${colors.bg} ${colors.text} ${colors.border}
        ${sizeClasses[size]}
        ${className}
      `}
      title={`Sentiment: ${label} (${score?.toFixed(0) || 0}/100)`}
    >
      <span>{emoji}</span>
      {showScore && <span>{score?.toFixed(0) || 0}</span>}
      <span className="capitalize">{label}</span>
    </span>
  );
};

/**
 * Compact version showing just the score with color coding
 */
export const SentimentScore = ({ score, size = 'md', className = '' }) => {
  const colors = getSentimentColor(score);

  const sizeClasses = {
    sm: 'text-xs w-6 h-6',
    md: 'text-sm w-8 h-8',
    lg: 'text-base w-10 h-10'
  };

  return (
    <div
      className={`
        inline-flex items-center justify-center rounded-full font-bold
        ${colors.bg} ${colors.text}
        ${sizeClasses[size]}
        ${className}
      `}
      title={`Sentiment Score: ${score?.toFixed(0) || 0}/100`}
    >
      {score?.toFixed(0) || '-'}
    </div>
  );
};

/**
 * Detailed sentiment breakdown showing all components
 */
export const SentimentBreakdown = ({
  scores = {},
  flags = {},
  className = ''
}) => {
  const { news = 50, analyst = 50, insider = 50, catalyst = 50 } = scores;

  const ScoreBar = ({ label, value, icon }) => {
    const width = `${Math.min(100, Math.max(0, value))}%`;
    const colors = getSentimentColor(value);

    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="w-16 text-gray-600">{icon} {label}</span>
        <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full ${colors.bg} transition-all duration-300`}
            style={{ width }}
          />
        </div>
        <span className={`w-12 text-right font-medium ${colors.text}`}>
          {value?.toFixed(0)}<span className="text-xs text-gray-400 font-normal">/100</span>
        </span>
      </div>
    );
  };

  return (
    <div className={`space-y-2 ${className}`}>
      <ScoreBar label="News" value={news} icon="📰" />
      <ScoreBar label="Analyst" value={analyst} icon="📊" />
      <ScoreBar label="Insider" value={insider} icon="👤" />
      <ScoreBar label="Catalyst" value={catalyst} icon="📅" />

      {/* Flags */}
      {Object.entries(flags).some(([_, v]) => v) && (
        <div className="flex flex-wrap gap-1 pt-2 border-t">
          {flags.has_recent_upgrade && (
            <span className="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded">
              ⬆️ Upgrade
            </span>
          )}
          {flags.has_recent_downgrade && (
            <span className="text-xs px-2 py-0.5 bg-red-100 text-red-700 rounded">
              ⬇️ Downgrade
            </span>
          )}
          {flags.insider_buying && (
            <span className="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded">
              💰 Insider Buying
            </span>
          )}
          {flags.insider_selling && (
            <span className="text-xs px-2 py-0.5 bg-red-100 text-red-700 rounded">
              💸 Insider Selling
            </span>
          )}
          {flags.earnings_risk && (
            <span className="text-xs px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded">
              ⚠️ Earnings Soon
            </span>
          )}
        </div>
      )}
    </div>
  );
};

export default SentimentBadge;
