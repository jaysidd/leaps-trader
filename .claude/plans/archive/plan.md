# Trading Bot Implementation Plan — Dual Engine (Stocks + Options)

## Overview

Add a production-quality automated trading bot to LEAPS Trader. The bot connects the existing Signal Engine (3 strategies, confidence scoring, AI analysis) to Alpaca order execution via a 7-module safety pipeline. Supports stocks (fractional, bracket orders) AND options (limit orders, self-managed SL/TP). User-configurable limits protect capital.

**Guiding Principle**: Safety-first. Paper trading default. Every trade journaled. Circuit breakers non-negotiable. No silent failures.

---

## Architecture: 7-Module Pipeline

```
Signal Engine (existing, Module 1-2)
    │
    ▼
Risk Gateway (NEW, Module 3)
    │ Checks: per-trade limit, daily loss, max positions, buying power, circuit breaker, market hours
    ▼
Position Sizer (NEW, Module 4)
    │ Modes: fixed dollar, % of portfolio, risk-based ($ risk / stop distance)
    ▼
Order Executor (ENHANCED, Module 5)
    │ Stocks: bracket orders (entry+TP+SL). Options: limit order + self-managed exits
    ▼
Position Monitor (NEW, Module 6)
    │ Runs every 1min: SL/TP/trailing stop checks, signal invalidation, LEAPS roll alerts
    ▼
Trade Journal (NEW, Module 7)
    │ Records signal→entry→exit→P&L with exit reason. Performance analytics.
    ▼
Auto-Trader Orchestrator (NEW)
    │ State machine: STOPPED → RUNNING → PAUSED → HALTED
    │ Integrates into existing check_signals_job() in main.py
```

---

## Execution Modes (User Chooses in Settings)

| Mode | Behavior |
|------|----------|
| **Signal Only** | Generate signals, show on dashboard + Telegram. No auto-trading. (Current behavior, default) |
| **Semi-Auto** | Signal fires → user gets Telegram/dashboard notification → one-click "Approve" button → pipeline executes |
| **Full Auto** | Signal fires → risk check → size → execute → monitor → exit. Zero human input. |

---

## Phase 1: Database Models

### File: `backend/app/models/bot_config.py` (NEW)

```python
class ExecutionMode(str, enum.Enum):
    SIGNAL_ONLY = "signal_only"
    SEMI_AUTO = "semi_auto"
    FULL_AUTO = "full_auto"

class SizingMode(str, enum.Enum):
    FIXED_DOLLAR = "fixed_dollar"
    PCT_PORTFOLIO = "pct_portfolio"
    RISK_BASED = "risk_based"

class BotConfiguration(Base):
    __tablename__ = "bot_configuration"

    id = Column(Integer, primary_key=True)

    # Execution mode
    execution_mode = Column(String(20), default="signal_only")  # signal_only, semi_auto, full_auto
    paper_mode = Column(Boolean, default=True)  # ALWAYS default True

    # Per-Trade Limits (user-configurable)
    max_per_stock_trade = Column(Float, default=500.0)   # Max $ per stock trade
    max_per_options_trade = Column(Float, default=300.0)  # Max $ per options trade
    sizing_mode = Column(String(20), default="fixed_dollar")
    risk_pct_per_trade = Column(Float, default=1.0)       # For risk-based sizing: risk 1% of portfolio

    # Daily Limits
    max_daily_loss = Column(Float, default=500.0)         # Stop trading after this $ loss in a day
    max_trades_per_day = Column(Integer, default=10)
    max_concurrent_positions = Column(Integer, default=5)

    # Portfolio Limits
    max_portfolio_allocation_pct = Column(Float, default=10.0)  # Max 10% in any single position
    max_total_invested_pct = Column(Float, default=80.0)        # Keep 20% cash reserve

    # Exit Rules
    default_take_profit_pct = Column(Float, default=20.0)
    default_stop_loss_pct = Column(Float, default=10.0)
    trailing_stop_enabled = Column(Boolean, default=False)
    trailing_stop_pct = Column(Float, default=5.0)
    close_positions_eod = Column(Boolean, default=False)  # Close all before market close
    leaps_roll_alert_dte = Column(Integer, default=60)    # Alert when LEAPS reaches this DTE

    # Signal Filters
    min_confidence_to_execute = Column(Float, default=75.0)
    require_ai_analysis = Column(Boolean, default=False)
    min_ai_conviction = Column(Float, default=7.0)        # Out of 10
    enabled_strategies = Column(JSON, default=["orb_breakout", "vwap_pullback", "range_breakout"])

    # Circuit Breakers (percentage of daily starting equity)
    circuit_breaker_warn_pct = Column(Float, default=3.0)   # 3% → log warning
    circuit_breaker_pause_pct = Column(Float, default=5.0)  # 5% → pause bot, notify user
    circuit_breaker_halt_pct = Column(Float, default=10.0)  # 10% → halt bot, require manual restart
    auto_resume_next_day = Column(Boolean, default=True)

    # Options-Specific
    max_bid_ask_spread_pct = Column(Float, default=15.0)
    min_option_open_interest = Column(Integer, default=100)
    min_option_delta = Column(Float, default=0.30)
    options_order_type = Column(String(20), default="limit")  # Always limit for options

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

### File: `backend/app/models/executed_trade.py` (NEW)

```python
class ExitReason(str, enum.Enum):
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    TIME_EXIT = "time_exit"             # EOD close or expiry approaching
    SIGNAL_INVALIDATED = "signal_invalidated"
    CIRCUIT_BREAKER = "circuit_breaker"
    MANUAL = "manual"                   # User closed manually
    KILL_SWITCH = "kill_switch"         # Emergency stop
    PARTIAL_EXIT = "partial_exit"

