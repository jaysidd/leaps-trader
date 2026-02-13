/**
 * Market Pulse Widget - Shows major indices and their performance
 */
import { useState, useEffect } from 'react';

const TrendIcon = ({ trend }) => {
  if (trend === 'up') {
    return <span className="text-green-500">▲</span>;
  } else if (trend === 'down') {
    return <span className="text-red-500">▼</span>;
  }
  return <span className="text-gray-400">─</span>;
};

const IndexCard = ({ index }) => {
  const isPositive = index.change_percent >= 0;
  const changeColor = isPositive ? 'text-green-500' : 'text-red-500';
  const bgColor = isPositive ? 'bg-green-500/10' : 'bg-red-500/10';

  return (
    <div className={`${bgColor} rounded-lg p-3 border border-gray-700`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-gray-300">{index.symbol}</span>
        <TrendIcon trend={index.trend} />
      </div>
      <div className="text-lg font-bold text-white">
        {index.price?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
      <div className={`text-sm ${changeColor}`}>
        {isPositive ? '+' : ''}{index.change_percent?.toFixed(2)}%
      </div>
    </div>
  );
};

export default function MarketPulse({ data, loading }) {
  const indices = data?.indices || [];
  const volatility = data?.volatility || {};
  const vix = volatility?.vix || {};

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-20 bg-gray-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          Market Pulse
        </h3>
        {vix.value && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-400">VIX:</span>
            <span className={`font-medium ${
              vix.level === 'low' ? 'text-green-400' :
              vix.level === 'normal' ? 'text-yellow-400' :
              vix.level === 'elevated' ? 'text-orange-400' :
              'text-red-400'
            }`}>
              {vix.value?.toFixed(1)}
            </span>
            <span className="text-gray-500 text-xs">({vix.level})</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {indices.map((index) => (
          <IndexCard key={index.symbol} index={index} />
        ))}
      </div>
    </div>
  );
}
