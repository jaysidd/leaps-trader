/**
 * AlertCard Component
 * Displays a single webhook alert in a card format similar to screener results
 */
import { formatCurrency, formatDateTime } from '../../utils/formatters';

// Status badge colors
const STATUS_COLORS = {
  active: 'bg-green-100 text-green-800 border-green-200',
  triggered: 'bg-blue-100 text-blue-800 border-blue-200',
  expired: 'bg-gray-100 text-gray-600 border-gray-200',
  dismissed: 'bg-red-100 text-red-800 border-red-200',
};

// Event type badge colors
const EVENT_TYPE_COLORS = {
  new_setup: 'bg-purple-100 text-purple-800',
  trigger: 'bg-orange-100 text-orange-800',
};

// Direction badge colors
const DIRECTION_COLORS = {
  buy: 'bg-green-500 text-white',
  sell: 'bg-red-500 text-white',
};

export default function AlertCard({ alert, onStatusUpdate, onDelete, onViewDetails }) {
  const {
    id,
    provider,
    setup_id,
    event_type,
    symbol,
    direction,
    entry_zone,
    stop_loss,
    tp1,
    tp2,
    current_price,
    alert_timestamp,
    received_at,
    status,
  } = alert;

  // Calculate risk/reward ratio if we have the data
  const calculateRiskReward = () => {
    if (!entry_zone || !stop_loss || !tp1) return null;

    const entryMid = (entry_zone[0] + entry_zone[1]) / 2;
    const risk = Math.abs(entryMid - stop_loss);
    const reward = Math.abs(tp1 - entryMid);

    if (risk === 0) return null;
    return (reward / risk).toFixed(2);
  };

  const riskReward = calculateRiskReward();

  // Format entry zone
  const formatEntryZone = () => {
    if (!entry_zone || entry_zone.length < 2) return 'N/A';
    return `${formatCurrency(entry_zone[0])} - ${formatCurrency(entry_zone[1])}`;
  };

  return (
    <div className="bg-white rounded-lg shadow-md border border-gray-200 overflow-hidden hover:shadow-lg transition-shadow">
      {/* Header */}
      <div className={`px-4 py-3 flex items-center justify-between ${
        direction === 'buy' ? 'bg-green-50 border-b border-green-100' : 'bg-red-50 border-b border-red-100'
      }`}>
        <div className="flex items-center gap-3">
          {/* Symbol */}
          <div className="text-xl font-bold text-gray-900">{symbol}</div>

          {/* Direction Badge */}
          <span className={`px-3 py-1 rounded-full text-sm font-semibold uppercase ${DIRECTION_COLORS[direction] || 'bg-gray-500 text-white'}`}>
            {direction}
          </span>

          {/* Event Type Badge */}
          <span className={`px-2 py-1 rounded text-xs font-medium ${EVENT_TYPE_COLORS[event_type] || 'bg-gray-100 text-gray-800'}`}>
            {event_type === 'new_setup' ? '🆕 New Setup' : '🎯 Triggered'}
          </span>

          {/* Status Badge */}
          <span className={`px-2 py-1 rounded border text-xs font-medium ${STATUS_COLORS[status] || 'bg-gray-100 text-gray-600'}`}>
            {status}
          </span>
        </div>

        {/* Provider and Setup ID */}
        <div className="text-sm text-gray-500">
          <span className="font-medium">Provider:</span> {provider}
          <span className="ml-3 font-mono text-xs text-gray-400" title={setup_id}>
            ID: {setup_id?.slice(0, 8)}...
          </span>
        </div>
      </div>

      {/* Body */}
      <div className="p-4">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {/* Current Price */}
          <div>
            <div className="text-xs text-gray-500 uppercase font-medium">Current Price</div>
            <div className="text-lg font-semibold text-gray-900">{formatCurrency(current_price)}</div>
          </div>

          {/* Entry Zone */}
          <div>
            <div className="text-xs text-gray-500 uppercase font-medium">Entry Zone</div>
            <div className="text-lg font-semibold text-blue-600">{formatEntryZone()}</div>
          </div>

          {/* Stop Loss */}
          <div>
            <div className="text-xs text-gray-500 uppercase font-medium">Stop Loss</div>
            <div className="text-lg font-semibold text-red-600">{formatCurrency(stop_loss)}</div>
          </div>

          {/* Take Profit 1 */}
          <div>
            <div className="text-xs text-gray-500 uppercase font-medium">TP1</div>
            <div className="text-lg font-semibold text-green-600">{formatCurrency(tp1)}</div>
          </div>

          {/* Take Profit 2 */}
          <div>
            <div className="text-xs text-gray-500 uppercase font-medium">TP2</div>
            <div className="text-lg font-semibold text-green-700">{formatCurrency(tp2)}</div>
          </div>

          {/* Risk/Reward */}
          {riskReward && (
            <div>
              <div className="text-xs text-gray-500 uppercase font-medium">R:R Ratio</div>
              <div className="text-lg font-semibold text-purple-600">1:{riskReward}</div>
            </div>
          )}
        </div>

        {/* Timestamps */}
        <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between text-sm text-gray-500">
          <div>
            <span className="font-medium">Alert Time:</span> {formatDateTime(alert_timestamp)}
          </div>
          <div>
            <span className="font-medium">Received:</span> {formatDateTime(received_at)}
          </div>
        </div>
      </div>

      {/* Actions Footer */}
      <div className="px-4 py-3 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
        {/* Status Actions */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600 mr-2">Set Status:</span>
          {status !== 'active' && (
            <button
              onClick={() => onStatusUpdate(id, 'active')}
              className="px-2 py-1 text-xs bg-green-100 text-green-700 rounded hover:bg-green-200 transition-colors"
            >
              Active
            </button>
          )}
          {status !== 'triggered' && (
            <button
              onClick={() => onStatusUpdate(id, 'triggered')}
              className="px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors"
            >
              Triggered
            </button>
          )}
          {status !== 'expired' && (
            <button
              onClick={() => onStatusUpdate(id, 'expired')}
              className="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors"
            >
              Expired
            </button>
          )}
          {status !== 'dismissed' && (
            <button
              onClick={() => onStatusUpdate(id, 'dismissed')}
              className="px-2 py-1 text-xs bg-red-100 text-red-700 rounded hover:bg-red-200 transition-colors"
            >
              Dismiss
            </button>
          )}
        </div>

        {/* Main Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => onViewDetails(alert)}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            View Details →
          </button>
          <button
            onClick={() => onDelete(id)}
            className="px-3 py-2 text-sm text-red-600 hover:text-red-800 hover:bg-red-50 rounded-lg transition-colors"
          >
            🗑️
          </button>
        </div>
      </div>
    </div>
  );
}