class TradeStatus(str, enum.Enum):
    PENDING_ENTRY = "pending_entry"     # Order submitted, awaiting fill
    OPEN = "open"                       # Position active
    PENDING_EXIT = "pending_exit"       # Exit order submitted
    CLOSED = "closed"                   # Fully exited
    CANCELLED = "cancelled"             # Entry order cancelled/rejected
    ERROR = "error"                     # Something went wrong

class ExecutedTrade(Base):
    __tablename__ = "executed_trades"

    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey('trading_signals.id'), nullable=True, index=True)

    # What was traded
    symbol = Column(String(20), nullable=False, index=True)
    asset_type = Column(String(10), nullable=False, default="stock")  # stock, option
    direction = Column(String(10), nullable=False)                    # buy, sell
    option_symbol = Column(String(50), nullable=True)                 # Full OCC symbol for options
    option_type = Column(String(10), nullable=True)                   # call, put
    option_strike = Column(Float, nullable=True)
    option_expiry = Column(Date, nullable=True)

    # Entry
    entry_order_id = Column(String(100), nullable=True)   # Alpaca order ID
    entry_price = Column(Float, nullable=True)
    entry_filled_at = Column(DateTime(timezone=True), nullable=True)
    quantity = Column(Float, nullable=False)                # Shares or contracts
    notional = Column(Float, nullable=True)                 # Dollar value at entry
    is_fractional = Column(Boolean, default=False)

    # Exit targets (set at entry, can be updated)
    take_profit_price = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    trailing_stop_pct = Column(Float, nullable=True)
    trailing_stop_high_water = Column(Float, nullable=True) # Highest price since entry (for trailing)

    # Bracket order IDs (stocks only — Alpaca creates child orders)
    tp_order_id = Column(String(100), nullable=True)
    sl_order_id = Column(String(100), nullable=True)

    # Exit
    exit_order_id = Column(String(100), nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_filled_at = Column(DateTime(timezone=True), nullable=True)
    exit_reason = Column(String(30), nullable=True)         # ExitReason enum value

    # P&L
    realized_pl = Column(Float, nullable=True)              # Dollar P&L
    realized_pl_pct = Column(Float, nullable=True)          # Percentage P&L
    fees = Column(Float, default=0.0)

    # Meta
    status = Column(String(20), default="pending_entry", index=True)
    execution_mode = Column(String(20), nullable=True)       # What mode was active when executed
    hold_duration_minutes = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)                      # Any notes (circuit breaker reason, etc.)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index('idx_trade_status', 'status'),
        Index('idx_trade_symbol', 'symbol'),
        Index('idx_trade_signal', 'signal_id'),
        Index('idx_trade_created', 'created_at'),
        Index('idx_trade_exit_reason', 'exit_reason'),
    )
```

### File: `backend/app/models/bot_state.py` (NEW)

```python
class CircuitBreakerLevel(str, enum.Enum):
    NONE = "none"
    WARNING = "warning"
    PAUSED = "paused"
    HALTED = "halted"

