/**
 * Alerts Tab Component
 * Displays webhook alerts from trading signal providers
 * AND user-created dynamic alerts from LEAPS Trader
 */
import { useState, useEffect, useCallback } from 'react';
import Card from '../common/Card';
import { getAlerts, getProviders, getWebhookStats, updateAlertStatus, deleteAlert, clearAlerts } from '../../api/alerts';
import { listAlerts as listUserAlerts, listNotifications, markNotificationRead, clearNotifications } from '../../api/userAlerts';
import AlertCard from './AlertCard';
import AlertBuilder from './AlertBuilder';
import UserAlertsList from './UserAlertsList';

// Built-in provider for LEAPS Trader alerts
const LEAPS_TRADER_PROVIDER = 'LEAPS Trader';

// Status badge colors
const STATUS_COLORS = {
  active: 'bg-green-100 text-green-800 border-green-200',
  triggered: 'bg-blue-100 text-blue-800 border-blue-200',
  expired: 'bg-gray-100 text-gray-600 border-gray-200',
  dismissed: 'bg-red-100 text-red-800 border-red-200',
};

// Notification status colors
const NOTIFICATION_STATUS_COLORS = {
  unread: 'bg-blue-100 text-blue-800',
  read: 'bg-gray-100 text-gray-600',
};

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

// Event type badge colors (for webhook alerts)
const EVENT_TYPE_COLORS = {
  new_setup: 'bg-purple-100 text-purple-800',
  trigger: 'bg-orange-100 text-orange-800',
};

// Direction badge colors
const DIRECTION_COLORS = {
  buy: 'bg-green-500 text-white',
  sell: 'bg-red-500 text-white',
};

