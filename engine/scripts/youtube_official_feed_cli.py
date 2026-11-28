#!/usr/bin/env python3
"""Operator entry for the YouTube official-feed shadow adapter."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from youtube_official_feed.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