class BotStatus(str, enum.Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"       # Circuit breaker or user-paused
    HALTED = "halted"       # Critical circuit breaker — requires manual restart

class BotState(Base):
    __tablename__ = "bot_state"

    id = Column(Integer, primary_key=True)
    status = Column(String(20), default="stopped")

    # Daily tracking (reset at market open)
    daily_pl = Column(Float, default=0.0)
    daily_trades_count = Column(Integer, default=0)
    daily_wins = Column(Integer, default=0)
    daily_losses = Column(Integer, default=0)
    daily_start_equity = Column(Float, nullable=True)       # Snapshot at market open

    # Circuit breaker
    circuit_breaker_level = Column(String(20), default="none")
    circuit_breaker_triggered_at = Column(DateTime(timezone=True), nullable=True)
    circuit_breaker_reason = Column(String(255), nullable=True)

    # Position tracking
    open_positions_count = Column(Integer, default=0)
    open_stock_positions = Column(Integer, default=0)
    open_option_positions = Column(Integer, default=0)

    # Health
    last_health_check = Column(DateTime(timezone=True), nullable=True)
    last_signal_processed_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    consecutive_errors = Column(Integer, default=0)

    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

### File: `backend/app/models/daily_bot_performance.py` (NEW)

```python
class DailyBotPerformance(Base):
    __tablename__ = "daily_bot_performance"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True, index=True)

    trades_count = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    win_rate = Column(Float, nullable=True)                 # 0-100
    gross_pl = Column(Float, default=0.0)
    net_pl = Column(Float, default=0.0)                     # After fees
    total_fees = Column(Float, default=0.0)

    best_trade_pl = Column(Float, nullable=True)
    worst_trade_pl = Column(Float, nullable=True)
    avg_trade_pl = Column(Float, nullable=True)
    avg_hold_minutes = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)

    start_equity = Column(Float, nullable=True)
    end_equity = Column(Float, nullable=True)

    stocks_traded = Column(Integer, default=0)
    options_traded = Column(Integer, default=0)
    circuit_breaker_triggered = Column(Boolean, default=False)
```

### Changes to `backend/app/models/__init__.py`
Add imports for: `BotConfiguration`, `ExecutedTrade`, `BotState`, `DailyBotPerformance`

### Verification
- Restart backend → tables auto-created
- Check PostgreSQL: `\dt` shows new tables
- Test: `curl localhost:8000/health` returns healthy

---

## Phase 2: Enhanced Trading Service (Bracket + Stop + Options Orders)

### File: `backend/app/services/trading/alpaca_trading_service.py` (MODIFY)

Add these methods to existing `AlpacaTradingService` class:

**`place_bracket_order(symbol, qty, side, limit_price, take_profit_price, stop_loss_price, time_in_force="day") -> Dict`**
- Uses `MarketOrderRequest` (or `LimitOrderRequest`) with `take_profit=TakeProfitRequest(limit_price=tp)` and `stop_loss=StopLossRequest(stop_price=sl)`
- Import `TakeProfitRequest`, `StopLossRequest` from `alpaca.trading.requests`
- Returns entry order + child order IDs

**`place_stop_order(symbol, qty, side, stop_price, time_in_force="day") -> Dict`**
- Uses existing `StopOrderRequest`

**`place_trailing_stop_order(symbol, qty, side, trail_percent, time_in_force="day") -> Dict`**
- Import `TrailingStopOrderRequest` from `alpaca.trading.requests`

**`place_notional_order(symbol, notional, side, time_in_force="day") -> Dict`**
- For fractional shares: `MarketOrderRequest` with `notional=amount` instead of `qty`

**`place_option_order(option_symbol, qty, side, limit_price, time_in_force="day") -> Dict`**
- Option symbols use OCC format: "AAPL250117C00150000"
- Always limit orders for options
- `time_in_force` must be "day" for options (Alpaca limitation)

**`get_order_status(order_id) -> Dict`**
- Enhanced version of `get_order` with fill details and child order tracking

**`cancel_all_orders() -> Dict`**
- `self._client.cancel_orders()` — for kill switch

**`close_all_positions() -> Dict`**
- `self._client.close_all_positions()` — for kill switch

### Verification
- Unit test: place bracket paper order for AAPL → confirm 3 orders created (parent + TP + SL)
- Unit test: place notional $100 order for AAPL → confirm fractional qty
- Unit test: cancel_all_orders on paper account

---

## Phase 3: Risk Gateway

### File: `backend/app/services/trading/risk_gateway.py` (NEW)

```python
class RiskCheckResult:
    approved: bool
    reason: str              # "" if approved, explanation if rejected
    adjusted_params: dict    # May reduce quantity if position limit exceeded
    warnings: list[str]      # Non-blocking warnings (e.g., approaching daily limit)

class RiskGateway:
    def __init__(self, db: Session):
        self.db = db

    def check_trade(
        self,
        signal: TradingSignal,
        bot_config: BotConfiguration,
        bot_state: BotState,
        account: dict          # From alpaca get_account()
    ) -> RiskCheckResult:
        """Run all risk checks. Returns approved/rejected with reason."""
        # Checks run in order (fail-fast):
        # 1. Bot status check (must be RUNNING)
        # 2. Circuit breaker check (must be NONE or WARNING)
        # 3. Market hours check (market must be open)
        # 4. Daily trade count check (< max_trades_per_day)
        # 5. Daily loss check (daily_pl + this trade's max loss < max_daily_loss)
        # 6. Concurrent positions check (< max_concurrent_positions)
        # 7. Per-trade limit check (trade cost < max_per_stock_trade or max_per_options_trade)
        # 8. Buying power check (sufficient buying power for trade)
        # 9. Portfolio allocation check (position < max_portfolio_allocation_pct of equity)
        # 10. Total invested check (total invested < max_total_invested_pct)
        # 11. Confidence filter (signal.confidence >= min_confidence_to_execute)
        # 12. AI analysis filter (if require_ai_analysis: signal must have ai_deep_analysis)
        # 13. Strategy filter (signal.strategy must be in enabled_strategies)
        # 14. Duplicate position check (no existing position in same symbol+direction)
        # 15. Options-specific: bid-ask spread check (< max_bid_ask_spread_pct)
        # 16. Options-specific: open interest check (> min_option_open_interest)

    def update_circuit_breaker(self, bot_config, bot_state, account) -> CircuitBreakerLevel:
        """Check daily P&L against circuit breaker thresholds. Returns new level."""
        # Calculate current drawdown: (daily_start_equity - current_equity) / daily_start_equity
        # Compare against warn/pause/halt thresholds
        # Update bot_state.circuit_breaker_level
        # If PAUSED or HALTED: send Telegram notification
```

### Verification
- Unit test: signal with confidence 60 + min_confidence 75 → REJECTED
- Unit test: daily_loss $480 + max_daily_loss $500 + new trade max risk $50 → REJECTED
- Unit test: 5 open positions + max_concurrent 5 → REJECTED
- Unit test: valid signal passing all checks → APPROVED

---

## Phase 4: Position Sizer

### File: `backend/app/services/trading/position_sizer.py` (NEW)

```python
class SizeResult:
    quantity: float          # Shares or contracts
    notional: float          # Dollar value
    is_fractional: bool      # True if fractional shares
    is_notional_order: bool  # True if should use notional order type
    asset_type: str          # "stock" or "option"
    capped_reason: str       # "" or "capped by max_per_trade" etc.

class PositionSizer:
    def calculate_size(
        self,
        signal: TradingSignal,
        bot_config: BotConfiguration,
        account: dict,
        current_price: float,
        asset_type: str = "stock"
    ) -> SizeResult:
        """Calculate position size based on configured mode."""

        if bot_config.sizing_mode == "fixed_dollar":
            # Stock: max_per_stock_trade / current_price = shares (fractional OK)
            # Option: max_per_options_trade / (option_premium * 100) = contracts (whole only)
            # Use notional order for stocks when fractional

        elif bot_config.sizing_mode == "pct_portfolio":
            # Dollar amount = equity * (max_portfolio_allocation_pct / 100)
            # Then same division as fixed_dollar

        elif bot_config.sizing_mode == "risk_based":
            # Risk amount = equity * (risk_pct_per_trade / 100)
            # Stop distance = abs(entry_price - stop_loss)
            # Shares = risk_amount / stop_distance
            # Requires signal to have stop_loss set

        # Final cap: never exceed max_per_stock_trade or max_per_options_trade
        # For options: round down to whole contracts, minimum 1
```

### Verification
- Unit test: fixed_dollar $500, AAPL @ $230 → 2.17 shares (fractional, notional order)
- Unit test: fixed_dollar $500, PLTR @ $25 → 20 shares (whole, regular order)
- Unit test: risk_based 1%, $50k equity, entry $100, SL $95 → risk $500, shares = $500/$5 = 100
- Unit test: option $300 budget, premium $2.50 → 1 contract ($250 < $300)

---

## Phase 5: Order Executor

### File: `backend/app/services/trading/order_executor.py` (NEW)

```python
class OrderResult:
    success: bool
    order_id: str
    child_order_ids: dict    # {"take_profit": "...", "stop_loss": "..."} for bracket
    fill_price: float
    fill_qty: float
    error: str

class OrderExecutor:
    def __init__(self, trading_service: AlpacaTradingService):
        self.trading = trading_service

    def execute_entry(
        self,
        signal: TradingSignal,
        size_result: SizeResult,
        bot_config: BotConfiguration,
    ) -> OrderResult:
        """Place entry order based on asset type."""

        if size_result.asset_type == "stock":
            # Calculate TP/SL prices from signal or config defaults
            tp_price = signal.target_1 or (signal.entry_price * (1 + bot_config.default_take_profit_pct / 100))
            sl_price = signal.stop_loss or (signal.entry_price * (1 - bot_config.default_stop_loss_pct / 100))

            if size_result.is_notional_order:
                # Notional order (fractional) — no bracket support
                # Place market notional, then set up separate SL monitoring
                result = self.trading.place_notional_order(...)
                # SL/TP will be handled by Position Monitor (Module 6)
            else:
                # Bracket order (whole shares) — TP+SL built in
                result = self.trading.place_bracket_order(
                    symbol, qty, "buy", entry_price, tp_price, sl_price
                )

        elif size_result.asset_type == "option":
            # Options: always limit order at mid-price
            # No bracket orders for options — SL/TP handled by Position Monitor
            mid_price = (bid + ask) / 2
            result = self.trading.place_option_order(
                option_symbol, qty=size_result.quantity, side="buy",
                limit_price=mid_price
            )

    def execute_exit(
        self,
        trade: ExecutedTrade,
        reason: ExitReason,
    ) -> OrderResult:
        """Exit an open position."""
        if trade.asset_type == "stock":
            return self.trading.close_position(trade.symbol, qty=trade.quantity)
        elif trade.asset_type == "option":
            return self.trading.place_option_order(
                trade.option_symbol, qty=trade.quantity, side="sell",
                limit_price=current_mid_price
            )

    def cancel_all(self) -> dict:
        """Kill switch: cancel all open orders."""
        return self.trading.cancel_all_orders()

    def close_all(self) -> dict:
        """Kill switch: close all positions."""
        return self.trading.close_all_positions()
```

### Verification
- Paper trade test: bracket buy AAPL → verify 3 orders in Alpaca dashboard
- Paper trade test: notional $100 buy AAPL → verify fractional fill
- Paper trade test: exit position → verify closed

---

## Phase 6: Position Monitor

### File: `backend/app/services/trading/position_monitor.py` (NEW)

```python
class ExitSignal:
    trade_id: int
    reason: ExitReason
    current_price: float
    trigger_price: float     # The price that triggered the exit

class PositionMonitor:
    def __init__(self, db: Session, trading_service, alpaca_data_service):
        self.db = db
        self.trading = trading_service
        self.data = alpaca_data_service

    def check_all_positions(self, bot_config: BotConfiguration) -> list[ExitSignal]:
        """Check all open ExecutedTrades for exit conditions. Returns exit signals."""
        open_trades = self.db.query(ExecutedTrade).filter(
            ExecutedTrade.status == "open"
        ).all()

        exit_signals = []
        for trade in open_trades:
            signal = self._check_single_position(trade, bot_config)
            if signal:
                exit_signals.append(signal)
        return exit_signals

    def _check_single_position(self, trade, bot_config) -> ExitSignal | None:
        """Check one position for exit conditions. Order of checks:"""
        current_price = self._get_current_price(trade)

        # 1. Stop loss check
        if trade.stop_loss_price and current_price <= trade.stop_loss_price:
            return ExitSignal(trade.id, ExitReason.STOP_LOSS, current_price, trade.stop_loss_price)

        # 2. Take profit check
        if trade.take_profit_price and current_price >= trade.take_profit_price:
            return ExitSignal(trade.id, ExitReason.TAKE_PROFIT, current_price, trade.take_profit_price)

        # 3. Trailing stop check + high water mark update
        if trade.trailing_stop_pct:
            if current_price > (trade.trailing_stop_high_water or trade.entry_price):
                trade.trailing_stop_high_water = current_price
                self.db.commit()
            trailing_stop_price = trade.trailing_stop_high_water * (1 - trade.trailing_stop_pct / 100)
            if current_price <= trailing_stop_price:
                return ExitSignal(trade.id, ExitReason.TRAILING_STOP, current_price, trailing_stop_price)

        # 4. EOD close check
        if bot_config.close_positions_eod and self._is_near_market_close():
            return ExitSignal(trade.id, ExitReason.TIME_EXIT, current_price, 0)

        # 5. Signal invalidation check (if original signal has conditions)
        # Check TradingSignal.invalidation_conditions against current market data

        # 6. LEAPS roll alert (options only)
        if trade.asset_type == "option" and trade.option_expiry:
            dte = (trade.option_expiry - date.today()).days
            if dte <= bot_config.leaps_roll_alert_dte:
                # Don't auto-exit, but send alert via Telegram
                self._send_roll_alert(trade, dte)

        return None

    def health_check(self, bot_state: BotState) -> bool:
        """Verify bot state consistency. Returns False if inconsistent."""
        # Compare: open_positions_count in bot_state vs actual Alpaca positions
        # Compare: open ExecutedTrade records vs Alpaca positions
        # If mismatch: log error, set bot_state.last_error, return False
```

### Scheduler Integration (in `main.py`)
```python
# NEW: Monitor positions every 1 minute during market hours
scheduler.add_job(
    monitor_positions_job,
    'interval',
    minutes=1,
    id='position_monitor',
    replace_existing=True
)
```

### Verification
- Unit test: trade with SL $95, current price $94 → ExitSignal(STOP_LOSS)
- Unit test: trade with TP $120, current price $121 → ExitSignal(TAKE_PROFIT)
- Unit test: trailing stop 5%, high water $110, current $103 → ExitSignal(TRAILING_STOP)
- Unit test: health check with mismatched position counts → returns False

---

## Phase 7: Trade Journal

### File: `backend/app/services/trading/trade_journal.py` (NEW)

```python
class TradeJournal:
    def __init__(self, db: Session):
        self.db = db

    def record_entry(self, signal, order_result, bot_config, size_result) -> ExecutedTrade:
        """Create ExecutedTrade record when entry order fills."""
        trade = ExecutedTrade(
            signal_id=signal.id,
            symbol=signal.symbol,
            asset_type=size_result.asset_type,
            direction=signal.direction,
            entry_order_id=order_result.order_id,
            entry_price=order_result.fill_price,
            entry_filled_at=datetime.now(timezone.utc),
            quantity=order_result.fill_qty,
            notional=order_result.fill_price * order_result.fill_qty,
            is_fractional=size_result.is_fractional,
            take_profit_price=...,   # From signal or config default
            stop_loss_price=...,
            trailing_stop_pct=bot_config.trailing_stop_pct if bot_config.trailing_stop_enabled else None,
            tp_order_id=order_result.child_order_ids.get("take_profit"),
            sl_order_id=order_result.child_order_ids.get("stop_loss"),
            status="open",
            execution_mode=bot_config.execution_mode,
            # option fields if applicable...
        )
        self.db.add(trade)
        self.db.commit()
        return trade

    def record_exit(self, trade, exit_order_result, reason) -> ExecutedTrade:
        """Update ExecutedTrade when position is closed."""
        trade.exit_order_id = exit_order_result.order_id
        trade.exit_price = exit_order_result.fill_price
        trade.exit_filled_at = datetime.now(timezone.utc)
        trade.exit_reason = reason.value
        trade.realized_pl = (trade.exit_price - trade.entry_price) * trade.quantity * (1 if trade.direction == "buy" else -1)
        trade.realized_pl_pct = (trade.realized_pl / trade.notional) * 100
        trade.hold_duration_minutes = (trade.exit_filled_at - trade.entry_filled_at).total_seconds() / 60
        trade.status = "closed"
        self.db.commit()
        return trade

    def get_daily_stats(self, date) -> dict:
        """Aggregate today's trades into performance metrics."""
        # Query ExecutedTrades for given date
        # Calculate: trades_count, wins, losses, win_rate, gross_pl, net_pl
        # best_trade, worst_trade, avg_hold_minutes
        # Upsert into DailyBotPerformance table

    def get_performance_summary(self, start_date, end_date) -> dict:
        """Performance analytics over a date range."""
        # Return: total_trades, win_rate, total_pl, avg_pl_per_trade,
        # sharpe_ratio, max_drawdown, equity_curve (list of daily equity values),
        # best_day, worst_day, avg_hold_time,
        # by_strategy breakdown, by_asset_type breakdown
```

### Verification
- Integration test: full cycle — signal → entry → monitor → exit → verify ExecutedTrade record complete
- Unit test: P&L calculation: buy 10 @ $100, sell @ $110 → realized_pl = $100, pct = 10%

---

## Phase 8: Auto-Trader Orchestrator

### File: `backend/app/services/trading/auto_trader.py` (NEW)

```python
class AutoTrader:
    """
    Orchestrates the full trading pipeline.
    State machine: STOPPED → RUNNING → PAUSED → HALTED
    """
    def __init__(self):
        self._risk_gateway = None
        self._position_sizer = None
        self._order_executor = None
        self._position_monitor = None
        self._trade_journal = None

    def _init_services(self, db: Session):
        """Lazy-init services with db session."""
        from app.services.trading.alpaca_trading_service import alpaca_trading_service
        config = self._get_config(db)
        state = self._get_or_create_state(db)

        self._risk_gateway = RiskGateway(db)
        self._position_sizer = PositionSizer()
        self._order_executor = OrderExecutor(alpaca_trading_service)
        self._position_monitor = PositionMonitor(db, alpaca_trading_service, alpaca_data_service)
        self._trade_journal = TradeJournal(db)
        return config, state

    def process_new_signals(self, signals: list[TradingSignal], db: Session) -> list[ExecutedTrade]:
        """Main pipeline: signal → risk → size → execute → journal. Called from check_signals_job."""
        config, state = self._init_services(db)

        if config.execution_mode == "signal_only":
            return []  # Nothing to do

        executed = []
        account = alpaca_trading_service.get_account()

        for signal in signals:
            # Skip if below confidence threshold
            if (signal.confidence_score or 0) < config.min_confidence_to_execute:
                continue

            # Semi-auto: mark as pending approval, don't execute
            if config.execution_mode == "semi_auto":
                self._mark_pending_approval(signal, db)
                continue

            # Full-auto: run the pipeline
            trade = self._execute_signal(signal, config, state, account, db)
            if trade:
                executed.append(trade)

        return executed

    def execute_approved_signal(self, signal_id: int, db: Session) -> ExecutedTrade:
        """Semi-auto: user approved a signal. Execute it now."""
        signal = db.query(TradingSignal).get(signal_id)
        config, state = self._init_services(db)
        account = alpaca_trading_service.get_account()
        return self._execute_signal(signal, config, state, account, db)

    def _execute_signal(self, signal, config, state, account, db) -> ExecutedTrade | None:
        """Core pipeline for a single signal."""
        # 1. Risk check
        risk_result = self._risk_gateway.check_trade(signal, config, state, account)
        if not risk_result.approved:
            logger.info(f"Signal {signal.symbol} rejected by risk gateway: {risk_result.reason}")
            self._notify_rejection(signal, risk_result)
            return None

        # 2. Position sizing
        current_price = self._get_current_price(signal.symbol)
        size_result = self._position_sizer.calculate_size(signal, config, account, current_price)

        # 3. Execute entry
        order_result = self._order_executor.execute_entry(signal, size_result, config)
        if not order_result.success:
            logger.error(f"Order failed for {signal.symbol}: {order_result.error}")
            return None

        # 4. Journal the trade
        trade = self._trade_journal.record_entry(signal, order_result, config, size_result)

        # 5. Update state
        state.daily_trades_count += 1
        state.open_positions_count += 1
        db.commit()

        # 6. Update circuit breaker
        self._risk_gateway.update_circuit_breaker(config, state, account)

        # 7. Notify
        self._send_execution_notification(signal, trade)

        return trade

    def start(self, db: Session) -> dict:
        """Start the bot. Validates config first."""
        config = self._get_config(db)
        state = self._get_or_create_state(db)

        # Validation: must have Alpaca configured + paper_mode check
        if not alpaca_trading_service.is_available:
            return {"error": "Alpaca trading not configured"}

        # Snapshot starting equity
        account = alpaca_trading_service.get_account()
        state.daily_start_equity = account["equity"]
        state.status = "running"
        state.started_at = datetime.now(timezone.utc)
        state.consecutive_errors = 0
        db.commit()

        return {"status": "running", "paper_mode": config.paper_mode}

    def stop(self, db: Session) -> dict:
        """Graceful stop. Does NOT cancel orders or close positions."""
        state = self._get_or_create_state(db)
        state.status = "stopped"
        db.commit()
        return {"status": "stopped"}

    def emergency_stop(self, close_positions: bool, db: Session) -> dict:
        """Kill switch. Cancels all orders. Optionally closes all positions."""
        state = self._get_or_create_state(db)
        results = {"orders_cancelled": 0, "positions_closed": 0}

        # Cancel all orders
        cancel_result = self._order_executor.cancel_all()
        results["orders_cancelled"] = cancel_result.get("count", 0)

        # Close all positions if requested
        if close_positions:
            close_result = self._order_executor.close_all()
            results["positions_closed"] = close_result.get("count", 0)

            # Mark all open ExecutedTrades as closed with kill_switch reason
            open_trades = db.query(ExecutedTrade).filter(ExecutedTrade.status == "open").all()
            for trade in open_trades:
                trade.status = "closed"
                trade.exit_reason = "kill_switch"
                trade.exit_filled_at = datetime.now(timezone.utc)

        state.status = "stopped"
        state.circuit_breaker_level = "none"
        state.open_positions_count = 0
        db.commit()

        # Notify
        self._send_telegram(f"🚨 EMERGENCY STOP executed. Orders cancelled: {results['orders_cancelled']}. Positions closed: {results['positions_closed']}")

        return results

    def _get_config(self, db) -> BotConfiguration:
        config = db.query(BotConfiguration).first()
        if not config:
            config = BotConfiguration()  # All defaults
            db.add(config)
            db.commit()
        return config

    def _get_or_create_state(self, db) -> BotState:
        state = db.query(BotState).first()
        if not state:
            state = BotState()
            db.add(state)
            db.commit()
        return state

# Singleton
auto_trader = AutoTrader()
```

### Integration into `main.py` — modify `check_signals_job()`
After `new_signals = signal_engine.process_all_queue_items(db)`, add:
```python
# ── Auto-trading pipeline ──
if new_signals:
    try:
        from app.services.trading.auto_trader import auto_trader
        executed_trades = auto_trader.process_new_signals(new_signals, db)
        if executed_trades:
            logger.info(f"Auto-trader executed {len(executed_trades)} trades")
    except Exception as e:
        logger.error(f"Auto-trader error: {e}")
```

### New scheduler jobs in `main.py`

```python
# Position monitor: every 1 minute during market hours
async def monitor_positions_job():
    """Monitor open positions for SL/TP/trailing stop exits."""
    # Market hours check (same as check_signals_job)
    db = SessionLocal()
    try:
        from app.services.trading.auto_trader import auto_trader
        auto_trader.check_and_exit_positions(db)
    finally:
        db.close()

# Daily reset: at 9:30 AM ET
async def bot_daily_reset_job():
    """Reset daily counters at market open."""
    db = SessionLocal()
    try:
        from app.services.trading.auto_trader import auto_trader
        auto_trader.daily_reset(db)
    finally:
        db.close()

# Health check: every 5 minutes
async def bot_health_check_job():
    """Verify bot state consistency."""
    db = SessionLocal()
    try:
        from app.services.trading.auto_trader import auto_trader
        auto_trader.health_check(db)
    finally:
        db.close()
```

### Verification
- Integration test: create BotConfig (full_auto, paper_mode=True), create signal, call process_new_signals → ExecutedTrade created
- Integration test: emergency_stop with close_positions=True → all orders cancelled, positions closed
- Test: signal_only mode → process_new_signals returns empty list

---

## Phase 9: API Endpoints

### File: `backend/app/api/endpoints/bot.py` (NEW)

```python
router = APIRouter(dependencies=[Depends(require_trading_auth)])

# Configuration
GET  /config              → Get current BotConfiguration
PUT  /config              → Update BotConfiguration (validates constraints)

# Bot Control
POST /start               → Start bot (validates config, snapshots equity)
POST /stop                → Graceful stop
POST /pause               → Pause bot
POST /resume              → Resume from pause
POST /emergency-stop      → Kill switch (body: { close_positions: bool })

# Status
GET  /status              → BotState + account summary + active config snapshot

# Signal Approval (semi-auto mode)
POST /approve/{signal_id} → Approve a pending signal for execution
POST /reject/{signal_id}  → Reject a pending signal

# Trade Journal
GET  /trades              → List executed trades (filters: status, symbol, date_range, exit_reason)
GET  /trades/{trade_id}   → Single trade detail with linked signal
GET  /trades/active       → Currently open trades only

# Performance
GET  /performance         → Summary stats (win_rate, total_pl, sharpe, equity_curve)
GET  /performance/daily   → List of DailyBotPerformance records
GET  /performance/today   → Today's live stats from BotState
```

### Register in `main.py`
```python
from app.api.endpoints import bot
app.include_router(bot.router, prefix=f"{app_settings.API_V1_PREFIX}/trading/bot", tags=["trading-bot"])
```

### Verification
- `curl -X GET localhost:8000/api/v1/trading/bot/config` → returns default config
- `curl -X PUT localhost:8000/api/v1/trading/bot/config -d '{"max_per_stock_trade": 100}'` → updates
- `curl -X POST localhost:8000/api/v1/trading/bot/start` → returns running status

---

## Phase 10: Scheduler Integration

### File: `backend/app/main.py` (MODIFY)

Add 3 new scheduler jobs:
1. `monitor_positions_job` — every 1 minute (position SL/TP monitoring)
2. `bot_daily_reset_job` — cron at 9:30 AM ET weekdays (daily counter reset)
3. `bot_health_check_job` — every 5 minutes (state consistency verification)

Modify existing `check_signals_job` to call `auto_trader.process_new_signals()` after signal generation.

### Verification
- Check scheduler logs: "Schedulers started (alerts: 5min, signals: 5min, positions: 1min, bot_reset: 9:30ET, health: 5min, ...)"
- Monitor: position_monitor fires every minute during market hours

---

## Phase 11: Frontend — Settings Auto-Trading Tab

### File: `frontend/src/pages/Settings.jsx` (MODIFY)

Add new tab: `{ id: 'auto-trading', label: 'Auto Trading', icon: '🤖', description: 'Trading bot configuration' }`

### File: `frontend/src/components/settings/AutoTradingSettings.jsx` (NEW)

Sections:
1. **Execution Mode** — Radio group: Signal Only / Semi-Auto / Full Auto
   - Warning banner when Full Auto selected
   - Paper/Live toggle with red warning for Live

2. **Per-Trade Limits** — Number inputs for:
   - Max $ Per Stock Trade
   - Max $ Per Options Trade
   - Sizing Mode dropdown (Fixed Dollar / % of Portfolio / Risk-Based)

3. **Daily Limits** — Number inputs for:
   - Max Daily Loss ($)
   - Max Trades Per Day
   - Max Concurrent Positions

4. **Exit Rules** — Number inputs for:
   - Default Take Profit %
   - Default Stop Loss %
   - Trailing Stop toggle + %
   - Close All Before Market Close toggle

5. **Signal Filters** —
   - Min Confidence slider (0-100)
   - Require AI Analysis toggle
   - Min AI Conviction (1-10)
   - Strategy checkboxes

6. **Circuit Breakers** — Number inputs for warn/pause/halt percentages

7. **Options Settings** — Max spread %, min OI, min delta

### File: `frontend/src/api/bot.js` (NEW)
API client for all bot endpoints.

### File: `frontend/src/stores/botStore.js` (NEW)
Zustand store for:
- `botConfig` — loaded from API
- `botStatus` — polled every 10 seconds when bot is running
- `todayStats` — daily P&L, trade count
- Actions: `startBot()`, `stopBot()`, `pauseBot()`, `emergencyStop()`, `updateConfig()`

### Verification
- Navigate to Settings → Auto Trading tab renders all controls
- Change execution mode → save → reload → persisted
- Change max_per_stock_trade → save → API confirms update

---

## Phase 12: Frontend — Bot Status Bar + Semi-Auto + Trade Journal

### File: `frontend/src/components/BotStatusBar.jsx` (NEW)
Persistent bar at top of layout (below nav) when bot is running:
- Status indicator: 🟢 Running / 🟡 Paused / 🔴 Halted / ⚪ Stopped
- Daily P&L: +$45.20 (green) or -$23.10 (red)
- Open positions count: "3 positions"
- Circuit breaker: "OK" or "⚠️ Warning" or "🛑 Paused"
- Kill Switch button (red, right-aligned)

### File: `frontend/src/pages/Signals.jsx` (MODIFY)
When execution_mode == "semi_auto":
- Signal cards show "Approve" (green) + "Reject" (red) buttons instead of "Trade"
- Approve calls `POST /api/v1/trading/bot/approve/{signal_id}`
- After approval: show order result inline

### File: `frontend/src/pages/TradeJournal.jsx` (NEW page) or tab in existing page
- Table: Symbol, Direction, Asset Type, Entry Price, Exit Price, P&L ($), P&L (%), Exit Reason, Duration, Date
- Filters: date range, symbol, status (open/closed), exit reason
- Color coding: green rows for wins, red for losses
- Summary cards at top: Total P&L, Win Rate, Best Trade, Worst Trade

### Route: Add `/trade-journal` to `App.jsx`

### Verification
- Start bot → BotStatusBar appears across all pages
- Semi-auto: signal appears → click Approve → trade executes → journal entry appears
- Trade Journal page: shows all executed trades with P&L

---

## Phase 13: Frontend — Performance Dashboard + Kill Switch

### File: `frontend/src/components/BotPerformance.jsx` (NEW)
- Equity curve chart (line chart over time)
- Win rate by strategy (bar chart)
- P&L by day (bar chart, green/red)
- Stats cards: Sharpe Ratio, Max Drawdown, Avg Hold Time, Total Trades

### Kill Switch Enhancement
- BotStatusBar kill switch button → confirmation modal:
  - "Cancel all open orders?" [Yes/No]
  - "Also close all positions?" [Yes/No]
  - Red styling, clear warning text
- POST `/emergency-stop` with `close_positions` flag

### Verification
- Performance dashboard loads with chart data
- Kill switch: click → confirm → all orders cancelled → positions closed → bot stopped

---

## Implementation Order Summary

| Phase | What | Files | Dependencies |
|-------|------|-------|-------------|
| 1 | Database models | 4 new model files + __init__.py | None |
| 2 | Enhanced trading service | Modify alpaca_trading_service.py | Phase 1 |
| 3 | Risk Gateway | 1 new service file | Phase 1 |
| 4 | Position Sizer | 1 new service file | Phase 1 |
| 5 | Order Executor | 1 new service file | Phase 2 |
| 6 | Position Monitor | 1 new service file | Phase 1, 5 |
| 7 | Trade Journal | 1 new service file | Phase 1 |
| 8 | Auto-Trader orchestrator | 1 new service file + modify main.py | Phase 3-7 |
| 9 | API endpoints | 1 new endpoint file + register in main.py | Phase 8 |
| 10 | Scheduler integration | Modify main.py | Phase 8 |
| 11 | Frontend Settings tab | 3 new files + modify Settings.jsx | Phase 9 |
| 12 | Frontend Status Bar + Journal | 3-4 new files + modify Signals.jsx, App.jsx | Phase 9, 11 |
| 13 | Frontend Performance + Kill Switch | 1-2 new files | Phase 12 |

**Total: ~15 new files, ~5 modified files, 13 testable phases**

Each phase is independently testable and deployable. We build bottom-up: models → services → API → frontend. At every phase, the existing system continues to work unchanged.
