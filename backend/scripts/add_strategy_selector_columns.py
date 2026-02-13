"""
Add multi-strategy pipeline columns to signal_queues and trading_signals tables.

signal_queues:
  - confidence_level: VARCHAR(10) — HIGH/MEDIUM/LOW
  - strategy_reasoning: TEXT — why this timeframe was selected

trading_signals:
  - validation_status: VARCHAR(20) — validated/rejected/pending_validation
  - validation_reasoning: TEXT — AI reasoning for go/no-go
  - validated_at: TIMESTAMPTZ — when validation occurred

Usage:
  cd backend
  source ../venv/bin/activate
  python3 scripts/add_strategy_selector_columns.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from app.database import SessionLocal


def migrate():
    db = SessionLocal()
    try:
        # signal_queues: confidence_level + strategy_reasoning
        for col, col_type in [
            ("confidence_level", "VARCHAR(10)"),
            ("strategy_reasoning", "TEXT"),
        ]:
            try:
                db.execute(text(
                    f"ALTER TABLE signal_queues ADD COLUMN {col} {col_type}"
                ))
                db.commit()
                print(f"  Added signal_queues.{col}")
            except Exception as e:
                db.rollback()
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print(f"  signal_queues.{col} already exists, skipping")
                else:
                    raise

        # trading_signals: validation_status + validation_reasoning + validated_at
        for col, col_type in [
            ("validation_status", "VARCHAR(20)"),
            ("validation_reasoning", "TEXT"),
            ("validated_at", "TIMESTAMPTZ"),
        ]:
            try:
                db.execute(text(
                    f"ALTER TABLE trading_signals ADD COLUMN {col} {col_type}"
                ))
                db.commit()
                print(f"  Added trading_signals.{col}")
            except Exception as e:
                db.rollback()
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print(f"  trading_signals.{col} already exists, skipping")
                else:
                    raise

        print("Migration complete.")
    except Exception as e:
        db.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
