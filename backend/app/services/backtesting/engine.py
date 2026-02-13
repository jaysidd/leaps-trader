"""
Backtest Engine — orchestrates backtest execution using Backtrader.

Flow:
1. Load config from BacktestResult DB record
2. Fetch historical data via Alpaca
3. Feed into Backtrader Cerebro
4. Run backtest (blocking — called via asyncio.to_thread)
5. Extract results and save back to DB
"""
import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta, timezone
from loguru import logger
from sqlalchemy.orm import Session

from app.models.backtest_result import BacktestResult
from app.services.data_fetcher.alpaca_service import alpaca_service
from app.services.signals.signal_engine import SignalEngine
from app.services.backtesting.strategies import STRATEGY_MAP


class BacktestEngine:
    """Orchestrates Backtrader-powered backtests."""

    def run_backtest(self, backtest_id: int, db: Session):
        """
        Main entry point — runs a backtest synchronously.
        Designed to be called via asyncio.to_thread() from async endpoint.
        """
        bt_record = db.query(BacktestResult).filter(BacktestResult.id == backtest_id).first()
        if not bt_record:
            logger.error(f"Backtest {backtest_id} not found")
            return

        try:
            # Mark as running
            bt_record.status = "running"
            db.commit()

            # Validate strategy
            if bt_record.strategy not in STRATEGY_MAP:
                raise ValueError(f"Unknown strategy: {bt_record.strategy}")

            # Fetch historical data
            df = self._fetch_data(
                symbol=bt_record.symbol,
                timeframe=bt_record.timeframe,
                start_date=bt_record.start_date,
                end_date=bt_record.end_date,
            )
            if df is None or df.empty or len(df) < 50:
                raise ValueError(
                    f"Insufficient data for {bt_record.symbol} "
                    f"({len(df) if df is not None else 0} bars, need 50+)"
                )

            logger.info(
                f"Backtest {backtest_id}: {bt_record.symbol} {bt_record.strategy} "
                f"{bt_record.timeframe} — {len(df)} bars loaded"
            )

            # Build feed
            feed = self._build_feed(df)

            # Get strategy params from SignalEngine (stay in sync)
            strategy_params = self._get_strategy_params(
                bt_record.strategy, bt_record.cap_size, bt_record.timeframe
            )
            strategy_params["position_size_pct"] = bt_record.position_size_pct

            # Configure and run cerebro
            cerebro = self._configure_cerebro(
                strategy_name=bt_record.strategy,
                params=strategy_params,
                capital=bt_record.initial_capital,
                feed=feed,
            )

            results = cerebro.run()
            strat = results[0]

            # Extract results
            metrics = self._extract_results(cerebro, strat, bt_record.initial_capital)

            # Save results
            bt_record.status = "completed"
            bt_record.final_value = metrics["final_value"]
            bt_record.total_return_pct = metrics["total_return_pct"]
            bt_record.sharpe_ratio = metrics["sharpe_ratio"]
            bt_record.max_drawdown_pct = metrics["max_drawdown_pct"]
            bt_record.win_rate = metrics["win_rate"]
            bt_record.profit_factor = metrics["profit_factor"]
            bt_record.total_trades = metrics["total_trades"]
            bt_record.winning_trades = metrics["winning_trades"]
            bt_record.losing_trades = metrics["losing_trades"]
            bt_record.avg_win_pct = metrics["avg_win_pct"]
            bt_record.avg_loss_pct = metrics["avg_loss_pct"]
            bt_record.best_trade_pct = metrics["best_trade_pct"]
            bt_record.worst_trade_pct = metrics["worst_trade_pct"]
            bt_record.avg_trade_duration = metrics["avg_trade_duration"]
            bt_record.equity_curve = metrics["equity_curve"]
            bt_record.trade_log = metrics["trade_log"]
            bt_record.parameters = strategy_params
            bt_record.completed_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(
                f"Backtest {backtest_id} completed: "
                f"return={metrics['total_return_pct']:.2f}%, "
                f"trades={metrics['total_trades']}, "
                f"sharpe={metrics['sharpe_ratio']}"
            )

        except Exception as e:
            logger.error(f"Backtest {backtest_id} failed: {e}")
            bt_record.status = "failed"
            bt_record.error_message = str(e)
            bt_record.completed_at = datetime.now(timezone.utc)
            db.commit()

    # ─────────────────────────────────────────────────────────────────────
    # Data Fetching
    # ─────────────────────────────────────────────────────────────────────

    def _fetch_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """
        Fetch historical bars from Alpaca.
        Returns DataFrame with OHLCV + indicators.
        """
        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

        # Use a large limit to fetch all bars in the date range
        # For 5m bars over 6 months ≈ 10,000 bars; 10000 is Alpaca's max per request
        df = alpaca_service.get_bars(
            symbol=symbol,
            timeframe=timeframe,
            start=start_dt,
            end=end_dt,
            limit=10000,
        )

        if df is not None and not df.empty:
            # Calculate indicators (EMA8, EMA21, RSI14, ATR14, vol_ma20)
            df = alpaca_service.calculate_indicators(df)

        return df

    # ─────────────────────────────────────────────────────────────────────
    # Feed Construction
    # ─────────────────────────────────────────────────────────────────────

    def _build_feed(self, df: pd.DataFrame) -> bt.feeds.PandasData:
        """Convert DataFrame to Backtrader PandasData feed."""
        # alpaca_service.get_bars() returns a 'datetime' column, not as index
        # Set it as the index for Backtrader
        if "datetime" in df.columns:
            df = df.set_index("datetime")

        # Remove timezone info (Backtrader doesn't handle tz-aware datetimes)
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_convert("America/New_York").tz_localize(None)

        # Ensure index is DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # Drop non-OHLCV columns that Backtrader doesn't need
        # (indicators are already calculated and available via column access if needed)
        keep_cols = ["open", "high", "low", "close", "volume"]
        extra_cols = [c for c in df.columns if c not in keep_cols]

        # Backtrader PandasData expects specific column names
        feed = bt.feeds.PandasData(
            dataname=df[keep_cols],
            datetime=None,  # Use index
            open="open",
            high="high",
            low="low",
            close="close",
            volume="volume",
            openinterest=-1,
        )
        return feed

    # ─────────────────────────────────────────────────────────────────────
    # Strategy Params
    # ─────────────────────────────────────────────────────────────────────

    def _get_strategy_params(
        self, strategy_name: str, cap_size: str, timeframe: str
    ) -> dict:
        """
        Load strategy parameters from SignalEngine.PARAMS.
        Falls back to reasonable defaults if not found.
        """
        try:
            params = SignalEngine.PARAMS.get(cap_size, {}).get(timeframe, {})
            if params:
                return dict(params)  # Copy
        except Exception as e:
            logger.warning(f"Could not load params for {cap_size}/{timeframe}: {e}")

        # Defaults
        return {
            "stop_atr_mult": 0.5,
            "rsi_long_min": 50,
            "rsi_short_max": 50,
            "min_atr_percent": 0.15,
            "max_atr_percent": 2.0,
            "min_rvol": 0.8,
            "volume_spike_mult": 1.2,
            "min_confidence": 60,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Cerebro Configuration
    # ─────────────────────────────────────────────────────────────────────

    def _configure_cerebro(
        self, strategy_name: str, params: dict, capital: float, feed
    ) -> bt.Cerebro:
        """Set up Cerebro engine with strategy, analyzers, and broker."""
        cerebro = bt.Cerebro()
        cerebro.adddata(feed)

        # Add strategy with parameters
        strategy_cls = STRATEGY_MAP[strategy_name]
        # Filter params to only those the strategy accepts
        valid_params = {k: v for k, v in params.items() if k in strategy_cls.params._getkeys()}
        cerebro.addstrategy(strategy_cls, **valid_params)

        # Broker settings
        cerebro.broker.setcash(capital)
        cerebro.broker.setcommission(commission=0.0)  # Alpaca is commission-free

        # Analyzers
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.05)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
        cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
        cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")

        return cerebro

    # ─────────────────────────────────────────────────────────────────────
    # Results Extraction
    # ─────────────────────────────────────────────────────────────────────

    def _extract_results(self, cerebro, strategy, initial_capital: float) -> dict:
        """Extract performance metrics from completed backtest."""

        final_value = cerebro.broker.getvalue()
        total_return_pct = ((final_value - initial_capital) / initial_capital) * 100

        # ── Sharpe Ratio ──────────────────────────────────────────────
        sharpe = strategy.analyzers.sharpe.get_analysis()
        sharpe_ratio = sharpe.get("sharperatio")
        if sharpe_ratio is None or (isinstance(sharpe_ratio, float) and np.isnan(sharpe_ratio)):
            sharpe_ratio = 0.0
        else:
            sharpe_ratio = round(float(sharpe_ratio), 3)

        # ── Drawdown ──────────────────────────────────────────────────
        dd = strategy.analyzers.drawdown.get_analysis()
        max_drawdown_pct = round(dd.get("max", {}).get("drawdown", 0.0), 2)

        # ── Trade Analyzer ────────────────────────────────────────────
        ta = strategy.analyzers.trades.get_analysis()
        total_trades = ta.get("total", {}).get("total", 0)
        won_trades = ta.get("won", {}).get("total", 0)
        lost_trades = ta.get("lost", {}).get("total", 0)

        win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0.0

        # Profit factor
        gross_profit = ta.get("won", {}).get("pnl", {}).get("total", 0.0)
        gross_loss = abs(ta.get("lost", {}).get("pnl", {}).get("total", 0.0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
            float("inf") if gross_profit > 0 else 0.0
        )
        if profit_factor == float("inf"):
            profit_factor = 99.99  # Cap for display

        # Average win/loss %
        avg_win_pct = 0.0
        avg_loss_pct = 0.0
        if won_trades > 0 and initial_capital > 0:
            avg_win_pct = (gross_profit / won_trades / initial_capital) * 100
        if lost_trades > 0 and initial_capital > 0:
            avg_loss_pct = (gross_loss / lost_trades / initial_capital) * 100

        # Best/worst trade %
        best_trade_pct = 0.0
        worst_trade_pct = 0.0
        trade_log = strategy.trade_log or []
        if trade_log:
            pnl_pcts = [t.get("pnl_pct", 0) for t in trade_log]
            best_trade_pct = max(pnl_pcts) if pnl_pcts else 0.0
            worst_trade_pct = min(pnl_pcts) if pnl_pcts else 0.0

        # Average trade duration
        avg_bars = 0
        if trade_log:
            bars_list = [t.get("bars_held", 0) for t in trade_log]
            avg_bars = sum(bars_list) / len(bars_list) if bars_list else 0
        avg_trade_duration = f"{int(avg_bars)} bars" if avg_bars > 0 else "N/A"

        # ── Equity Curve ──────────────────────────────────────────────
        equity_curve = strategy.equity_curve or []
        # Downsample if too many points (keep max 500 for frontend)
        if len(equity_curve) > 500:
            step = len(equity_curve) // 500
            equity_curve = equity_curve[::step]

        return {
            "final_value": round(final_value, 2),
            "total_return_pct": round(total_return_pct, 2),
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown_pct": max_drawdown_pct,
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "total_trades": total_trades,
            "winning_trades": won_trades,
            "losing_trades": lost_trades,
            "avg_win_pct": round(avg_win_pct, 2),
            "avg_loss_pct": round(avg_loss_pct, 2),
            "best_trade_pct": round(best_trade_pct, 2),
            "worst_trade_pct": round(worst_trade_pct, 2),
            "avg_trade_duration": avg_trade_duration,
            "equity_curve": equity_curve,
            "trade_log": trade_log,
        }


# Singleton instance
backtest_engine = BacktestEngine()
