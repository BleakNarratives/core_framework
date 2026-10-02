#!/usr/bin/env python3
"""Deterministic tests for the sprawl scanner (temp tree, no external I/O)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_framework.bin.sprawl_scan import (  # noqa: E402
    apply_consolidation,
    family_verdict,
    plan_consolidation,
    render_consolidation,
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


def _docs_named(root: Path, name: str):
    return [e for e in scan(root, depth=5) if e.basename == name]


def test_family_verdict_classifies_mirror_config_snapshot(tmp_path):
    # 3-project mirror
    for proj in ("a", "b", "c"):
        _write(tmp_path / proj / "ROADMAP.md", "# same\n- [ ] x\n")
    assert family_verdict(_docs_named(tmp_path, "roadmap.md"))[0] == "MIRROR"

    # agent/tool config dir
    _write(tmp_path / ".claude" / "MEMORY-OPTIMIZATION.md", "# same\nbody\n")
    _write(tmp_path / ".codex" / "MEMORY-OPTIMIZATION.md", "# same\nbody\n")
    assert family_verdict(_docs_named(tmp_path, "memory-optimization.md"))[0] == "CONFIG"

    # point-in-time workspace snapshot
    _write(tmp_path / "iWarship" / "docs" / "WHITE_PAPER_INTRO.md", "# same\nbody\n")
    _write(tmp_path / "iWarship" / ".dev-cockpit" / "workspaces" / "dc1" / "docs" / "WHITE_PAPER_INTRO.md",
           "# same\nbody\n")
    assert family_verdict(_docs_named(tmp_path, "white_paper_intro.md"))[0] == "SNAPSHOT"


def test_family_verdict_safe_for_root_stray(tmp_path):
    _write(tmp_path / "A9_RESCUE_PLAN.md", "# same\nbody\n")
    _write(tmp_path / "tools" / "rescue" / "A9_RESCUE_PLAN.md", "# same\nbody\n")
    verdict, _ = family_verdict(_docs_named(tmp_path, "a9_rescue_plan.md"))
    assert verdict == "SAFE"


def test_plan_consolidation_skips_divergent_and_picks_non_stray(tmp_path):
    _write(tmp_path / "A9_RESCUE_PLAN.md", "# same\nbody\n")
    _write(tmp_path / "tools" / "rescue" / "A9_RESCUE_PLAN.md", "# same\nbody\n")
    _write(tmp_path / "p1" / "QRD.md", "# one\n")
    _write(tmp_path / "p2" / "QRD.md", "# two\n")  # divergent
    plan = plan_consolidation(scan(tmp_path, depth=5))
    names = {row["name"] for row in plan}
    assert "qrd.md" not in names            # divergent never in scope
    row = next(r for r in plan if r["name"] == "a9_rescue_plan.md")
    assert row["verdict"] == "SAFE"
    assert row["canonical"] == "tools/rescue/A9_RESCUE_PLAN.md"


def test_apply_consolidation_backs_up_and_writes_pointer(tmp_path):
    original = "# Canonical body\n- [ ] keep me\n"
    _write(tmp_path / "A9_RESCUE_PLAN.md", original)
    _write(tmp_path / "tools" / "rescue" / "A9_RESCUE_PLAN.md", original)
    backup = tmp_path / "backup"
    actions, backup_root = apply_consolidation(
        plan_consolidation(scan(tmp_path, depth=5)), tmp_path, backup_dir=backup, stamp="t",
    )
    assert actions == ["A9_RESCUE_PLAN.md -> tools/rescue/A9_RESCUE_PLAN.md"]
    assert backup_root == backup
    assert (backup / "A9_RESCUE_PLAN.md").read_text() == original   # original preserved
    stub = (tmp_path / "A9_RESCUE_PLAN.md").read_text()
    assert "tools/rescue/A9_RESCUE_PLAN.md" in stub                # pointer to canonical
    # Canonical is untouched.
    assert (tmp_path / "tools" / "rescue" / "A9_RESCUE_PLAN.md").read_text() == original


def test_apply_consolidation_ignores_non_safe(tmp_path):
    for proj in ("a", "b", "c"):
        _write(tmp_path / proj / "ROADMAP.md", "# same\n- [ ] x\n")
    before = {p: (tmp_path / p / "ROADMAP.md").read_text() for p in ("a", "b", "c")}
    actions, _ = apply_consolidation(
        plan_consolidation(scan(tmp_path, depth=5)), tmp_path, backup_dir=tmp_path / "bak",
    )
    assert actions == []  # MIRROR is left alone
    for p in ("a", "b", "c"):
        assert (tmp_path / p / "ROADMAP.md").read_text() == before[p]


def test_pointer_stub_is_not_indexed(tmp_path):
    _write(tmp_path / "alpha" / "ROADMAP.md", "# Consolidated duplicate\nbody\n")
    paths = {e.path for e in scan(tmp_path, depth=5)}
    assert "alpha/ROADMAP.md" not in paths


def test_render_consolidation_lists_safe_action(tmp_path):
    _write(tmp_path / "A9_RESCUE_PLAN.md", "# same\nbody\n")
    _write(tmp_path / "tools" / "rescue" / "A9_RESCUE_PLAN.md", "# same\nbody\n")
    md = render_consolidation(plan_consolidation(scan(tmp_path, depth=5)), tmp_path)
    assert "SPRAWL_CONSOLIDATE" in md
    assert "collapse → pointer" in md
    assert "`A9_RESCUE_PLAN.md`" in md
