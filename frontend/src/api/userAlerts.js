/**
 * User Alerts API client
 * Create and manage dynamic, condition-based alerts
 */
import apiClient from './axios';

const API_PREFIX = '/api/v1/alerts';

/**
 * Get available alert types and configuration options
 */
export const getAlertTypes = async () => {
  const response = await apiClient.get(`${API_PREFIX}/types`);
  return response.data;
};

/**
 * Create a new user alert
 */
export const createAlert = async (alertData) => {
  const response = await apiClient.post(`${API_PREFIX}/`, alertData);
  return response.data;
};

/**
 * List user alerts with optional filters
 */
export const listAlerts = async (params = {}) => {
  const response = await apiClient.get(`${API_PREFIX}/`, { params });
  return response.data;
};

/**
 * Get a single alert by ID
 */
export const getAlert = async (alertId) => {
  const response = await apiClient.get(`${API_PREFIX}/${alertId}`);
  return response.data;
};

/**
 * Update an existing alert
 */
export const updateAlert = async (alertId, updates) => {
  const response = await apiClient.patch(`${API_PREFIX}/${alertId}`, updates);
  return response.data;
};

/**
 * Delete an alert
 */
export const deleteAlert = async (alertId) => {
  const response = await apiClient.delete(`${API_PREFIX}/${alertId}`);
  return response.data;
};

/**
 * Toggle an alert's active status
 */
export const toggleAlert = async (alertId) => {
  const response = await apiClient.post(`${API_PREFIX}/${alertId}/toggle`);
  return response.data;
};

/**
 * Manually check an alert's conditions
 */
export const checkAlertNow = async (alertId) => {
  const response = await apiClient.post(`${API_PREFIX}/${alertId}/check`);
  return response.data;
};

/**
 * Check all active alerts
 */
export const checkAllAlerts = async () => {
  const response = await apiClient.post(`${API_PREFIX}/check-all`);
  return response.data;
};

/**
 * List triggered notifications
 */
export const listNotifications = async (params = {}) => {
  const response = await apiClient.get(`${API_PREFIX}/notifications/`, { params });
  return response.data;
};

/**
 * Mark a notification as read
 */
export const markNotificationRead = async (notificationId) => {
  const response = await apiClient.post(`${API_PREFIX}/notifications/${notificationId}/read`);
  return response.data;
};

/**
 * Mark all notifications as read
 */
export const markAllNotificationsRead = async () => {
  const response = await apiClient.post(`${API_PREFIX}/notifications/mark-all-read`);
  return response.data;
};

/**
 * Clear notifications
 */
export const clearNotifications = async (params = {}) => {
  const response = await apiClient.delete(`${API_PREFIX}/notifications/clear`, { params });
  return response.data;
};

export default {
  getAlertTypes,
  createAlert,
  listAlerts,
  getAlert,
  updateAlert,
  deleteAlert,
  toggleAlert,
  checkAlertNow,
  checkAllAlerts,
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  clearNotifications,
};