export default function AlertsTab({ onSelectAlert }) {
  // Common state
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedProvider, setSelectedProvider] = useState(LEAPS_TRADER_PROVIDER);

  // Webhook alerts state
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState(null);
  const [selectedStatus, setSelectedStatus] = useState('');
  const [selectedEventType, setSelectedEventType] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [total, setTotal] = useState(0);

  // LEAPS Trader state
  const [showAlertBuilder, setShowAlertBuilder] = useState(false);
  const [editingAlert, setEditingAlert] = useState(null); // Alert being edited
  const [notifications, setNotifications] = useState([]);
  const [notificationsPage, setNotificationsPage] = useState(1);
  const [notificationsTotal, setNotificationsTotal] = useState(0);
  const [userAlertsCount, setUserAlertsCount] = useState(0);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [activeView, setActiveView] = useState('profiles'); // 'profiles' or 'notifications'

  // Check if LEAPS Trader is selected
  const isLeapsTrader = selectedProvider === LEAPS_TRADER_PROVIDER;

  // Fetch webhook alerts
  const fetchAlerts = useCallback(async () => {
    if (isLeapsTrader) return;

    try {
      setLoading(true);
      setError(null);

      const params = {
        page,
        page_size: pageSize,
      };

      if (selectedProvider) params.provider = selectedProvider;
      if (selectedStatus) params.status = selectedStatus;
      if (selectedEventType) params.event_type = selectedEventType;

      const response = await getAlerts(params);
      setAlerts(response.alerts);
      setTotal(response.total);
    } catch (err) {
      console.error('Error fetching alerts:', err);
      setError('Failed to load alerts. Make sure the backend is running.');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, selectedProvider, selectedStatus, selectedEventType, isLeapsTrader]);

  // Fetch providers and stats
  const fetchProvidersAndStats = useCallback(async () => {
    try {
      const [providersRes, statsRes] = await Promise.all([
        getProviders(),
        getWebhookStats(),
      ]);
      // Add LEAPS Trader as first provider option
      setProviders([LEAPS_TRADER_PROVIDER, ...(providersRes.providers || [])]);
      setStats(statsRes);
    } catch (err) {
      console.error('Error fetching providers/stats:', err);
      // Still show LEAPS Trader even if webhook providers fail
      setProviders([LEAPS_TRADER_PROVIDER]);
    }
  }, []);

  // Fetch LEAPS Trader notifications
  const fetchNotifications = useCallback(async () => {
    if (!isLeapsTrader) return;

    try {
      setLoading(true);
      const response = await listNotifications({
        page: notificationsPage,
        page_size: pageSize,
      });
      setNotifications(response.notifications || []);
      setNotificationsTotal(response.total || 0);
    } catch (err) {
      console.error('Error fetching notifications:', err);
    } finally {
      setLoading(false);
    }
  }, [isLeapsTrader, notificationsPage, pageSize]);

  // Fetch user alerts count for stats
  const fetchUserAlertsCount = useCallback(async () => {
    if (!isLeapsTrader) return;

    try {
      const response = await listUserAlerts({ page: 1, page_size: 1 });
      setUserAlertsCount(response.total || 0);
    } catch (err) {
      console.error('Error fetching user alerts count:', err);
    }
  }, [isLeapsTrader]);

  // Initial load
  useEffect(() => {
    fetchProvidersAndStats();
  }, [fetchProvidersAndStats]);

  // Load data when provider changes
  useEffect(() => {
    if (isLeapsTrader) {
      fetchNotifications();
      fetchUserAlertsCount();
    } else {
      fetchAlerts();
    }
  }, [isLeapsTrader, fetchAlerts, fetchNotifications, fetchUserAlertsCount]);

  // Handle status update (webhook alerts)
  const handleStatusUpdate = async (alertId, newStatus) => {
    try {
      await updateAlertStatus(alertId, newStatus);
      fetchAlerts();
      fetchProvidersAndStats();
    } catch (err) {
      console.error('Error updating status:', err);
      setError('Failed to update alert status');
    }
  };

  // Handle delete (webhook alerts)
  const handleDelete = async (alertId) => {
    if (!window.confirm('Are you sure you want to delete this alert?')) return;

    try {
      await deleteAlert(alertId);
      fetchAlerts();
      fetchProvidersAndStats();
    } catch (err) {
      console.error('Error deleting alert:', err);
      setError('Failed to delete alert');
    }
  };

  // Handle clear all (webhook alerts)
  const handleClearAll = async () => {
    if (!window.confirm('Are you sure you want to clear all alerts? This cannot be undone.')) return;

    try {
      await clearAlerts({
        provider: selectedProvider || undefined,
        status: selectedStatus || undefined,
      });
      fetchAlerts();
      fetchProvidersAndStats();
    } catch (err) {
      console.error('Error clearing alerts:', err);
      setError('Failed to clear alerts');
    }
  };

  // Handle notification read
  const handleMarkRead = async (notificationId) => {
    try {
      await markNotificationRead(notificationId);
      fetchNotifications();
    } catch (err) {
      console.error('Error marking notification read:', err);
    }
  };

  // Handle clear notifications
  const handleClearNotifications = async () => {
    if (!window.confirm('Clear all notifications?')) return;

    try {
      await clearNotifications();
      fetchNotifications();
    } catch (err) {
      console.error('Error clearing notifications:', err);
    }
  };

  // Reset filters
  const resetFilters = () => {
    setSelectedProvider('');
    setSelectedStatus('');
    setSelectedEventType('');
    setPage(1);
  };

  // Handle alert created
  const handleAlertCreated = () => {
    setShowAlertBuilder(false);
    setEditingAlert(null);
    setRefreshTrigger(prev => prev + 1);
    fetchUserAlertsCount();
  };

  // Handle alert updated
  const handleAlertUpdated = () => {
    setShowAlertBuilder(false);
    setEditingAlert(null);
    setRefreshTrigger(prev => prev + 1);
  };

  // Handle edit alert
  const handleEditAlert = (alert) => {
    setEditingAlert(alert);
    setShowAlertBuilder(true);
  };

  // Handle close builder
  const handleCloseBuilder = () => {
    setShowAlertBuilder(false);
    setEditingAlert(null);
  };

  const totalPages = Math.ceil(total / pageSize);
  const notificationsTotalPages = Math.ceil(notificationsTotal / pageSize);

  // Format notification date
  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  return (
    <div className="space-y-6">
      {/* Stats Summary - Different for LEAPS Trader */}
      {isLeapsTrader ? (
        <Card>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-blue-600">{userAlertsCount}</div>
              <div className="text-sm text-gray-600">Alert Profiles</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-green-600">{notificationsTotal}</div>
              <div className="text-sm text-gray-600">Triggered Alerts</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-purple-600">
                {notifications.filter(n => !n.is_read).length}
              </div>
              <div className="text-sm text-gray-600">Unread</div>
            </div>
            <div className="text-center">
              <button
                onClick={() => setShowAlertBuilder(true)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
              >
                + Add Alert Profile
              </button>
            </div>
          </div>
        </Card>
      ) : stats && (
        <Card>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-gray-800">{stats.total}</div>
              <div className="text-sm text-gray-600">Total Alerts</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-green-600">{stats.by_status?.active || 0}</div>
              <div className="text-sm text-gray-600">Active</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-blue-600">{stats.by_status?.triggered || 0}</div>
              <div className="text-sm text-gray-600">Triggered</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-purple-600">{stats.by_event_type?.new_setup || 0}</div>
              <div className="text-sm text-gray-600">New Setups</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-orange-600">{stats.by_event_type?.trigger || 0}</div>
              <div className="text-sm text-gray-600">Triggers</div>
            </div>
          </div>
        </Card>
      )}

      {/* Filters */}
      <Card>
        <div className="flex flex-wrap items-center gap-4">
          {/* Provider Filter */}
          <div className="flex-1 min-w-[150px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
            <select
              value={selectedProvider}
              onChange={(e) => {
                setSelectedProvider(e.target.value);
                setPage(1);
                setNotificationsPage(1);
                setActiveView('profiles');
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">All Providers</option>
              {providers.map((provider) => (
                <option key={provider} value={provider}>
                  {provider}
                </option>
              ))}
            </select>
          </div>

          {/* Conditional filters based on provider */}
          {isLeapsTrader ? (
            /* LEAPS Trader View Toggle */
            <div className="flex-1 min-w-[150px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">View</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setActiveView('profiles')}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeView === 'profiles'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  Alert Profiles
                </button>
                <button
                  onClick={() => setActiveView('notifications')}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeView === 'notifications'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  Triggered ({notificationsTotal})
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* Status Filter */}
              <div className="flex-1 min-w-[150px]">
                <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                <select
                  value={selectedStatus}
                  onChange={(e) => {
                    setSelectedStatus(e.target.value);
                    setPage(1);
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="">All Statuses</option>
                  <option value="active">Active</option>
                  <option value="triggered">Triggered</option>
                  <option value="expired">Expired</option>
                  <option value="dismissed">Dismissed</option>
                </select>
              </div>

              {/* Event Type Filter */}
              <div className="flex-1 min-w-[150px]">
                <label className="block text-sm font-medium text-gray-700 mb-1">Event Type</label>
                <select
                  value={selectedEventType}
                  onChange={(e) => {
                    setSelectedEventType(e.target.value);
                    setPage(1);
                  }}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="">All Types</option>
                  <option value="new_setup">New Setup</option>
                  <option value="trigger">Trigger</option>
                </select>
              </div>
            </>
          )}

          {/* Action Buttons */}
          <div className="flex gap-2 items-end">
            {!isLeapsTrader && (
              <>
                <button
                  onClick={resetFilters}
                  className="px-4 py-2 text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                >
                  Reset
                </button>
                <button
                  onClick={fetchAlerts}
                  className="px-4 py-2 text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
                >
                  Refresh
                </button>
                {alerts.length > 0 && (
                  <button
                    onClick={handleClearAll}
                    className="px-4 py-2 text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors"
                  >
                    Clear All
                  </button>
                )}
              </>
            )}
            {isLeapsTrader && activeView === 'notifications' && notifications.length > 0 && (
              <button
                onClick={handleClearNotifications}
                className="px-4 py-2 text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors"
              >
                Clear All
              </button>
            )}
          </div>
        </div>
      </Card>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-start">
            <div className="text-red-600 mr-3 text-xl">⚠️</div>
            <div>
              <h3 className="font-semibold text-red-900 mb-1">Error</h3>
              <p className="text-red-800">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Alert Builder Modal */}
      {showAlertBuilder && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <AlertBuilder
              existingAlert={editingAlert}
              onAlertCreated={handleAlertCreated}
              onAlertUpdated={handleAlertUpdated}
              onClose={handleCloseBuilder}
            />
          </div>
        </div>
      )}

      {/* LEAPS Trader Content */}
      {isLeapsTrader && (
        <>
          {activeView === 'profiles' ? (
            /* Alert Profiles View */
            <UserAlertsList
              onSelectAlert={onSelectAlert}
              onEditAlert={handleEditAlert}
              refreshTrigger={refreshTrigger}
            />
          ) : (
            /* Notifications View */
            <>
              {loading && (
                <div className="text-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                  <p className="text-gray-600">Loading notifications...</p>
                </div>
              )}

              {!loading && notifications.length === 0 && (
                <Card>
                  <div className="text-center py-12">
                    <div className="text-6xl mb-4">🔔</div>
                    <h3 className="text-xl font-semibold text-gray-800 mb-2">No Triggered Alerts Yet</h3>
                    <p className="text-gray-600">
                      When your alert conditions are met, notifications will appear here.
                    </p>
                  </div>
                </Card>
              )}

              {!loading && notifications.length > 0 && (
                <div className="space-y-4">
                  {notifications.map((notification) => (
                    <Card key={notification.id}>
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-2xl">
                              {ALERT_TYPE_ICONS[notification.alert_type] || '🔔'}
                            </span>
                            <h3 className="font-semibold text-gray-900">
                              {notification.alert_name}
                            </h3>
                            <span className="font-bold text-blue-600">
                              {notification.symbol}
                            </span>
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                              notification.is_read ? NOTIFICATION_STATUS_COLORS.read : NOTIFICATION_STATUS_COLORS.unread
                            }`}>
                              {notification.is_read ? 'Read' : 'Unread'}
                            </span>
                          </div>

                          <p className="text-gray-700 mb-2">{notification.message}</p>

                          <div className="flex items-center gap-4 text-xs text-gray-500">
                            <span>Triggered: {formatDate(notification.triggered_at)}</span>
                            {notification.triggered_value && (
                              <span>Value: {notification.triggered_value}</span>
                            )}
                            {notification.channels_sent?.length > 0 && (
                              <span>Sent via: {notification.channels_sent.join(', ')}</span>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          {!notification.is_read && (
                            <button
                              onClick={() => handleMarkRead(notification.id)}
                              className="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                            >
                              Mark Read
                            </button>
                          )}
                          <button
                            onClick={() => onSelectAlert && onSelectAlert({
                              ...notification,
                              provider: LEAPS_TRADER_PROVIDER,
                              _isNotification: true,
                            })}
                            className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                          >
                            Details
                          </button>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              )}

              {/* Notifications Pagination */}
              {!loading && notificationsTotalPages > 1 && (
                <Card>
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-gray-600">
                      Showing {(notificationsPage - 1) * pageSize + 1} - {Math.min(notificationsPage * pageSize, notificationsTotal)} of {notificationsTotal}
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setNotificationsPage((p) => Math.max(1, p - 1))}
                        disabled={notificationsPage === 1}
                        className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Previous
                      </button>
                      <span className="px-4 py-2 text-gray-600">
                        Page {notificationsPage} of {notificationsTotalPages}
                      </span>
                      <button
                        onClick={() => setNotificationsPage((p) => Math.min(notificationsTotalPages, p + 1))}
                        disabled={notificationsPage === notificationsTotalPages}
                        className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                </Card>
              )}
            </>
          )}
        </>
      )}

      {/* Webhook Alerts Content (when not LEAPS Trader) */}
      {!isLeapsTrader && (
        <>
          {/* Loading State */}
          {loading && (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading alerts...</p>
            </div>
          )}

          {/* Empty State */}
          {!loading && alerts.length === 0 && (
            <Card>
              <div className="text-center py-12">
                <div className="text-6xl mb-4">📡</div>
                <h3 className="text-xl font-semibold text-gray-800 mb-2">No Alerts Yet</h3>
                <p className="text-gray-600 mb-4">
                  Configure your webhook endpoints to start receiving trading signals.
                </p>
                <div className="bg-gray-50 rounded-lg p-4 max-w-lg mx-auto text-left">
                  <h4 className="font-medium text-gray-800 mb-2">Webhook URL:</h4>
                  <code className="block bg-gray-800 text-green-400 p-3 rounded text-sm break-all">
                    POST http://localhost:8000/api/v1/webhooks/receive/&#123;provider&#125;
                  </code>
                  <p className="text-sm text-gray-500 mt-2">
                    Replace &#123;provider&#125; with your signal provider name (e.g., "tradingbot")
                  </p>
                </div>
              </div>
            </Card>
          )}

          {/* Alerts List */}
          {!loading && alerts.length > 0 && (
            <div className="space-y-4">
              {alerts.map((alert) => (
                <AlertCard
                  key={alert.id}
                  alert={alert}
                  onStatusUpdate={handleStatusUpdate}
                  onDelete={handleDelete}
                  onViewDetails={onSelectAlert}
                />
              ))}
            </div>
          )}

          {/* Pagination */}
          {!loading && totalPages > 1 && (
            <Card>
              <div className="flex items-center justify-between">
                <div className="text-sm text-gray-600">
                  Showing {(page - 1) * pageSize + 1} - {Math.min(page * pageSize, total)} of {total} alerts
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <span className="px-4 py-2 text-gray-600">
                    Page {page} of {totalPages}
                  </span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
