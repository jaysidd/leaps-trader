/**
 * Backtesting API client
 * Run backtests, poll results, list history
 */
import apiClient from './axios';

const PREFIX = '/api/v1/backtesting';

// =============================================================================
// Run & Results
// =============================================================================

export const runBacktest = async (config) => {
  const response = await apiClient.post(`${PREFIX}/run`, config);
  return response.data;
};

export const getResults = async (id) => {
  const response = await apiClient.get(`${PREFIX}/results/${id}`);
  return response.data;
};

// =============================================================================
// List & Delete
// =============================================================================

export const listBacktests = async (params = {}) => {
  const response = await apiClient.get(`${PREFIX}/list`, { params });
  return response.data;
};

export const deleteBacktest = async (id) => {
  const response = await apiClient.delete(`${PREFIX}/${id}`);
  return response.data;
};

const backtestAPI = {
  runBacktest,
  getResults,
  listBacktests,
  deleteBacktest,
};

export default backtestAPI;
