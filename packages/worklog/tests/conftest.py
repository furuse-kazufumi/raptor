"""Ensure RAPTOR_DIR is importable so `from packages.worklog import ...` resolves
regardless of how pytest is invoked (per raptor Python-path-safety: only RAPTOR_DIR
is added to sys.path)."""

import sys
from pathlib import Path

RAPTOR_DIR = Path(__file__).resolve().parents[3]
if str(RAPTOR_DIR) not in sys.path:
    sys.path.insert(0, str(RAPTOR_DIR))
