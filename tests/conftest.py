"""Pytest bootstrap: make the repo root importable before test modules load.

core_framework sits inside the home repo; a few adapters deliberately reuse
outer-repo tooling (for example ``tools.ingest.trend_scraper``). Adding the repo
root here, ahead of collection, keeps that binding working regardless of the
working directory the suite is launched from.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
