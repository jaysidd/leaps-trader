"""
Root conftest for backend tests.

Adds both the backend directory and its parent to sys.path so tests
can use either import style:
  - ``from app.services...``  (preferred, for tests run from backend/)
  - ``from backend.app.services...``  (legacy, for tests run from project root)
"""
import sys
from pathlib import Path

# backend/ directory  (supports `from app.services...`)
backend_dir = str(Path(__file__).resolve().parents[1])
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# project root  (supports `from backend.app.services...`)
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)
