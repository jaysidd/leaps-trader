/**
 * Settings page with tabs for different configuration categories
 */
import { useState, useEffect } from 'react';
import { settingsAPI } from '../api/settings';
import tradingAPI from '../api/trading';
import { API_BASE_URL } from '../api/axios';
import AutoTradingSettings from '../components/settings/AutoTradingSettings';

// Tab configuration
const TABS = [
  { id: 'api-keys', label: 'API Keys', icon: '🔑', description: 'Configure API integrations' },
  { id: 'trading', label: 'Trading', icon: '📈', description: 'Alpaca trading configuration' },
  { id: 'auto-trading', label: 'Auto Trading', icon: '🤖', description: 'Trading bot configuration' },
  { id: 'screening', label: 'Screening Defaults', icon: '🎯', description: 'Default screening parameters' },
  { id: 'performance', label: 'Performance', icon: '⚡', description: 'Rate limits and caching' },
  { id: 'features', label: 'Features', icon: '🎛️', description: 'Enable/disable features' },
  { id: 'automation', label: 'Automation', icon: '🔄', description: 'Scheduled scans & auto-processing' },
  { id: 'system', label: 'System', icon: '🖥️', description: 'Server management' },
];

export default function Settings() {
  const [activeTab, setActiveTab] = useState('api-keys');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const [settings, setSettings] = useState({});
  const [apiKeys, setApiKeys] = useState([]);
  const [pendingChanges, setPendingChanges] = useState({});

  // Load settings on mount
  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const summary = await settingsAPI.getSettingsSummary();
      setSettings(summary.settings || {});
      setApiKeys(summary.api_keys || []);
    } catch (err) {
      setError('Failed to load settings: ' + (err.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const handleSettingChange = (key, value) => {
    setPendingChanges(prev => ({ ...prev, [key]: value }));
  };

  const saveSettings = async () => {
    if (Object.keys(pendingChanges).length === 0) return;

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      await settingsAPI.updateSettingsBatch(pendingChanges);
      setSuccess('Settings saved successfully!');
      setPendingChanges({});
      await loadSettings(); // Reload to get updated values
    } catch (err) {
      setError('Failed to save settings: ' + (err.message || 'Unknown error'));
    } finally {
      setSaving(false);
    }
  };

  const handleApiKeyUpdate = async (serviceName, apiKey) => {
    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await settingsAPI.updateApiKey(serviceName, apiKey);
      if (result.success) {
        setSuccess(result.message || 'API key updated successfully!');
        await loadSettings();
      } else {
        setError(result.error || 'Failed to update API key');
      }
    } catch (err) {
      setError('Failed to update API key: ' + (err.message || 'Unknown error'));
    } finally {
      setSaving(false);
    }
  };

  const getSettingValue = (key) => {
    if (key in pendingChanges) return pendingChanges[key];
    // Parse the nested key
    const parts = key.split('.');
    let value = settings;
    for (const part of parts) {
      if (value && typeof value === 'object') {
        if (part in value) {
          value = value[part];
        } else if (value[key]) {
          return value[key].value;
        } else {
          return undefined;
        }
      }
    }
    return value?.value !== undefined ? value.value : value;
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 py-8 transition-colors">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Settings</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">Configure your LEAPS Trader application</p>
        </div>

        {/* Alerts */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400">
            {error}
            <button onClick={() => setError(null)} className="ml-2 text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300">
              Dismiss
            </button>
          </div>
        )}
        {success && (
          <div className="mb-6 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg text-green-700 dark:text-green-400">
            {success}
            <button onClick={() => setSuccess(null)} className="ml-2 text-green-500 hover:text-green-700 dark:text-green-400 dark:hover:text-green-300">
              Dismiss
            </button>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="mb-6">
          <div className="border-b border-gray-200 dark:border-gray-700">
            <nav className="flex space-x-8">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                    activeTab === tab.id
                      ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300'
                  }`}
                >
                  <span className="text-lg mr-2">{tab.icon}</span>
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 border border-transparent dark:border-gray-700">
            {/* API Keys Tab */}
            {activeTab === 'api-keys' && (
              <ApiKeysTab
                apiKeys={apiKeys}
                onUpdate={handleApiKeyUpdate}
                saving={saving}
              />
            )}

            {/* Trading Tab */}
            {activeTab === 'trading' && (
              <TradingTab />
            )}

            {/* Auto Trading Tab */}
            {activeTab === 'auto-trading' && (
              <AutoTradingSettings />
            )}

            {/* Screening Defaults Tab */}
            {activeTab === 'screening' && (
              <ScreeningTab
                settings={settings.screening || {}}
                pendingChanges={pendingChanges}
                onChange={handleSettingChange}
                getSettingValue={getSettingValue}
              />
            )}

            {/* Performance Tab */}
            {activeTab === 'performance' && (
              <PerformanceTab
                rateLimits={settings.rate_limit || {}}
                cache={settings.cache || {}}
                pendingChanges={pendingChanges}
                onChange={handleSettingChange}
                getSettingValue={getSettingValue}
              />
            )}

            {/* Features Tab */}
            {activeTab === 'features' && (
              <FeaturesTab
                features={settings.feature || {}}
                pendingChanges={pendingChanges}
                onChange={handleSettingChange}
                getSettingValue={getSettingValue}
              />
            )}

            {/* Automation Tab */}
            {activeTab === 'automation' && (
              <AutomationTab
                settings={settings.automation || {}}
                pendingChanges={pendingChanges}
                onChange={handleSettingChange}
                getSettingValue={getSettingValue}
              />
            )}

            {/* System Tab */}
            {activeTab === 'system' && (
              <SystemTab />
            )}

            {/* Save Button */}
            {activeTab !== 'api-keys' && Object.keys(pendingChanges).length > 0 && (
              <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700 flex justify-end">
                <button
                  onClick={() => setPendingChanges({})}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg mr-3 hover:bg-gray-200 dark:hover:bg-gray-600"
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  onClick={saveSettings}
                  disabled={saving}
                  className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// API Keys Tab Component
function ApiKeysTab({ apiKeys, onUpdate, saving }) {
  const [editingKey, setEditingKey] = useState(null);
  const [newKeyValue, setNewKeyValue] = useState('');

  const handleSave = (serviceName) => {
    onUpdate(serviceName, newKeyValue);
    setEditingKey(null);
    setNewKeyValue('');
  };

  return (
    <div>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">API Key Configuration</h2>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        Configure API keys for external services. Keys are securely stored on the server
        and never exposed to the browser.
      </p>

      <div className="space-y-4">
        {apiKeys.map((api) => (
          <div key={api.service_name} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-3">
                  <h3 className="font-semibold text-gray-900 dark:text-white">{api.display_name}</h3>
                  {api.is_configured ? (
                    <span className="px-2 py-1 text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full">
                      Configured
                    </span>
                  ) : (
                    <span className="px-2 py-1 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded-full">
                      Not Configured
                    </span>
                  )}
                  {api.always_available && (
                    <span className="px-2 py-1 text-xs font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 rounded-full">
                      No Key Required
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{api.description}</p>

                {api.is_configured && api.usage_count > 0 && (
                  <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    Used {api.usage_count} times
                    {api.last_used && ` | Last used: ${new Date(api.last_used).toLocaleDateString()}`}
                    {api.error_count > 0 && (
                      <span className="text-red-500 dark:text-red-400"> | {api.error_count} errors</span>
                    )}
                  </div>
                )}
              </div>

              {!api.always_available && (
                <div className="ml-4">
                  {editingKey === api.service_name ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="password"
                        value={newKeyValue}
                        onChange={(e) => setNewKeyValue(e.target.value)}
                        placeholder="Enter API key"
                        className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm w-64 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                        autoFocus
                      />
                      <button
                        onClick={() => handleSave(api.service_name)}
                        disabled={saving || !newKeyValue}
                        className="px-3 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700 disabled:opacity-50"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => {
                          setEditingKey(null);
                          setNewKeyValue('');
                        }}
                        className="px-3 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm hover:bg-gray-200 dark:hover:bg-gray-600"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setEditingKey(api.service_name)}
                      className="px-4 py-2 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 rounded-lg text-sm hover:bg-blue-200 dark:hover:bg-blue-900/50"
                    >
                      {api.is_configured ? 'Update Key' : 'Add Key'}
                    </button>
                  )}
                </div>
              )}
            </div>

            {api.env_key && (
              <div className="mt-3 text-xs text-gray-400 dark:text-gray-500">
                Environment variable: <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">{api.env_key}</code>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-6 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
        <p className="text-sm text-yellow-800 dark:text-yellow-300">
          <strong>Note:</strong> After updating API keys, you may need to restart the server
          for changes to take effect. Use the "Restart Server" button in the System tab.
        </p>
      </div>
    </div>
  );
}

// Screening Defaults Tab Component
function ScreeningTab({ settings, pendingChanges, onChange, getSettingValue }) {
  const formatNumber = (num) => {
    if (num >= 1_000_000_000) return `$${(num / 1_000_000_000).toFixed(1)}B`;
    if (num >= 1_000_000) return `$${(num / 1_000_000).toFixed(0)}M`;
    return num;
  };

  return (
    <div>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">Screening Defaults</h2>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        Configure default values for stock screening. These can be overridden per scan.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Market Cap Range */}
        <div className="space-y-4">
          <h3 className="font-medium text-gray-800 dark:text-gray-200">Market Cap Range</h3>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
              Minimum: {formatNumber(getSettingValue('screening.market_cap_min') || 1000000000)}
            </label>
            <input
              type="range"
              min="100000000"
              max="50000000000"
              step="100000000"
              value={getSettingValue('screening.market_cap_min') || 1000000000}
              onChange={(e) => onChange('screening.market_cap_min', parseInt(e.target.value))}
              className="w-full accent-blue-600"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
              Maximum: {formatNumber(getSettingValue('screening.market_cap_max') || 100000000000)}
            </label>
            <input
              type="range"
              min="1000000000"
              max="500000000000"
              step="1000000000"
              value={getSettingValue('screening.market_cap_max') || 100000000000}
              onChange={(e) => onChange('screening.market_cap_max', parseInt(e.target.value))}
              className="w-full accent-blue-600"
            />
          </div>
        </div>

        {/* Growth Requirements */}
        <div className="space-y-4">
          <h3 className="font-medium text-gray-800 dark:text-gray-200">Growth Requirements</h3>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
              Revenue Growth Min: {getSettingValue('screening.revenue_growth_min') || 10}%
            </label>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={getSettingValue('screening.revenue_growth_min') || 10}
              onChange={(e) => onChange('screening.revenue_growth_min', parseInt(e.target.value))}
              className="w-full accent-blue-600"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
              Earnings Growth Min: {getSettingValue('screening.earnings_growth_min') || 5}%
            </label>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={getSettingValue('screening.earnings_growth_min') || 5}
              onChange={(e) => onChange('screening.earnings_growth_min', parseInt(e.target.value))}
              className="w-full accent-blue-600"
            />
          </div>
        </div>

        {/* Technical Indicators */}
        <div className="space-y-4">
          <h3 className="font-medium text-gray-800 dark:text-gray-200">RSI Range</h3>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
              Minimum RSI: {getSettingValue('screening.rsi_min') || 25}
            </label>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={getSettingValue('screening.rsi_min') || 25}
              onChange={(e) => onChange('screening.rsi_min', parseInt(e.target.value))}
              className="w-full accent-blue-600"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
              Maximum RSI: {getSettingValue('screening.rsi_max') || 75}
            </label>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={getSettingValue('screening.rsi_max') || 75}
              onChange={(e) => onChange('screening.rsi_max', parseInt(e.target.value))}
              className="w-full accent-blue-600"
            />
          </div>
        </div>

        {/* Options Criteria */}
        <div className="space-y-4">
          <h3 className="font-medium text-gray-800 dark:text-gray-200">Options Criteria</h3>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
              Max IV: {getSettingValue('screening.iv_max') || 100}%
            </label>
            <input
              type="range"
              min="20"
              max="200"
              step="5"
              value={getSettingValue('screening.iv_max') || 100}
              onChange={(e) => onChange('screening.iv_max', parseInt(e.target.value))}
              className="w-full accent-blue-600"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
              Min DTE: {getSettingValue('screening.dte_min') || 365} days
            </label>
            <input
              type="range"
              min="180"
              max="730"
              step="30"
              value={getSettingValue('screening.dte_min') || 365}
              onChange={(e) => onChange('screening.dte_min', parseInt(e.target.value))}
              className="w-full accent-blue-600"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// Performance Tab Component
function PerformanceTab({ rateLimits, cache, pendingChanges, onChange, getSettingValue }) {
  return (
    <div>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">Performance Settings</h2>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        Configure rate limits and caching to optimize performance and avoid API throttling.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Rate Limits */}
        <div>
          <h3 className="font-medium text-gray-800 dark:text-gray-200 mb-4">Rate Limits</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                Yahoo Finance requests/second: {getSettingValue('rate_limit.yahoo_requests_per_second') || 2}
              </label>
              <input
                type="range"
                min="1"
                max="5"
                step="1"
                value={getSettingValue('rate_limit.yahoo_requests_per_second') || 2}
                onChange={(e) => onChange('rate_limit.yahoo_requests_per_second', parseInt(e.target.value))}
                className="w-full accent-blue-600"
              />
              <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                Higher values = faster scans, but may trigger rate limiting
              </p>
            </div>
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                Alpha Vantage requests/minute: {getSettingValue('rate_limit.alpha_vantage_requests_per_minute') || 5}
              </label>
              <input
                type="range"
                min="1"
                max="10"
                step="1"
                value={getSettingValue('rate_limit.alpha_vantage_requests_per_minute') || 5}
                onChange={(e) => onChange('rate_limit.alpha_vantage_requests_per_minute', parseInt(e.target.value))}
                className="w-full accent-blue-600"
              />
            </div>
          </div>
        </div>

        {/* Cache TTLs */}
        <div>
          <h3 className="font-medium text-gray-800 dark:text-gray-200 mb-4">Cache Duration</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                Quote cache (market hours): {getSettingValue('cache.quote_market_hours_ttl') || 60}s
              </label>
              <input
                type="range"
                min="30"
                max="300"
                step="30"
                value={getSettingValue('cache.quote_market_hours_ttl') || 60}
                onChange={(e) => onChange('cache.quote_market_hours_ttl', parseInt(e.target.value))}
                className="w-full accent-blue-600"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                Fundamentals cache: {Math.round((getSettingValue('cache.fundamentals_ttl') || 86400) / 3600)}h
              </label>
              <input
                type="range"
                min="3600"
                max="172800"
                step="3600"
                value={getSettingValue('cache.fundamentals_ttl') || 86400}
                onChange={(e) => onChange('cache.fundamentals_ttl', parseInt(e.target.value))}
                className="w-full accent-blue-600"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                Technical indicators cache: {Math.round((getSettingValue('cache.technical_indicators_ttl') || 3600) / 60)}min
              </label>
              <input
                type="range"
                min="300"
                max="7200"
                step="300"
                value={getSettingValue('cache.technical_indicators_ttl') || 3600}
                onChange={(e) => onChange('cache.technical_indicators_ttl', parseInt(e.target.value))}
                className="w-full accent-blue-600"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Trading Tab Component
function TradingTab() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [account, setAccount] = useState(null);
  const [tradingMode, setTradingMode] = useState(null);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    loadTradingData();
  }, []);

  const loadTradingData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [accountData, modeData] = await Promise.all([
        tradingAPI.getAccount(),
        tradingAPI.getTradingMode(),
      ]);
      setAccount(accountData);
      setTradingMode(modeData);
    } catch (err) {
      setError('Failed to load trading data: ' + (err.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  const handleModeChange = async (paperMode) => {
    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await tradingAPI.setTradingMode(paperMode);
      setTradingMode(result);
      setSuccess(`Switched to ${paperMode ? 'Paper' : 'Live'} trading mode`);
      // Reload account for updated data
      const accountData = await tradingAPI.getAccount();
      setAccount(accountData);
    } catch (err) {
      setError('Failed to change trading mode: ' + (err.message || 'Unknown error'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const isPaperMode = tradingMode?.paper_mode !== false;

  return (
    <div>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">Trading Configuration</h2>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        Configure Alpaca trading settings. Switch between paper and live trading modes.
      </p>

      {/* Alerts */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-6 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg text-green-700 dark:text-green-400">
          {success}
        </div>
      )}

      {/* Trading Mode Toggle */}
      <div className="mb-8">
        <h3 className="font-medium text-gray-800 dark:text-gray-200 mb-4">Trading Mode</h3>
        <div className="grid grid-cols-2 gap-4 max-w-md">
          <button
            onClick={() => handleModeChange(true)}
            disabled={saving || isPaperMode}
            className={`p-4 rounded-lg border-2 transition-all ${
              isPaperMode
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30'
                : 'border-gray-200 dark:border-gray-600 hover:border-blue-300'
            } ${saving ? 'opacity-50' : ''}`}
          >
            <div className="text-2xl mb-2">📝</div>
            <div className="font-semibold text-gray-900 dark:text-white">Paper Trading</div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">Simulated trades</div>
            {isPaperMode && (
              <div className="mt-2 text-xs text-blue-600 dark:text-blue-400 font-medium">Active</div>
            )}
          </button>
          <button
            onClick={() => handleModeChange(false)}
            disabled={saving || !isPaperMode}
            className={`p-4 rounded-lg border-2 transition-all ${
              !isPaperMode
                ? 'border-red-500 bg-red-50 dark:bg-red-900/30'
                : 'border-gray-200 dark:border-gray-600 hover:border-red-300'
            } ${saving ? 'opacity-50' : ''}`}
          >
            <div className="text-2xl mb-2">💰</div>
            <div className="font-semibold text-gray-900 dark:text-white">Live Trading</div>
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">Real money</div>
            {!isPaperMode && (
              <div className="mt-2 text-xs text-red-600 dark:text-red-400 font-medium">Active</div>
            )}
          </button>
        </div>

        {!isPaperMode && (
          <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <div className="flex items-center gap-2 text-red-800 dark:text-red-300">
              <span className="text-xl">⚠️</span>
              <span className="font-bold">Live Trading Mode Active</span>
            </div>
            <p className="text-red-700 dark:text-red-400 text-sm mt-1">
              Orders will execute with real money. Make sure you understand the risks.
            </p>
          </div>
        )}
      </div>

      {/* Account Information */}
      {account && (
        <div className="mb-8">
          <h3 className="font-medium text-gray-800 dark:text-gray-200 mb-4">Account Information</h3>
          <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <div>
                <div className="text-sm text-gray-500 dark:text-gray-400">Account Status</div>
                <div className={`font-semibold ${
                  account.status === 'ACTIVE' ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'
                }`}>
                  {account.status || 'Unknown'}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500 dark:text-gray-400">Equity</div>
                <div className="font-semibold text-gray-900 dark:text-white">
                  ${parseFloat(account.equity || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500 dark:text-gray-400">Buying Power</div>
                <div className="font-semibold text-blue-600 dark:text-blue-400">
                  ${parseFloat(account.buying_power || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500 dark:text-gray-400">Cash</div>
                <div className="font-semibold text-gray-900 dark:text-white">
                  ${parseFloat(account.cash || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500 dark:text-gray-400">Portfolio Value</div>
                <div className="font-semibold text-gray-900 dark:text-white">
                  ${parseFloat(account.portfolio_value || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500 dark:text-gray-400">Day Trade Count</div>
                <div className={`font-semibold ${
                  (account.daytrade_count || 0) >= 3 ? 'text-yellow-600 dark:text-yellow-400' : 'text-gray-900 dark:text-white'
                }`}>
                  {account.daytrade_count || 0}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500 dark:text-gray-400">Pattern Day Trader</div>
                <div className="font-semibold text-gray-900 dark:text-white">
                  {account.pattern_day_trader ? 'Yes' : 'No'}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500 dark:text-gray-400">Trading Blocked</div>
                <div className={`font-semibold ${
                  account.trading_blocked ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'
                }`}>
                  {account.trading_blocked ? 'Yes' : 'No'}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* API Status */}
      <div>
        <h3 className="font-medium text-gray-800 dark:text-gray-200 mb-4">API Status</h3>
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`w-3 h-3 rounded-full ${
                account ? 'bg-green-500' : 'bg-red-500'
              }`} />
              <span className="font-medium text-gray-900 dark:text-white">Alpaca API</span>
            </div>
            <span className={`text-sm ${
              account ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
            }`}>
              {account ? 'Connected' : 'Not Connected'}
            </span>
          </div>
          {!account && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
              Configure your Alpaca API keys in the API Keys tab to enable trading.
            </p>
          )}
        </div>
      </div>

      <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
        <p className="text-sm text-blue-800 dark:text-blue-300">
          <strong>Tip:</strong> Start with Paper Trading to test your strategies without risking real money.
          Paper trading uses simulated funds ($100,000) and mimics real market conditions.
        </p>
      </div>
    </div>
  );
}

// Features Tab Component
function FeaturesTab({ features, pendingChanges, onChange, getSettingValue }) {
  const toggleFeature = (key) => {
    const currentValue = getSettingValue(key);
    onChange(key, !currentValue);
  };

  const featuresList = [
    {
      key: 'feature.enable_ai_analysis',
      name: 'AI Analysis',
      description: 'Enable Claude AI-powered market analysis and insights'
    },
    {
      key: 'feature.enable_sentiment_analysis',
      name: 'Sentiment Analysis',
      description: 'Enable news and social media sentiment scoring'
    },
    {
      key: 'feature.enable_telegram_alerts',
      name: 'Telegram Alerts',
      description: 'Send alert notifications via Telegram bot'
    },
  ];

  return (
    <div>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">Feature Toggles</h2>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        Enable or disable optional features. Some features require API keys to be configured.
      </p>

      <div className="space-y-4">
        {featuresList.map((feature) => (
          <div
            key={feature.key}
            className="flex items-center justify-between p-4 border border-gray-200 dark:border-gray-700 rounded-lg"
          >
            <div>
              <h3 className="font-medium text-gray-900 dark:text-white">{feature.name}</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">{feature.description}</p>
            </div>
            <button
              onClick={() => toggleFeature(feature.key)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                getSettingValue(feature.key) ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  getSettingValue(feature.key) ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
        ))}
      </div>

      {/* UI Preferences */}
      <div className="mt-8">
        <h3 className="font-medium text-gray-800 dark:text-gray-200 mb-4">UI Preferences</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Default Preset</label>
            <select
              value={getSettingValue('ui.default_preset') || 'moderate'}
              onChange={(e) => onChange('ui.default_preset', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="conservative">Conservative</option>
              <option value="moderate">Moderate</option>
              <option value="aggressive">Aggressive</option>
              <option value="iv_crush">IV Crush</option>
              <option value="momentum">Momentum</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Results Per Page</label>
            <select
              value={getSettingValue('ui.results_per_page') || 25}
              onChange={(e) => onChange('ui.results_per_page', parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
            >
              <option value="10">10</option>
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  );
}

// Automation Tab Component
function AutomationTab({ settings, pendingChanges, onChange, getSettingValue }) {
  const autoScanEnabled = getSettingValue('automation.auto_scan_enabled');
  const autoProcess = getSettingValue('automation.auto_scan_auto_process');
  const presetsRaw = getSettingValue('automation.auto_scan_presets');
  const scanMode = getSettingValue('automation.auto_scan_mode') || 'interval';
  const scanInterval = getSettingValue('automation.auto_scan_interval_minutes') || 30;

  // Parse presets JSON safely
  let presets = [];
  try {
    presets = typeof presetsRaw === 'string' ? JSON.parse(presetsRaw) : (presetsRaw || []);
  } catch { presets = []; }

  const [newPreset, setNewPreset] = useState('');

  const addPreset = () => {
    if (newPreset.trim() && !presets.includes(newPreset.trim())) {
      const updated = [...presets, newPreset.trim()];
      onChange('automation.auto_scan_presets', JSON.stringify(updated));
      setNewPreset('');
    }
  };

  const removePreset = (preset) => {
    const updated = presets.filter(p => p !== preset);
    onChange('automation.auto_scan_presets', JSON.stringify(updated));
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-1">Automated Scanning</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Schedule daily scans and auto-process results through the strategy pipeline.
        </p>
      </div>

      {/* Enable toggle */}
      <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
        <div>
          <p className="font-medium text-gray-800 dark:text-gray-200">Enable Auto-Scan</p>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {scanMode === 'interval'
              ? `Scan every ${scanInterval} min during market hours (9:00–4:30 ET)`
              : 'Run configured scan presets daily at 8:30 AM CT'}
          </p>
        </div>
        <button
          onClick={() => onChange('automation.auto_scan_enabled', !autoScanEnabled)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            autoScanEnabled ? 'bg-purple-600' : 'bg-gray-300 dark:bg-gray-600'
          }`}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            autoScanEnabled ? 'translate-x-6' : 'translate-x-1'
          }`} />
        </button>
      </div>

      {/* Scan Mode */}
      <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
        <p className="font-medium text-gray-800 dark:text-gray-200 mb-2">Scan Mode</p>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
          Choose between continuous scanning during market hours or a single daily scan
        </p>
        <div className="flex gap-3 mb-3">
          <button
            onClick={() => onChange('automation.auto_scan_mode', 'interval')}
            className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
              scanMode === 'interval'
                ? 'bg-purple-600 text-white'
                : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700'
            }`}
          >
            🔄 Continuous
          </button>
          <button
            onClick={() => onChange('automation.auto_scan_mode', 'daily_cron')}
            className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
              scanMode === 'daily_cron'
                ? 'bg-purple-600 text-white'
                : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700'
            }`}
          >
            📅 Daily (8:30 CT)
          </button>
        </div>
        {scanMode === 'interval' && (
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">Scan interval</p>
            <div className="flex gap-2">
              {[15, 30, 60].map(mins => (
                <button
                  key={mins}
                  onClick={() => onChange('automation.auto_scan_interval_minutes', mins)}
                  className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    Number(scanInterval) === mins
                      ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 ring-2 ring-purple-500'
                      : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`}
                >
                  {mins} min
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Smart Scan */}
      <div className="flex items-center justify-between p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
        <div>
          <p className="font-medium text-blue-800 dark:text-blue-200">Smart Scan</p>
          <p className="text-sm text-blue-600 dark:text-blue-400">
            Automatically select presets based on market conditions (MRI, Trade Readiness, Fear & Greed).
            When enabled, preset selection is automatic.
          </p>
        </div>
        <button
          onClick={() => onChange('automation.smart_scan_enabled', !getSettingValue('automation.smart_scan_enabled'))}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            getSettingValue('automation.smart_scan_enabled') ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-600'
          }`}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            getSettingValue('automation.smart_scan_enabled') ? 'translate-x-6' : 'translate-x-1'
          }`} />
        </button>
      </div>

      {getSettingValue('automation.smart_scan_enabled') && (
        <div className="p-3 bg-blue-50 dark:bg-blue-900/10 rounded-lg border border-blue-100 dark:border-blue-900/30">
          <p className="text-sm text-blue-700 dark:text-blue-300">
            Presets are automatically selected based on market conditions. Go to the{' '}
            <a href="/autopilot" className="underline font-medium">Autopilot dashboard</a> to see current selections.
          </p>
        </div>
      )}

      {/* Presets */}
      {!getSettingValue('automation.smart_scan_enabled') && (
        <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
          <p className="font-medium text-gray-800 dark:text-gray-200 mb-2">Scan Presets</p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
            Which scan categories to run automatically
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
            {presets.map(preset => (
              <span key={preset} className="inline-flex items-center gap-1 px-3 py-1 bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 rounded-full text-sm">
                {preset}
                <button onClick={() => removePreset(preset)} className="hover:text-red-500">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </span>
            ))}
            {presets.length === 0 && (
              <span className="text-sm text-gray-400">No presets configured</span>
            )}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={newPreset}
              onChange={(e) => setNewPreset(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addPreset()}
              placeholder="Preset name (e.g. iv_crush, momentum)"
              className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200"
            />
            <button
              onClick={addPreset}
              className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-lg"
            >
              Add
            </button>
          </div>
        </div>
      )}

      {/* Auto-process toggle */}
      <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
        <div>
          <p className="font-medium text-gray-800 dark:text-gray-200">Auto-Process Results</p>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Automatically run StrategySelector after scan completes (HIGH confidence stocks auto-queue)
          </p>
        </div>
        <button
          onClick={() => onChange('automation.auto_scan_auto_process', !autoProcess)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            autoProcess ? 'bg-purple-600' : 'bg-gray-300 dark:bg-gray-600'
          }`}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            autoProcess ? 'translate-x-6' : 'translate-x-1'
          }`} />
        </button>
      </div>

      {/* Pipeline info */}
      <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
        <p className="font-medium text-gray-800 dark:text-gray-200 mb-2">Pipeline Flow</p>
        <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <span className="px-2 py-1 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400 rounded">
            {scanMode === 'interval' ? `Every ${scanInterval}min Scan` : '8:30 CT Scan'}
          </span>
          <span>→</span>
          <span className="px-2 py-1 bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-400 rounded">Strategy Select</span>
          <span>→</span>
          <span className="px-2 py-1 bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400 rounded">Signal Engine</span>
          <span>→</span>
          <span className="px-2 py-1 bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-400 rounded">AI Validate</span>
          <span>→</span>
          <span className="px-2 py-1 bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400 rounded">Bot Execute</span>
        </div>
      </div>
    </div>
  );
}

