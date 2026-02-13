/**
 * Mock data fixtures for E2E tests
 * Shapes match the actual API response formats from the backend
 */

// =============================================================================
// Bot Configuration (matches BotConfiguration model — 33 columns)
// =============================================================================

export const MOCK_BOT_CONFIG = {
  id: 1,
  execution_mode: 'signal_only',
  paper_mode: true,
  max_position_size: 5000,
  max_portfolio_pct: 5.0,
  max_daily_trades: 10,
  max_daily_loss: 500,
  max_open_positions: 5,
  max_drawdown_pct: 10.0,
  sizing_mode: 'fixed_dollar',
  fixed_dollar_amount: 2500,
  portfolio_pct: 5.0,
  risk_per_trade_pct: 1.0,
  default_stop_loss_pct: 2.0,
  default_take_profit_pct: 4.0,
  enable_trailing_stop: false,
  trailing_stop_pct: 1.5,
  min_confidence_score: 60,
  allowed_strategies: ['orb_breakout', 'vwap_pullback', 'trend_following'],
  allowed_timeframes: ['1h', '1d'],
  min_risk_reward: 1.5,
  eod_close_enabled: true,
  eod_close_minutes_before: 15,
  circuit_breaker_consecutive_losses: 3,
  circuit_breaker_daily_loss_pct: 3.0,
  enable_options_trading: false,
  max_option_contracts: 5,
  max_option_premium: 1000,
  created_at: '2025-01-15T10:00:00Z',
  updated_at: '2025-01-20T14:30:00Z',
};

// =============================================================================
// Bot State (matches BotState model — 20 columns)
// =============================================================================

export const MOCK_BOT_STATE = {
  status: 'running',
  paper_mode: true,
  execution_mode: 'signal_only',
  daily_pl: 125.50,
  daily_pl_pct: 0.13,
  daily_trades: 3,
  daily_wins: 2,
  daily_losses: 1,
  open_positions: 2,
  circuit_breaker: 'none',
  consecutive_losses: 0,
  start_equity: 100000,
  current_equity: 100125.50,
  max_drawdown_today: 75.00,
  last_trade_at: '2025-01-20T15:30:00Z',
  started_at: '2025-01-20T09:30:00Z',
};

export const MOCK_BOT_STATE_PAUSED = {
  ...MOCK_BOT_STATE,
  status: 'paused',
  circuit_breaker: 'warning',
};

export const MOCK_BOT_STATE_HALTED = {
  ...MOCK_BOT_STATE,
  status: 'halted',
  circuit_breaker: 'halted',
  consecutive_losses: 3,
};

export const MOCK_BOT_STATE_STOPPED = {
  ...MOCK_BOT_STATE,
  status: 'stopped',
};

// =============================================================================
// Trading Signals (matches TradingSignal model)
// =============================================================================

export const MOCK_SIGNALS = [
  {
    id: 101,
    symbol: 'AAPL',
    direction: 'buy',
    strategy: 'orb_breakout',
    timeframe: '1h',
    confidence_score: 82.5,
    entry_price: 185.50,
    stop_loss: 182.00,
    target_1: 192.00,
    target_2: 198.00,
    risk_reward_ratio: 1.86,
    status: 'active',
    is_read: false,
    trade_executed: false,
    validation_status: 'validated',
    generated_at: '2025-01-20T10:15:00Z',
    expires_at: '2025-01-20T16:00:00Z',
    notes: 'Strong breakout above ORB high with volume confirmation',
  },
  {
    id: 102,
    symbol: 'MSFT',
    direction: 'buy',
    strategy: 'vwap_pullback',
    timeframe: '1h',
    confidence_score: 71.0,
    entry_price: 415.20,
    stop_loss: 410.00,
    target_1: 425.00,
    target_2: 430.00,
    risk_reward_ratio: 1.88,
    status: 'active',
    is_read: true,
    trade_executed: false,
    validation_status: 'validated',
    generated_at: '2025-01-20T10:30:00Z',
    expires_at: '2025-01-20T16:00:00Z',
    notes: 'VWAP bounce with RSI divergence',
  },
  {
    id: 103,
    symbol: 'NVDA',
    direction: 'buy',
    strategy: 'trend_following',
    timeframe: '1d',
    confidence_score: 88.0,
    entry_price: 875.00,
    stop_loss: 850.00,
    target_1: 920.00,
    target_2: 950.00,
    risk_reward_ratio: 1.80,
    status: 'active',
    is_read: false,
    trade_executed: false,
    validation_status: 'validated',
    generated_at: '2025-01-20T09:35:00Z',
    expires_at: '2025-01-21T09:30:00Z',
    notes: 'SMA20 crossed above SMA50 with ADX > 25',
  },
];

