/**
 * Portfolio API client
 * Handles broker connections and portfolio data
 */
import axios from 'axios';
import { API_BASE_URL } from './axios';
const API_PREFIX = `${API_BASE_URL}/api/v1/portfolio`;

export const portfolioAPI = {
  // =============================================================================
  // Broker Status & Connections
  // =============================================================================

  /**
   * Get status of all supported brokers
   */
  async getBrokersStatus() {
    const response = await axios.get(`${API_PREFIX}/brokers/status`);
    return response.data;
  },

  /**
   * Get all broker connections
   */
  async getConnections() {
    const response = await axios.get(`${API_PREFIX}/connections`);
    return response.data;
  },

  /**
   * Connect to a broker account
   */
  async connectBroker(brokerType, username, password, mfaCode = null, deviceToken = null, accountName = null) {
    const response = await axios.post(`${API_PREFIX}/connections`, {
      broker_type: brokerType,
      username,
      password,
      mfa_code: mfaCode,
      device_token: deviceToken,
      account_name: accountName,
    });
    return response.data;
  },

  /**
   * Submit MFA code for pending connection (TOTP flow)
   */
  async submitMFA(connectionId, mfaCode) {
    const response = await axios.post(`${API_PREFIX}/connections/${connectionId}/mfa`, {
      connection_id: connectionId,
      mfa_code: mfaCode,
    });
    return response.data;
  },

  /**
   * Submit SMS/email verification code (Robinhood verification_workflow flow)
   */
  async submitVerification(connectionId, verificationCode, verificationData) {
    const response = await axios.post(`${API_PREFIX}/connections/${connectionId}/verify`, {
      verification_code: verificationCode,
      challenge_id: verificationData.challenge_id,
      workflow_id: verificationData.workflow_id,
      machine_id: verificationData.machine_id,
      device_token: verificationData.device_token,
    });
    return response.data;
  },

  /**
   * Disconnect a broker account
   */
  async disconnectBroker(connectionId) {
    const response = await axios.delete(`${API_PREFIX}/connections/${connectionId}`);
    return response.data;
  },

  /**
   * Manually sync positions for a connection
   */
  async syncConnection(connectionId) {
    const response = await axios.post(`${API_PREFIX}/connections/${connectionId}/sync`);
    return response.data;
  },

  /**
   * Refresh position prices using Alpaca live feed (no Robinhood call)
   */
  async refreshPrices() {
    const response = await axios.post(`${API_PREFIX}/positions/refresh-prices`);
    return response.data;
  },

  // =============================================================================
  // Portfolio Data
  // =============================================================================

  /**
   * Get aggregated portfolio summary
   */
  async getSummary() {
    const response = await axios.get(`${API_PREFIX}/summary`);
    return response.data;
  },

  /**
   * Get all positions
   */
  async getPositions(brokerId = null, assetType = null) {
    const params = {};
    if (brokerId) params.broker_id = brokerId;
    if (assetType) params.asset_type = assetType;

    const response = await axios.get(`${API_PREFIX}/positions`, { params });
    return response.data;
  },

  /**
   * Get position by symbol
   */
  async getPositionBySymbol(symbol) {
    const response = await axios.get(`${API_PREFIX}/positions/${symbol}`);
    return response.data;
  },

  /**
   * Get portfolio value history
   */
  async getHistory(span = 'month', brokerId = null) {
    const params = { span };
    if (brokerId) params.broker_id = brokerId;

    const response = await axios.get(`${API_PREFIX}/history`, { params });
    return response.data;
  },

  /**
   * Get dividend history
   */
  async getDividends() {
    const response = await axios.get(`${API_PREFIX}/dividends`);
    return response.data;
  },

  /**
   * Get recent orders
   */
  async getRecentOrders(limit = 50) {
    const response = await axios.get(`${API_PREFIX}/orders/recent`, {
      params: { limit },
    });
    return response.data;
  },
};

export default portfolioAPI;