// System Tab Component
function SystemTab() {
  const [connectionStatus, setConnectionStatus] = useState(null);
  const [restartStatus, setRestartStatus] = useState(null);
  const [checking, setChecking] = useState(false);
  const [restarting, setRestarting] = useState(false);

  const API_BASE = API_BASE_URL;

  const testConnection = async () => {
    setChecking(true);
    setConnectionStatus(null);
    try {
      const response = await fetch(`${API_BASE}/health`);
      const data = await response.json();
      setConnectionStatus({ type: 'success', message: `Connected — status: ${data.status}` });
    } catch (err) {
      setConnectionStatus({ type: 'error', message: `Connection failed: ${err.message}` });
    } finally {
      setChecking(false);
    }
  };

  const restartServer = async () => {
    setRestarting(true);
    setRestartStatus({ type: 'info', message: 'Restarting...' });
    try {
      await fetch(`${API_BASE}/restart`, { method: 'POST' });
    } catch {
      // Server will disconnect during restart, this is expected
    }
    setTimeout(async () => {
      try {
        const response = await fetch(`${API_BASE}/health`);
        const data = await response.json();
        setRestartStatus({ type: 'success', message: `Server restarted — status: ${data.status}` });
      } catch {
        setRestartStatus({ type: 'warning', message: 'Still restarting... refresh in a few seconds' });
      }
      setRestarting(false);
    }, 3000);
  };

  const statusBadge = (status) => {
    if (!status) return null;
    const colors = {
      success: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400',
      error: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400',
      info: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400',
      warning: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400',
    };
    return (
      <div className={`mt-3 px-3 py-2 rounded-lg text-sm font-medium ${colors[status.type]}`}>
        {status.message}
      </div>
    );
  };

  return (
    <div>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">System Management</h2>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        Test backend connectivity and manage the server.
      </p>

      {/* Actions */}
      <div className="space-y-4">
        <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-gray-900 dark:text-white">Test Connection</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">Check if the backend API is reachable</p>
            </div>
            <button
              onClick={testConnection}
              disabled={checking}
              className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors"
            >
              {checking ? 'Checking...' : 'Test Connection'}
            </button>
          </div>
          {statusBadge(connectionStatus)}
        </div>

        <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium text-gray-900 dark:text-white">Restart Server</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Restart the backend server (required after API key changes)
              </p>
            </div>
            <button
              onClick={restartServer}
              disabled={restarting}
              className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-50 transition-colors"
            >
              {restarting ? 'Restarting...' : 'Restart Server'}
            </button>
          </div>
          {statusBadge(restartStatus)}
        </div>
      </div>

      <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
        <p className="text-sm text-blue-800 dark:text-blue-300">
          <strong>Tip:</strong> If the backend is not responding, make sure it's running with{' '}
          <code className="bg-blue-100 dark:bg-blue-900/40 px-1 rounded">uvicorn app.main:app --reload</code>{' '}
          from the backend directory.
        </p>
      </div>
    </div>
  );
}