// =============================================================================
// Alpaca Positions
// =============================================================================

export const MOCK_POSITIONS = [
  {
    symbol: 'AAPL',
    name: 'Apple Inc.',
    quantity: 50,
    average_cost: 178.50,
    current_price: 185.50,
    market_value: 9275.00,
    unrealized_pl: 350.00,
    unrealized_pl_percent: 3.92,
    asset_type: 'stock',
    side: 'long',
    qty: '50',
    avg_entry_price: '178.50',
    unrealized_plpc: 0.0392,
  },
  {
    symbol: 'MSFT',
    name: 'Microsoft Corporation',
    quantity: 25,
    average_cost: 405.00,
    current_price: 415.20,
    market_value: 10380.00,
    unrealized_pl: 255.00,
    unrealized_pl_percent: 2.52,
    asset_type: 'stock',
    side: 'long',
    qty: '25',
    avg_entry_price: '405.00',
    unrealized_plpc: 0.0252,
  },
];

// =============================================================================
// Alpaca Account
// =============================================================================

export const MOCK_ACCOUNT = {
  status: 'ACTIVE',
  equity: '100000.00',
  buying_power: '200000.00',
  cash: '80000.00',
  portfolio_value: '20000.00',
  daytrade_count: 1,
  pattern_day_trader: false,
  trading_blocked: false,
};

// =============================================================================
// Signal Queue Items
// =============================================================================

export const MOCK_QUEUE_ITEMS = [
  {
    id: 201,
    symbol: 'AAPL',
    name: 'Apple Inc.',
    timeframe: '1h',
    strategy: 'orb_breakout',
    status: 'active',
    confidence_level: 'HIGH',
    source: 'auto_scan',
    times_checked: 5,
    signals_generated: 2,
    created_at: '2025-01-20T09:30:00Z',
    last_checked_at: '2025-01-20T10:15:00Z',
  },
  {
    id: 202,
    symbol: 'MSFT',
    name: 'Microsoft Corporation',
    timeframe: '1h',
    strategy: 'vwap_pullback',
    status: 'active',
    confidence_level: 'MEDIUM',
    source: 'auto_process',
    times_checked: 3,
    signals_generated: 1,
    created_at: '2025-01-20T09:30:00Z',
    last_checked_at: '2025-01-20T10:00:00Z',
  },
  {
    id: 203,
    symbol: 'NVDA',
    name: 'NVIDIA Corporation',
    timeframe: '1d',
    strategy: 'trend_following',
    status: 'paused',
    confidence_level: 'HIGH',
    source: 'auto_scan',
    times_checked: 10,
    signals_generated: 3,
    created_at: '2025-01-19T09:30:00Z',
    last_checked_at: '2025-01-20T09:45:00Z',
  },
];

// =============================================================================
// Queue Stats
// =============================================================================

export const MOCK_QUEUE_STATS = {
  active: 2,
  paused: 1,
  total: 3,
};

// =============================================================================
// Backtest Result (matches BacktestResult model)
// =============================================================================

