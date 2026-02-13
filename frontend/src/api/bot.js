/**
 * Trading Bot API client
 * Configuration, control, trade journal, and performance analytics
 */
import apiClient from './axios';

const BOT_PREFIX = '/api/v1/trading/bot';

// =============================================================================
// Configuration
// =============================================================================

export const getConfig = async () => {
  const response = await apiClient.get(`${BOT_PREFIX}/config`);
  return response.data;
};

export const updateConfig = async (updates) => {
  const response = await apiClient.put(`${BOT_PREFIX}/config`, updates);
  return response.data;
};

// =============================================================================
// Bot Control
// =============================================================================

export const startBot = async () => {
  const response = await apiClient.post(`${BOT_PREFIX}/start`);
  return response.data;
};

export const stopBot = async () => {
  const response = await apiClient.post(`${BOT_PREFIX}/stop`);
  return response.data;
};

export const pauseBot = async () => {
  const response = await apiClient.post(`${BOT_PREFIX}/pause`);
  return response.data;
};

export const resumeBot = async () => {
  const response = await apiClient.post(`${BOT_PREFIX}/resume`);
  return response.data;
};

export const emergencyStop = async (closePositions = true) => {
  const response = await apiClient.post(`${BOT_PREFIX}/emergency-stop`, {
    close_positions: closePositions,
  });
  return response.data;
};

// =============================================================================
// Status
// =============================================================================

export const getStatus = async () => {
  const response = await apiClient.get(`${BOT_PREFIX}/status`);
  return response.data;
};

// =============================================================================
// Signal Approval (Semi-Auto)
// =============================================================================

export const approveSignal = async (signalId) => {
  const response = await apiClient.post(`${BOT_PREFIX}/approve/${signalId}`);
  return response.data;
};

export const rejectSignal = async (signalId) => {
  const response = await apiClient.post(`${BOT_PREFIX}/reject/${signalId}`);
  return response.data;
};

export const getPendingApprovals = async () => {
  const response = await apiClient.get(`${BOT_PREFIX}/pending-approvals`);
  return response.data;
};

// =============================================================================
// Manual Signal Execution (Trade button in UI)
// =============================================================================

export const previewSignal = async (signalId) => {
  const response = await apiClient.post(`${BOT_PREFIX}/preview-signal/${signalId}`);
  return response.data;
};

export const executeSignal = async (signalId) => {
  const response = await apiClient.post(`${BOT_PREFIX}/execute-signal/${signalId}`);
  return response.data;
};

// =============================================================================
// Trade Journal
// =============================================================================

export const listTrades = async (params = {}) => {
  const response = await apiClient.get(`${BOT_PREFIX}/trades`, { params });
  return response.data;
};

export const getActiveTrades = async () => {
  const response = await apiClient.get(`${BOT_PREFIX}/trades/active`);
  return response.data;
};

export const getTrade = async (tradeId) => {
  const response = await apiClient.get(`${BOT_PREFIX}/trades/${tradeId}`);
  return response.data;
};

// =============================================================================
// Performance
// =============================================================================

export const getPerformance = async (params = {}) => {
  const response = await apiClient.get(`${BOT_PREFIX}/performance`, { params });
  return response.data;
};

export const getDailyPerformance = async (params = {}) => {
  const response = await apiClient.get(`${BOT_PREFIX}/performance/daily`, { params });
  return response.data;
};

export const getTodayPerformance = async () => {
  const response = await apiClient.get(`${BOT_PREFIX}/performance/today`);
  return response.data;
};

export const getExitReasonBreakdown = async (params = {}) => {
  const response = await apiClient.get(`${BOT_PREFIX}/performance/exit-reasons`, { params });
  return response.data;
};

const botAPI = {
  getConfig,
  updateConfig,
  startBot,
  stopBot,
  pauseBot,
  resumeBot,
  emergencyStop,
  getStatus,
  approveSignal,
  rejectSignal,
  getPendingApprovals,
  previewSignal,
  executeSignal,
  listTrades,
  getActiveTrades,
  getTrade,
  getPerformance,
  getDailyPerformance,
  getTodayPerformance,
  getExitReasonBreakdown,
};

export default botAPI;
