/**
 * Alert Builder Component
 * Create and edit dynamic, condition-based alerts
 */
import { useState, useEffect } from 'react';
import Card from '../common/Card';
import Button from '../common/Button';
import { getAlertTypes, createAlert, updateAlert } from '../../api/userAlerts';

export default function AlertBuilder({ existingAlert, onAlertCreated, onAlertUpdated, onClose }) {
  const [alertTypes, setAlertTypes] = useState([]);
  const [frequencies, setFrequencies] = useState([]);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Check if editing
  const isEditing = !!existingAlert;

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    symbol: '',
    alert_type: '',
    threshold_value: '',
    sma_period: 200,
    frequency: 'once',
    notification_channels: ['in_app'],
  });

  // Selected alert type config
  const [selectedTypeConfig, setSelectedTypeConfig] = useState(null);

  // Load alert types on mount
  useEffect(() => {
    loadAlertTypes();
  }, []);

  // Populate form when editing
  useEffect(() => {
    if (existingAlert && alertTypes.length > 0) {
      const typeConfig = alertTypes.find(t => t.value === existingAlert.alert_type);
      setSelectedTypeConfig(typeConfig);
      setFormData({
        name: existingAlert.name || '',
        description: existingAlert.description || '',
        symbol: existingAlert.symbol || '',
        alert_type: existingAlert.alert_type || '',
        threshold_value: existingAlert.threshold_value?.toString() || '',
        sma_period: existingAlert.sma_period || 200,
        frequency: existingAlert.frequency || 'once',
        notification_channels: existingAlert.notification_channels || ['in_app'],
      });
    }
  }, [existingAlert, alertTypes]);

  const loadAlertTypes = async () => {
    try {
      setLoading(true);
      const data = await getAlertTypes();
      setAlertTypes(data.alert_types);
      setFrequencies(data.frequencies);
      setChannels(data.notification_channels);
    } catch (err) {
      console.error('Error loading alert types:', err);
      setError('Failed to load alert configuration');
    } finally {
      setLoading(false);
    }
  };

  const handleTypeChange = (e) => {
    const typeValue = e.target.value;
    const typeConfig = alertTypes.find(t => t.value === typeValue);
    setSelectedTypeConfig(typeConfig);
    setFormData(prev => ({
      ...prev,
      alert_type: typeValue,
      threshold_value: isEditing ? prev.threshold_value : (typeConfig?.default_threshold || ''),
    }));
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleChannelToggle = (channel) => {
    setFormData(prev => {
      const channels = prev.notification_channels;
      if (channels.includes(channel)) {
        return { ...prev, notification_channels: channels.filter(c => c !== channel) };
      } else {
        return { ...prev, notification_channels: [...channels, channel] };
      }
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Validation
    if (!formData.name.trim()) {
      setError('Please enter an alert name');
      return;
    }
    if (!formData.symbol.trim()) {
      setError('Please enter a stock symbol');
      return;
    }
    if (!formData.alert_type) {
      setError('Please select an alert type');
      return;
    }
    if (selectedTypeConfig?.requires_threshold && !formData.threshold_value) {
      setError('Please enter a threshold value');
      return;
    }

    try {
      setSaving(true);

      const alertData = {
        name: formData.name.trim(),
        description: formData.description.trim() || null,
        symbol: formData.symbol.trim().toUpperCase(),
        alert_type: formData.alert_type,
        threshold_value: formData.threshold_value ? parseFloat(formData.threshold_value) : null,
        sma_period: selectedTypeConfig?.requires_sma_period ? parseInt(formData.sma_period) : null,
        frequency: formData.frequency,
        notification_channels: formData.notification_channels,
      };

      if (isEditing) {
        // Update existing alert
        const result = await updateAlert(existingAlert.id, alertData);
        setSuccess('Alert updated successfully!');

        if (onAlertUpdated) {
          onAlertUpdated(result.alert);
        }
      } else {
        // Create new alert
        const result = await createAlert(alertData);
        setSuccess('Alert created successfully!');

        // Reset form
        setFormData({
          name: '',
          description: '',
          symbol: '',
          alert_type: '',
          threshold_value: '',
          sma_period: 200,
          frequency: 'once',
          notification_channels: ['in_app'],
        });
        setSelectedTypeConfig(null);

        if (onAlertCreated) {
          onAlertCreated(result.alert);
        }
      }

    } catch (err) {
      console.error(`Error ${isEditing ? 'updating' : 'creating'} alert:`, err);
      setError(err.response?.data?.detail || `Failed to ${isEditing ? 'update' : 'create'} alert`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Card title={isEditing ? "Edit Alert" : "Create Alert"}>
        <div className="flex justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      </Card>
    );
  }

  return (
    <Card title={isEditing ? `Edit Alert: ${existingAlert.name}` : "Create Dynamic Alert"}>
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Error/Success Messages */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-red-800 text-sm">
            {error}
          </div>
        )}
        {success && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-green-800 text-sm">
            {success}
          </div>
        )}

        {/* Alert Name */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Alert Name *
          </label>
          <input
            type="text"
            name="name"
            value={formData.name}
            onChange={handleInputChange}
            placeholder="e.g., NVDA IV Low Alert"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* Stock Symbol */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Stock Symbol *
          </label>
          <input
            type="text"
            name="symbol"
            value={formData.symbol}
            onChange={handleInputChange}
            placeholder="e.g., NVDA"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent uppercase"
          />
        </div>

        {/* Alert Type */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Alert Type *
          </label>
          <select
            name="alert_type"
            value={formData.alert_type}
            onChange={handleTypeChange}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="">Select alert type...</option>
            {alertTypes.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
          {selectedTypeConfig && (
            <p className="mt-1 text-sm text-gray-500">
              {selectedTypeConfig.description}
            </p>
          )}
        </div>

        {/* Threshold Value */}
        {selectedTypeConfig?.requires_threshold && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {selectedTypeConfig.threshold_label} *
            </label>
            <input
              type="number"
              name="threshold_value"
              value={formData.threshold_value}
              onChange={handleInputChange}
              step="any"
              placeholder={`e.g., ${selectedTypeConfig.default_threshold || ''}`}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        )}

        {/* SMA Period */}
        {selectedTypeConfig?.requires_sma_period && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              SMA Period
            </label>
            <select
              name="sma_period"
              value={formData.sma_period}
              onChange={handleInputChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              {selectedTypeConfig.sma_options.map((period) => (
                <option key={period} value={period}>
                  {period}-day SMA
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Frequency */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Frequency
          </label>
          <div className="grid grid-cols-3 gap-2">
            {frequencies.map((freq) => (
              <button
                key={freq.value}
                type="button"
                onClick={() => setFormData(prev => ({ ...prev, frequency: freq.value }))}
                className={`px-3 py-2 rounded-lg border text-sm transition-colors ${
                  formData.frequency === freq.value
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                {freq.label}
              </button>
            ))}
          </div>
          <p className="mt-1 text-xs text-gray-500">
            {frequencies.find(f => f.value === formData.frequency)?.description}
          </p>
        </div>

        {/* Notification Channels */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Notify via
          </label>
          <div className="flex flex-wrap gap-2">
            {channels.map((channel) => (
              <button
                key={channel.value}
                type="button"
                onClick={() => handleChannelToggle(channel.value)}
                className={`px-3 py-2 rounded-lg border text-sm transition-colors ${
                  formData.notification_channels.includes(channel.value)
                    ? 'bg-green-600 text-white border-green-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                {channel.value === 'in_app' && '🔔 '}
                {channel.value === 'telegram' && '📱 '}
                {channel.label}
              </button>
            ))}
          </div>
        </div>

        {/* Description (optional) */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Description (optional)
          </label>
          <textarea
            name="description"
            value={formData.description}
            onChange={handleInputChange}
            placeholder="Add any notes about this alert..."
            rows={2}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* Buttons */}
        <div className="flex gap-3">
          <Button type="submit" disabled={saving}>
            {saving ? (isEditing ? 'Saving...' : 'Creating...') : (isEditing ? 'Save Changes' : 'Create Alert')}
          </Button>
          {onClose && (
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
          )}
        </div>
      </form>
    </Card>
  );
}