export const MOCK_BACKTEST_RESULT = {
  id: 301,
  symbol: 'AAPL',
  strategy: 'orb_breakout',
  timeframe: '5m',
  cap_size: 'large_cap',
  start_date: '2024-07-01',
  end_date: '2025-01-01',
  initial_capital: 100000,
  position_size_pct: 10,
  status: 'completed',
  total_return_pct: 12.45,
  sharpe_ratio: 1.82,
  max_drawdown_pct: 6.5,
  win_rate: 58.3,
  total_trades: 24,
  winning_trades: 14,
  losing_trades: 10,
  profit_factor: 1.95,
  avg_win_pct: 2.8,
  avg_loss_pct: -1.5,
  best_trade_pct: 6.2,
  worst_trade_pct: -3.8,
  final_value: 112450,
  equity_curve: [
    { date: '2024-07-01 09:30', value: 100000 },
    { date: '2024-08-01 09:30', value: 101500 },
    { date: '2024-09-01 09:30', value: 103200 },
    { date: '2024-10-01 09:30', value: 102800 },
    { date: '2024-11-01 09:30', value: 106000 },
    { date: '2024-12-01 09:30', value: 109500 },
    { date: '2025-01-01 09:30', value: 112450 },
  ],
  trade_log: [
    {
      entry_date: '2024-07-05 09:45',
      exit_date: '2024-07-05 11:30',
      direction: 'buy',
      entry_price: 185.20,
      exit_price: 188.40,
      size: 54,
      pnl: 172.80,
      pnl_pct: 1.73,
      bars_held: 14,
    },
    {
      entry_date: '2024-07-12 09:40',
      exit_date: '2024-07-12 14:00',
      direction: 'buy',
      entry_price: 190.50,
      exit_price: 187.80,
      size: 52,
      pnl: -140.40,
      pnl_pct: -1.42,
      bars_held: 52,
    },
    {
      entry_date: '2024-07-19 09:50',
      exit_date: '2024-07-19 13:15',
      direction: 'buy',
      entry_price: 192.00,
      exit_price: 196.50,
      size: 52,
      pnl: 234.00,
      pnl_pct: 2.34,
      bars_held: 41,
    },
  ],
  created_at: '2025-01-20T10:00:00Z',
  error_message: null,
};

export const MOCK_BACKTEST_PENDING = {
  id: 301,
  symbol: 'AAPL',
  strategy: 'orb_breakout',
  timeframe: '5m',
  cap_size: 'large_cap',
  status: 'pending',
  created_at: '2025-01-20T10:00:00Z',
};

export const MOCK_BACKTEST_RUNNING = {
  ...MOCK_BACKTEST_PENDING,
  status: 'running',
};

// =============================================================================
// Executed Trades (matches ExecutedTrade model — 34 columns)
// =============================================================================

export const MOCK_EXECUTED_TRADES = [
  {
    id: 401,
    signal_id: 101,
    symbol: 'AAPL',
    direction: 'buy',
    strategy: 'orb_breakout',
    asset_type: 'stock',
    quantity: 27,
    entry_price: 185.50,
    exit_price: 191.20,
    take_profit_price: 192.00,
    stop_loss_price: 182.00,
    status: 'closed',
    exit_reason: 'take_profit',
    realized_pl: 153.90,
    realized_pl_pct: 3.07,
    paper_trade: true,
    opened_at: '2025-01-19T10:15:00Z',
    closed_at: '2025-01-19T14:30:00Z',
    notes: 'Bracket order filled cleanly',
  },
  {
    id: 402,
    signal_id: 102,
    symbol: 'MSFT',
    direction: 'buy',
    strategy: 'vwap_pullback',
    asset_type: 'stock',
    quantity: 12,
    entry_price: 415.20,
    exit_price: 410.50,
    take_profit_price: 425.00,
    stop_loss_price: 410.00,
    status: 'closed',
    exit_reason: 'stop_loss',
    realized_pl: -56.40,
    realized_pl_pct: -1.13,
    paper_trade: true,
    opened_at: '2025-01-18T11:00:00Z',
    closed_at: '2025-01-18T13:45:00Z',
    notes: 'Stop loss triggered on reversal',
  },
  {
    id: 403,
    signal_id: 103,
    symbol: 'NVDA',
    direction: 'buy',
    strategy: 'trend_following',
    asset_type: 'stock',
    quantity: 3,
    entry_price: 875.00,
    exit_price: null,
    take_profit_price: 920.00,
    stop_loss_price: 850.00,
    status: 'open',
    exit_reason: null,
    realized_pl: null,
    realized_pl_pct: null,
    paper_trade: true,
    opened_at: '2025-01-20T09:35:00Z',
    closed_at: null,
    notes: 'Position open, trend intact',
  },
];

