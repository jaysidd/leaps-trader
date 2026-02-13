/**
 * User Alerts List Component
 * Display and manage user-created dynamic alerts
 */
import { useState, useEffect, useCallback } from 'react';
import Card from '../common/Card';
import Button from '../common/Button';
import { listAlerts, toggleAlert, deleteAlert, checkAlertNow, checkAllAlerts } from '../../api/userAlerts';

// Alert type icons
const ALERT_TYPE_ICONS = {
  iv_rank_below: '📉',
  iv_rank_above: '📈',
  price_above: '⬆️',
  price_below: '⬇️',
  rsi_oversold: '🔻',
  rsi_overbought: '🔺',
  price_cross_sma: '📊',
  earnings_approaching: '📅',
  screening_match: '✅',
  leaps_available: '🎯',
};

// Status colors
const STATUS_COLORS = {
  active: 'bg-green-100 text-green-800 border-green-200',
  inactive: 'bg-gray-100 text-gray-600 border-gray-200',
};

export default function UserAlertsList({ onSelectAlert, onEditAlert, refreshTrigger }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [checkingAll, setCheckingAll] = useState(false);
  const [checkingId, setCheckingId] = useState(null);

  // Pagination
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 10;

  // Filters
  const [showActive, setShowActive] = useState(null); // null = all, true = active, false = inactive

  const fetchAlerts = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const params = {
        page,
        page_size: pageSize,
      };

      if (showActive !== null) {
        params.is_active = showActive;
      }

      const data = await listAlerts(params);
      setAlerts(data.alerts);
      setTotal(data.total);
    } catch (err) {
      console.error('Error fetching alerts:', err);
      setError('Failed to load alerts');
    } finally {
      setLoading(false);
    }
  }, [page, showActive]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts, refreshTrigger]);

  const handleToggle = async (alertId) => {
    try {
      await toggleAlert(alertId);
      fetchAlerts();
    } catch (err) {
      console.error('Error toggling alert:', err);
    }
  };

  const handleDelete = async (alertId) => {
    if (!window.confirm('Are you sure you want to delete this alert?')) return;

    try {
      await deleteAlert(alertId);
      fetchAlerts();
    } catch (err) {
      console.error('Error deleting alert:', err);
    }
  };

  const handleCheckNow = async (alertId) => {
    try {
      setCheckingId(alertId);
      const result = await checkAlertNow(alertId);

      if (result.triggered) {
        alert(`Alert triggered! ${result.notification.message}`);
      } else {
        alert('Alert conditions not met at this time.');
      }

      fetchAlerts();
    } catch (err) {
      console.error('Error checking alert:', err);
    } finally {
      setCheckingId(null);
    }
  };

  const handleCheckAll = async () => {
    try {
      setCheckingAll(true);
      const result = await checkAllAlerts();

      if (result.triggered > 0) {
        alert(`${result.triggered} alert(s) triggered!`);
      } else {
        alert(`Checked ${result.checked} alerts. No conditions met.`);
      }

      fetchAlerts();
    } catch (err) {
      console.error('Error checking all alerts:', err);
    } finally {
      setCheckingAll(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  if (loading && alerts.length === 0) {
    return (
      <Card title="Your Alerts">
        <div className="flex justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with filters and actions */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">Filter:</span>
            <button
              onClick={() => setShowActive(null)}
              className={`px-3 py-1 rounded text-sm ${
                showActive === null ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'
              }`}
            >
              All ({total})
            </button>
            <button
              onClick={() => setShowActive(true)}
              className={`px-3 py-1 rounded text-sm ${
                showActive === true ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-700'
              }`}
            >
              Active
            </button>
            <button
              onClick={() => setShowActive(false)}
              className={`px-3 py-1 rounded text-sm ${
                showActive === false ? 'bg-gray-600 text-white' : 'bg-gray-100 text-gray-700'
              }`}
            >
              Inactive
            </button>
          </div>

          <div className="flex gap-2">
            <Button
              onClick={handleCheckAll}
              disabled={checkingAll}
              variant="secondary"
            >
              {checkingAll ? 'Checking...' : 'Check All Now'}
            </Button>
            <Button onClick={fetchAlerts} variant="secondary">
              Refresh
            </Button>
          </div>
        </div>
      </Card>

      {/* Error message */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
          {error}
        </div>
      )}

      {/* Empty state */}
      {!loading && alerts.length === 0 && (
        <Card>
          <div className="text-center py-12">
            <div className="text-6xl mb-4">🔔</div>
            <h3 className="text-xl font-semibold text-gray-800 mb-2">No Alerts Yet</h3>
            <p className="text-gray-600">
              Create your first alert to get notified when conditions are met.
            </p>
          </div>
        </Card>
      )}

      {/* Alerts list */}
      {alerts.map((alert) => (
        <Card key={alert.id}>
          <div className="flex items-start justify-between gap-4">
            {/* Left side - Alert info */}
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-2xl">
                  {ALERT_TYPE_ICONS[alert.alert_type] || '🔔'}
                </span>
                <h3 className="font-semibold text-gray-900">{alert.name}</h3>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  alert.is_active ? STATUS_COLORS.active : STATUS_COLORS.inactive
                }`}>
                  {alert.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>

              <div className="space-y-1 text-sm">
                <div className="flex items-center gap-4 text-gray-600">
                  <span className="font-medium text-blue-600">{alert.symbol}</span>
                  <span>{alert.alert_type_description}</span>
                  {alert.threshold_value && (
                    <span className="font-medium">Threshold: {alert.threshold_value}</span>
                  )}
                </div>

                <div className="flex items-center gap-4 text-gray-500 text-xs">
                  <span>Frequency: {alert.frequency}</span>
                  <span>Triggered: {alert.times_triggered}x</span>
                  {alert.last_triggered_at && (
                    <span>Last: {new Date(alert.last_triggered_at).toLocaleDateString()}</span>
                  )}
                </div>

                {alert.description && (
                  <p className="text-gray-500 italic">{alert.description}</p>
                )}
              </div>
            </div>

            {/* Right side - Actions */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleCheckNow(alert.id)}
                disabled={checkingId === alert.id}
                className="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200 disabled:opacity-50"
                title="Check now"
              >
                {checkingId === alert.id ? '...' : '▶'}
              </button>
              {onEditAlert && (
                <button
                  onClick={() => onEditAlert(alert)}
                  className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                  title="Edit"
                >
                  ✏️
                </button>
              )}
              <button
                onClick={() => handleToggle(alert.id)}
                className={`px-3 py-1 text-sm rounded ${
                  alert.is_active
                    ? 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200'
                    : 'bg-green-100 text-green-700 hover:bg-green-200'
                }`}
                title={alert.is_active ? 'Pause' : 'Resume'}
              >
                {alert.is_active ? '⏸' : '▶'}
              </button>
              <button
                onClick={() => handleDelete(alert.id)}
                className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
                title="Delete"
              >
                ✕
              </button>
            </div>
          </div>
        </Card>
      ))}

      {/* Pagination */}
      {totalPages > 1 && (
        <Card>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-600">
              Showing {(page - 1) * pageSize + 1} - {Math.min(page * pageSize, total)} of {total}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 border rounded hover:bg-gray-50 disabled:opacity-50"
              >
                Previous
              </button>
              <span className="px-3 py-1 text-gray-600">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1 border rounded hover:bg-gray-50 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
