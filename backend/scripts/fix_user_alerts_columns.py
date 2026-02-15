"""
Add missing columns to user_alerts table.

The SQLAlchemy model (app/models/user_alert.py) defines these columns but
Base.metadata.create_all() does not ALTER existing tables.  This script
adds the columns manually so the alert_checker job stops erroring.

Columns added:
  - alert_scope:      VARCHAR(20) DEFAULT 'ticker'
  - alert_params:     JSON
  - severity:         VARCHAR(20) DEFAULT 'warning'
  - cooldown_minutes: INTEGER DEFAULT 60
  - dedupe_key:       VARCHAR(255)
  - last_dedupe_at:   TIMESTAMPTZ

Usage:
  cd backend
  source venv/bin/activate
  python3 scripts/fix_user_alerts_columns.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from app.database import SessionLocal


COLUMNS = [
    ("alert_scope",      "VARCHAR(20) DEFAULT 'ticker'"),
    ("alert_params",     "JSON"),
    ("severity",         "VARCHAR(20) DEFAULT 'warning'"),
    ("cooldown_minutes", "INTEGER DEFAULT 60"),
    ("dedupe_key",       "VARCHAR(255)"),
    ("last_dedupe_at",   "TIMESTAMPTZ"),
]


def migrate():
    db = SessionLocal()
    added = 0
    skipped = 0
    try:
        for col, col_type in COLUMNS:
            try:
                db.execute(text(
                    f"ALTER TABLE user_alerts ADD COLUMN {col} {col_type}"
                ))
                db.commit()
                print(f"  ✅ Added user_alerts.{col}")
                added += 1
            except Exception as e:
                db.rollback()
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print(f"  ⏭️  user_alerts.{col} already exists, skipping")
                    skipped += 1
                else:
                    raise

        print(f"\nMigration complete. Added: {added}, Skipped (already exist): {skipped}")
    except Exception as e:
        db.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
