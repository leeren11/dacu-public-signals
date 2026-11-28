#!/usr/bin/env python3
"""Operator entry for the independent evidence_research_v2 shadow layer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_v2.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
