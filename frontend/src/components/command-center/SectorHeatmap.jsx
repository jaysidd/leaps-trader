/**
 * Sector Heatmap - Visual representation of sector performance
 */
export default function SectorHeatmap({ data, loading }) {
  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="grid grid-cols-4 gap-2">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <div key={i} className="h-12 bg-gray-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  const sectors = data?.all || data || [];

  // Calculate max absolute change for scaling
  const maxChange = Math.max(...sectors.map((s) => Math.abs(s.change_percent || 0)), 1);

  const getColor = (changePercent) => {
    const intensity = Math.min(Math.abs(changePercent) / maxChange, 1);

    if (changePercent > 0) {
      // Green gradient
      const r = Math.round(34 - 34 * intensity);
      const g = Math.round(197 - 97 * intensity);
      const b = Math.round(94 - 94 * intensity);
      return `rgb(${r}, ${g}, ${b})`;
    } else if (changePercent < 0) {
      // Red gradient
      const r = Math.round(220 - 20 * intensity);
      const g = Math.round(38 - 38 * intensity);
      const b = Math.round(38 - 38 * intensity);
      return `rgb(${r}, ${g}, ${b})`;
    }
    return '#6b7280'; // Gray for no change
  };

  const getTextColor = (changePercent) => {
    const intensity = Math.abs(changePercent) / maxChange;
    return intensity > 0.5 ? 'text-white' : 'text-gray-200';
  };

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
          Sectors
        </h3>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="text-red-400">▼ Weak</span>
          <span>|</span>
          <span className="text-green-400">▲ Strong</span>
        </div>
      </div>

      <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
        {sectors.map((sector) => (
          <div
            key={sector.symbol}
            className={`rounded-lg p-2 text-center transition-transform hover:scale-105 cursor-pointer ${getTextColor(sector.change_percent)}`}
            style={{ backgroundColor: getColor(sector.change_percent) }}
            title={`${sector.name}: ${sector.change_percent >= 0 ? '+' : ''}${sector.change_percent?.toFixed(2)}%`}
          >
            <div className="text-xs font-medium truncate">{sector.symbol}</div>
            <div className="text-sm font-bold">
              {sector.change_percent >= 0 ? '+' : ''}
              {sector.change_percent?.toFixed(1)}%
            </div>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="mt-4 pt-3 border-t border-gray-700">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="text-gray-400">Leading:</span>
            {sectors.slice(0, 2).map((s) => (
              <span key={s.symbol} className="text-green-400">
                {s.symbol}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-gray-400">Lagging:</span>
            {sectors.slice(-2).map((s) => (
              <span key={s.symbol} className="text-red-400">
                {s.symbol}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
