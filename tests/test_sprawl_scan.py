#!/usr/bin/env python3
"""Deterministic tests for the sprawl scanner (temp tree, no external I/O)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_framework.bin.sprawl_scan import (  # noqa: E402
    render_markdown,
    render_triage,
    scan,
    summarize,
)


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _tree(tmp_path: Path) -> Path:
    _write(tmp_path / "alpha" / "ROADMAP.md",
           "# Alpha roadmap\n- [ ] task one\n- [ ] task two\n- [x] done one\n")
    _write(tmp_path / "alpha" / "sub" / "QRD.md", "# QRD\n- [ ] qrd task\n")
    _write(tmp_path / "beta" / "HANDOFF_2026.md", "# Handoff\nno checkboxes here\n")
    _write(tmp_path / "beta" / "notes.md", "# Notes\n- [ ] ignored, not a target\n")
    # Must be pruned:
    _write(tmp_path / "node_modules" / "ROADMAP.md", "# dep\n- [ ] should not appear\n")
    _write(tmp_path / ".git" / "ROADMAP.md", "# git\n- [ ] should not appear\n")
    return tmp_path


def test_scan_finds_targets_and_prunes(tmp_path):
    root = _tree(tmp_path)
    entries = scan(root, depth=5)
    paths = {e.path for e in entries}
    assert "alpha/ROADMAP.md" in paths
    assert "alpha/sub/QRD.md" in paths
    assert "beta/HANDOFF_2026.md" in paths
    assert "beta/notes.md" not in paths
    assert not any("node_modules" in p for p in paths)
    assert not any(p.startswith(".git") for p in paths)


def test_open_and_done_counts(tmp_path):
    root = _tree(tmp_path)
    entries = {e.path: e for e in scan(root, depth=5)}
    roadmap = entries["alpha/ROADMAP.md"]
    assert roadmap.open_count == 2
    assert roadmap.done_count == 1
    assert roadmap.title == "Alpha roadmap"
    assert roadmap.project == "alpha"


def test_summarize(tmp_path):
    root = _tree(tmp_path)
    totals = summarize(scan(root, depth=5))
    assert totals["docs"] == 3
    assert totals["open_tasks"] == 3
    assert totals["done_tasks"] == 1
    assert totals["projects"] == 2


def test_render_markdown_contains_open_tasks(tmp_path):
    root = _tree(tmp_path)
    md = render_markdown(scan(root, depth=5), root)
    assert "SPRAWL_INDEX" in md
    assert "task one" in md
    assert "| `alpha` |" in md


def test_depth_limit(tmp_path):
    root = _tree(tmp_path)
    entries = scan(root, depth=1)
    paths = {e.path for e in entries}
    assert "alpha/ROADMAP.md" in paths
    assert "alpha/sub/QRD.md" not in paths  # deeper than depth 1 from root


def test_category_classification(tmp_path):
    root = _tree(tmp_path)
    cats = {e.path: e.category for e in scan(root, depth=5)}
    assert cats["alpha/ROADMAP.md"] == "plan"
    assert cats["alpha/sub/QRD.md"] == "record"
    assert cats["beta/HANDOFF_2026.md"] == "handoff"


def test_triage_flags_duplicates_and_incomplete(tmp_path):
    root = tmp_path
    _write(root / "p1" / "ROADMAP.md", "# one\n- [ ] task\n")
    _write(root / "p2" / "ROADMAP.md", "# two\n- [x] done\n")      # divergent
    _write(root / "p1" / "QRD.md", "# same\nbody\n")
    _write(root / "p2" / "QRD.md", "# same\nbody\n")               # identical
    _write(root / "p1" / "WHITE_PAPER.md", "# Draft\nThis is a TODO stub draft.\n")
    entries = scan(root, depth=5)
    md = render_triage(entries, root, stale_days=0, incomplete_words=800)
    assert "SPRAWL_TRIAGE" in md
    assert "`roadmap.md`" in md            # duplicate family
    assert "DIVERGENT" in md               # roadmap copies differ
    assert "identical" in md               # qrd copies match
    assert "p1/WHITE_PAPER.md" in md       # incomplete worklist
    assert "Standing actions" in md
