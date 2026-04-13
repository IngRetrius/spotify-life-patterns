"""
Pytest configuration.

Adds the project root to sys.path so tests can import `transformation.*`
and `ingestion.*` without requiring the package to be installed.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