// =============================================================================
// Preview Signal Response (from POST /api/v1/trading/bot/preview-signal/{id})
// =============================================================================

export const MOCK_PREVIEW_RESPONSE = {
  signal: MOCK_SIGNALS[0],
  current_price: 186.00,
  risk_check: {
    approved: true,
    reason: null,
    warnings: ['Approaching max daily trades (8/10)'],
  },
  sizing: {
    quantity: 13,
    notional: 2418.00,
    asset_type: 'stock',
    is_fractional: false,
    rejected: false,
    reject_reason: null,
    capped_reason: null,
  },
  config: {
    execution_mode: 'signal_only',
    paper_mode: true,
    sizing_mode: 'fixed_dollar',
    fixed_dollar_amount: 2500,
  },
  account: {
    equity: 100000,
    buying_power: 200000,
  },
};

// =============================================================================
// Execute Signal Response (from POST /api/v1/trading/bot/execute-signal/{id})
// =============================================================================

export const MOCK_EXECUTE_RESPONSE = {
  success: true,
  trade: {
    id: 410,
    signal_id: 101,
    symbol: 'AAPL',
    direction: 'buy',
    asset_type: 'stock',
    quantity: 13,
    entry_price: 186.00,
    take_profit_price: 192.00,
    stop_loss_price: 182.00,
    status: 'open',
    paper_trade: true,
    opened_at: '2025-01-20T10:20:00Z',
  },
};

// =============================================================================
// Bot Performance Response (from GET /api/v1/trading/bot/performance)
// =============================================================================

export const MOCK_PERFORMANCE = {
  total_trades: 45,
  win_rate: 55.6,
  total_pl: 1250.75,
  avg_pl_per_trade: 27.79,
  profit_factor: 1.65,
  max_drawdown: 425.00,
  avg_win: 85.50,
  avg_loss: -52.30,
  best_trade: 312.00,
  worst_trade: -185.00,
  period: {
    start: '2024-12-21',
    end: '2025-01-20',
  },
  by_strategy: {
    orb_breakout: { count: 20, wins: 12, losses: 8, pl: 650.00 },
    vwap_pullback: { count: 15, wins: 8, losses: 7, pl: 320.00 },
    trend_following: { count: 10, wins: 5, losses: 5, pl: 280.75 },
  },
  by_asset_type: {
    stock: { count: 40, wins: 23, losses: 17, pl: 1100.00 },
    option: { count: 5, wins: 2, losses: 3, pl: 150.75 },
  },
};

// =============================================================================
// Today Performance (from GET /api/v1/trading/bot/performance/today)
// =============================================================================

export const MOCK_TODAY_PERFORMANCE = {
  status: 'running',
  daily_pl: 125.50,
  daily_trades: 3,
  daily_wins: 2,
  daily_losses: 1,
  win_rate: 66.7,
  open_positions: 2,
};

// =============================================================================
// Daily Performance Records (from GET /api/v1/trading/bot/performance/daily)
// =============================================================================

export const MOCK_DAILY_RECORDS = [
  { date: '2025-01-20', trades: 3, wins: 2, losses: 1, win_rate: 66.7, net_pl: 125.50, best_trade: 95.00, worst_trade: -35.50 },
  { date: '2025-01-17', trades: 5, wins: 3, losses: 2, win_rate: 60.0, net_pl: 210.30, best_trade: 130.00, worst_trade: -65.00 },
  { date: '2025-01-16', trades: 4, wins: 2, losses: 2, win_rate: 50.0, net_pl: -45.20, best_trade: 80.00, worst_trade: -85.00 },
];

// =============================================================================
// Exit Reason Breakdown
// =============================================================================

