"""
Data migration: Convert existing 4h queue items to 1h.
Historical trading signals with timeframe=4h are left untouched.

Usage:
  cd backend
  source ../venv/bin/activate
  python3 scripts/migrate_4h_to_1h.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.models.signal_queue import SignalQueue

def migrate():
    db = SessionLocal()
    try:
        items = db.query(SignalQueue).filter(SignalQueue.timeframe == "4h").all()
        count = len(items)
        if count == 0:
            print("No 4h queue items found. Nothing to migrate.")
            return

        for item in items:
            item.timeframe = "1h"

        db.commit()
        print(f"Migrated {count} queue item(s) from 4h -> 1h.")
    except Exception as e:
        db.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