export const MOCK_EXIT_REASONS = {
  take_profit: { count: 18, total_pl: 1530.00 },
  stop_loss: { count: 15, total_pl: -784.50 },
  trailing_stop: { count: 5, total_pl: 325.00 },
  eod_close: { count: 7, total_pl: 180.25 },
};

// =============================================================================
// Unread Count Response
// =============================================================================

export const MOCK_UNREAD_COUNT = {
  unread_count: 2,
};

// =============================================================================
// Settings Summary Response
// =============================================================================

export const MOCK_SETTINGS_SUMMARY = {
  settings: {
    screening: {},
    rate_limit: {},
    cache: {},
    feature: {},
    automation: {},
  },
  api_keys: [
    {
      service_name: 'alpaca',
      display_name: 'Alpaca Trading',
      description: 'Stock & options trading API',
      is_configured: true,
      always_available: false,
      usage_count: 150,
      error_count: 0,
      env_key: 'ALPACA_API_KEY',
    },
    {
      service_name: 'fmp',
      display_name: 'Financial Modeling Prep',
      description: 'Fundamentals & financial data',
      is_configured: true,
      always_available: false,
      usage_count: 500,
      error_count: 2,
      env_key: 'FMP_API_KEY',
    },
  ],
};

// =============================================================================
// Portfolio Summary
// =============================================================================

export const MOCK_PORTFOLIO_SUMMARY = {
  connected: true,
  total_portfolio_value: 120000,
  total_cash: 80000,
  total_invested: 40000,
  total_buying_power: 200000,
  total_positions: 5,
  total_unrealized_pl: 1250.00,
  total_unrealized_pl_percent: 3.23,
  last_sync: '2025-01-20T10:30:00Z',
};

// =============================================================================
// Brokers Status
// =============================================================================

export const MOCK_BROKERS_STATUS = [
  {
    type: 'alpaca',
    name: 'Alpaca',
    available: true,
    coming_soon: false,
    features: ['stocks', 'options', 'paper'],
  },
  {
    type: 'robinhood',
    name: 'Robinhood',
    available: true,
    coming_soon: false,
    features: ['stocks', 'options', 'crypto'],
  },
];

// =============================================================================
// Batch Quotes
// =============================================================================

export const MOCK_BATCH_QUOTES = {
  quotes: {
    AAPL: { current_price: 185.50, change_percent: 1.25 },
    MSFT: { current_price: 415.20, change_percent: -0.35 },
    NVDA: { current_price: 875.00, change_percent: 2.10 },
  },
};

// =============================================================================
// Backtest History List
// =============================================================================

export const MOCK_BACKTEST_LIST = [
  {
    id: 301,
    symbol: 'AAPL',
    strategy: 'orb_breakout',
    timeframe: '5m',
    cap_size: 'large_cap',
    total_return_pct: 12.45,
    sharpe_ratio: 1.82,
    total_trades: 24,
    status: 'completed',
    created_at: '2025-01-20T10:00:00Z',
  },
  {
    id: 302,
    symbol: 'MSFT',
    strategy: 'vwap_pullback',
    timeframe: '15m',
    cap_size: 'large_cap',
    total_return_pct: -3.20,
    sharpe_ratio: -0.45,
    total_trades: 18,
    status: 'completed',
    created_at: '2025-01-19T14:00:00Z',
  },
];

// =============================================================================
// Command Center Dashboard
// =============================================================================

export const MOCK_DASHBOARD = {
  market_pulse: {
    spy_price: 590.50,
    spy_change_pct: 0.35,
    qqq_price: 510.20,
    qqq_change_pct: 0.80,
    vix: 14.5,
    market_regime: 'bullish',
  },
  fear_greed: {
    value: 65,
    label: 'Greed',
  },
};

// =============================================================================
// News Items (for NewsTicker)
// =============================================================================

export const MOCK_NEWS = [
  { headline: 'Fed holds rates steady, signals future cuts', source: 'Reuters', url: '#' },
  { headline: 'Tech earnings beat expectations across the board', source: 'CNBC', url: '#' },
  { headline: 'Oil prices rise on supply concerns', source: 'Bloomberg', url: '#' },
];
