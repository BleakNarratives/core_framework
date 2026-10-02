#!/usr/bin/env python3
"""
core_framework/bin/sprawl_scan.py

Canonical sprawl scanner + triage planner. Walks a repo tree, finds every
roadmap / handoff / QRD / MRD / STANK / white-paper / compilation-style markdown
doc, extracts open checklist items, classifies each doc, and writes TWO files so
the pile is legible without opening hundreds of documents:

  <root>/SPRAWL_INDEX.md   — the map (totals, per-project, every open task)
  <root>/SPRAWL_TRIAGE.md  — the plan (duplicates, stale, incomplete work, queue)

Read-only: it never edits or moves the docs it scans. The only writes are the
two generated files. Regenerate any time.

Usage:
    python3 -m core_framework.bin.sprawl_scan
    python3 -m core_framework.bin.sprawl_scan --json
    python3 -m core_framework.bin.sprawl_scan --root . --no-triage
    python3 -m core_framework.bin.sprawl_scan --stale-days 30 --max-per-doc 25
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable, List

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = FRAMEWORK_ROOT.parent

# Directories that never hold source docs worth indexing.
PRUNE_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".cache", ".npm", ".rustup", ".cargo", "site-packages", ".mypy_cache",
    ".pytest_cache", ".next", "dist", "build", "target", ".tox",
    ".terraform", ".gradle", ".idea", ".vs", "models",
}


def _prune_dir(name: str) -> bool:
    return (
        name in PRUNE_DIRS
        or name.startswith(".git")
        or name.endswith("-env")
        or name.endswith("_env")
        or "site-packages" in name
    )

# Filename globs (lowercase, basename match).
NAME_PATTERNS = (
    "roadmap*.md", "*_roadmap.md", "*handoff*.md", "session*.md",
    "qrd*.md", "mrd*.md", "todo*.md", "*_todo.md", "backlog*.md",
    "*_plan.md", "plan*.md", "*plan*.md",
    "stank.md", "who_did_what.md", "curator.md", "mentor.md", "memo*.md",
    "*white*paper*.md", "*whitepaper*.md", "*meatsuit*.md",
    "*model_collab*.md", "*collab*.md", "decision_log*.md",
    "agents.md", "soul.md", "user.md",
)

CATEGORY_RULES = (
    ("whitepaper", ("white paper", "white_paper", "whitepaper", "meatsuit", "collab")),
    ("ledger", ("stank", "who_did_what", "curator", "mentor")),
    ("handoff", ("handoff", "session", "decision_log")),
    ("record", ("qrd", "mrd")),
    ("todo", ("todo", "backlog")),
    ("plan", ("roadmap", "plan")),
    ("policy", ("agents", "soul", "user")),
    ("misc", ()),
)

OPEN_RE = re.compile(r"^\s*[-*]\s*\[ \]\s*(.+?)\s*$")
DONE_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*(.+?)\s*$")
TITLE_RE = re.compile(r"^\s*#\s+(.+?)\s*$")
INCOMPLETE_RE = re.compile(
    r"\b(todo|tbd|fixme|xxx|stub|draft|unfinished|placeholder|coming soon|wip)\b",
    re.IGNORECASE,
)

# Pointer stubs written by `apply_consolidation` are markers, not documents:
# skip them so a resolved duplicate family stops appearing in the index/worklist.
POINTER_MARKER = "# Consolidated duplicate"

MAX_READ_BYTES = 400_000
DEFAULT_STALE_DAYS = 30
DEFAULT_INCOMPLETE_WORDS = 800

# Path fragments that mark museum / backup / recovery trees. Most duplicate doc
# families live here; separating them makes the active work surface realistic.
BACKUP_MARKERS = ("archive", "graveyard", "unpacked", "recovery", "backup", "dump", "_incoming")

# Consolidation-planner classification. Byte-identical is necessary but not
# sufficient for a safe collapse: mirrors, agent-tool config, and workspace
# snapshots are identical on purpose.
AGENT_CONFIG_DIRS = {
    ".claude", ".codex", ".gemini", ".hermes", ".junie", ".openhands",
    ".vscode", ".config", ".codebuddy", ".grok",
}
SNAPSHOT_MARKERS = ("dev-cockpit", "workspaces", "snapshot", "backup", "archive")
SUSPECT_PATH_PARTS = {"~"}


@dataclass
class DocEntry:
    path: str
    project: str
    category: str
    title: str
    mtime: str
    age_days: int
    words: int
    incomplete_markers: int
    content_hash: str = ""
    backup: bool = False
    open_tasks: List[str] = field(default_factory=list)
    done_count: int = 0

    @property
    def open_count(self) -> int:
        return len(self.open_tasks)

    @property
    def basename(self) -> str:
        return Path(self.path).name.lower()

    @property
    def stem(self) -> str:
        return Path(self.path).stem.lower()


def _is_target(name: str) -> bool:
    lowered = name.lower()
    return any(fnmatch(lowered, pattern) for pattern in NAME_PATTERNS)


def _classify(name: str) -> str:
    lowered = name.lower()
    for category, needles in CATEGORY_RULES:
        if any(n in lowered for n in needles):
            return category
    return "misc"


def _is_backup(rel: Path) -> bool:
    parts = [p.lower() for p in rel.parts[:-1]]  # exclude the filename itself
    return any(any(marker in part for marker in BACKUP_MARKERS) for part in parts)


def _project_of(rel: Path) -> str:
    parts = rel.parts
    if len(parts) <= 1:
        return "(root)"
    return parts[0]


def _parse_doc(path: Path, root: Path, now: float) -> DocEntry | None:
    try:
        raw = path.read_bytes()[:MAX_READ_BYTES]
        text = raw.decode("utf-8", errors="replace")
        stat = path.stat()
    except OSError:
        return None

    if text.lstrip().startswith(POINTER_MARKER):
        return None

    title = ""
    open_tasks: List[str] = []
    done = 0
    for line in text.splitlines():
        if not title:
            m = TITLE_RE.match(line)
            if m:
                title = m.group(1)
        m_open = OPEN_RE.match(line)
        if m_open:
            task = m_open.group(1).strip()
            if task and not task.startswith("~~"):
                open_tasks.append(task)
            continue
        if DONE_RE.match(line):
            done += 1

    rel = path.relative_to(root)
    return DocEntry(
        path=str(rel),
        project=_project_of(rel),
        category=_classify(path.name),
        title=title or path.name,
        mtime=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
        age_days=int(max(0, (now - stat.st_mtime) // 86400)),
        words=len(text.split()),
        incomplete_markers=len(INCOMPLETE_RE.findall(text)),
        content_hash=hashlib.sha256(raw).hexdigest()[:12],
        backup=_is_backup(rel),
        open_tasks=open_tasks,
        done_count=done,
    )


def scan(root: Path, depth: int = 5) -> List[DocEntry]:
    root = root.resolve()
    root_depth = len(root.parts)
    now = time.time()
    entries: List[DocEntry] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        if len(current.parts) - root_depth >= depth:
            dirnames[:] = []
        else:
            dirnames[:] = sorted(d for d in dirnames if not _prune_dir(d))
        for name in sorted(filenames):
            if _is_target(name):
                entry = _parse_doc(current / name, root, now)
                if entry is not None:
                    entries.append(entry)
    entries.sort(key=lambda e: (e.category, e.project, e.path))
    return entries


def summarize(entries: Iterable[DocEntry]) -> dict:
    entries = list(entries)
    by_category = Counter(e.category for e in entries)
    active = [e for e in entries if not e.backup]
    backup = [e for e in entries if e.backup]
    return {
        "docs": len(entries),
        "open_tasks": sum(e.open_count for e in entries),
        "done_tasks": sum(e.done_count for e in entries),
        "projects": len({e.project for e in entries}),
        "by_category": dict(sorted(by_category.items())),
        "active_docs": len(active),
        "active_open_tasks": sum(e.open_count for e in active),
        "backup_docs": len(backup),
        "backup_open_tasks": sum(e.open_count for e in backup),
    }


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------
def render_markdown(entries: List[DocEntry], root: Path, max_per_doc: int = 25,
                    generated: str | None = None) -> str:
    generated = generated or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    totals = summarize(entries)
    by_project: dict[str, list[DocEntry]] = defaultdict(list)
    for entry in entries:
        by_project[entry.project].append(entry)

    def stats(project: str) -> tuple[int, int, int]:
        docs = by_project[project]
        return len(docs), sum(d.open_count for d in docs), sum(d.done_count for d in docs)

    lines = [
        "# SPRAWL_INDEX.md — the canonical map of the doc pile",
        "",
        "> **This is THE index.** Generated by `core_framework/bin/sprawl_scan.py`; do not hand-edit.",
        f"> Generated: {generated} · root: `{root}`",
        "> Regenerate: `python3 -m core_framework.bin.sprawl_scan`",
        ">",
        "> Companion plan: `SPRAWL_TRIAGE.md`. Read (never moves) every roadmap /",
        "> handoff / QRD / MRD / STANK / white-paper-style doc.",
        "",
        "## Totals",
        "",
        f"- **docs:** {totals['docs']} across {totals['projects']} projects",
        f"- **active docs:** {totals['active_docs']} · **active open tasks:** {totals['active_open_tasks']}",
        f"- **backup/museum docs:** {totals['backup_docs']} · backup open tasks: {totals['backup_open_tasks']}",
        f"- **open tasks (all):** {totals['open_tasks']}",
        f"- **done tasks:** {totals['done_tasks']}",
        f"- **by category:** " + ", ".join(f"{k}={v}" for k, v in totals["by_category"].items()),
        "",
        "## By project (open tasks, descending)",
        "",
        "| project | docs | open | done |",
        "|---|---:|---:|---:|",
    ]
    for project in sorted(by_project, key=lambda p: (-stats(p)[1], p)):
        docs, open_n, done_n = stats(project)
        lines.append(f"| `{project}` | {docs} | {open_n} | {done_n} |")
    lines += ["", "## Open tasks", ""]

    any_open = False
    for project in sorted(by_project, key=lambda p: (-stats(p)[1], p)):
        if stats(project)[1] == 0:
            continue
        any_open = True
        lines += [f"### {project} — {stats(project)[1]} open", ""]
        for entry in sorted(by_project[project], key=lambda e: -e.open_count):
            if entry.open_count == 0:
                continue
            lines.append(
                f"#### `{entry.path}` — {entry.open_count} open, {entry.done_count} done "
                f"({entry.category}, mtime {entry.mtime})"
            )
            if entry.title and entry.title != entry.path:
                lines.append(f"_{entry.title}_")
            shown = entry.open_tasks[:max_per_doc]
            lines += [f"- [ ] {task}" for task in shown]
            if entry.open_count > len(shown):
                lines.append(f"- … +{entry.open_count - len(shown)} more")
            lines.append("")
    if not any_open:
        lines += ["_No open checklist items found._", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Triage plan
# ---------------------------------------------------------------------------
def render_triage(entries: List[DocEntry], root: Path, *, stale_days: int = DEFAULT_STALE_DAYS,
                  incomplete_words: int = DEFAULT_INCOMPLETE_WORDS,
                  generated: str | None = None) -> str:
    generated = generated or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Museum/backup trees are separated first: most duplicate families live there.
    active = [e for e in entries if not e.backup]
    backup = [e for e in entries if e.backup]

    # 1. duplicate families by basename (active only)
    families: dict[str, list[DocEntry]] = defaultdict(list)
    for entry in active:
        families[entry.basename].append(entry)
    dupe_families = {k: v for k, v in families.items() if len(v) > 1}

    # 2. incomplete whitepapers (active only)
    incomplete_wp = [
        e for e in active
        if e.category == "whitepaper"
        and (e.incomplete_markers > 0 or e.words < incomplete_words)
    ]
    incomplete_wp.sort(key=lambda e: (-e.incomplete_markers, e.words))

    # 3. stale (old + nothing open, active only)
    stale = [e for e in active if e.open_count == 0 and e.age_days >= stale_days]
    stale.sort(key=lambda e: -e.age_days)

    # 4. active queue
    queue = [e for e in active if e.open_count > 0]
    queue.sort(key=lambda e: -e.open_count)

    # 5. ledger/category census + backup rollup
    census = Counter(e.category for e in active)
    backup_projects = Counter(e.project for e in backup)

    lines = [
        "# SPRAWL_TRIAGE.md — the plan for the doc pile",
        "",
        "> **Generated plan.** Produced by `core_framework/bin/sprawl_scan.py`;",
        "> regenerate rather than hand-edit. It proposes actions; it never executes them.",
        f"> Generated: {generated} · root: `{root}`",
        "",
        "## How to use this",
        "",
        "Work top-to-bottom. Every bucket here can be cleared without leaving this file.",
        "Nothing is moved or deleted automatically; the commands are listed for you (or a",
        "follow-up agent) to run deliberately.",
        "",
        "## Snapshot",
        "",
        f"- active docs: **{len(active)}** · active categories: "
        + ", ".join(f"{k}={v}" for k, v in sorted(census.items())),
        f"- active docs with open tasks: **{len(queue)}**",
        f"- duplicate filename families (active): **{len(dupe_families)}**",
        f"- incomplete whitepaper/stub docs (active): **{len(incomplete_wp)}**",
        f"- stale candidates (active, no open tasks, ≥{stale_days}d): **{len(stale)}**",
        f"- museum/backup docs skipped from buckets: **{len(backup)}**",
        "",
        "---",
        "",
        "## 0. Museum / backup trees — ignore as a block",
        "",
        "These projects look like archive/recovery/backup copies. Their docs are",
        "excluded from the buckets below so the active surface stays small. Handle",
        "them once, as a set — don't triage them doc-by-doc.",
        "",
    ]
    if backup_projects:
        lines += ["| backup project | docs |", "|---|---:|"]
        for project, count in backup_projects.most_common(40):
            lines.append(f"| `{project}` | {count} |")
        if len(backup_projects) > 40:
            lines.append(f"| … +{len(backup_projects) - 40} more | |")
    else:
        lines.append("_None detected._")
    lines += [
        "",
        "---",
        "",
        "## 1. Duplicate filename families — consolidate (active)",
        "",
        "Same filename across projects is the #1 source of drift. Decide one canonical",
        "copy per family; everything else is a sync target or an archive candidate.",
        "",
    ]
    if dupe_families:
        lines += [
            "**Verdict matters.** `identical` families are pure copy-propagation and can be",
            "collapsed to one canonical copy plus pointers. `DIVERGENT` families share only",
            "the filename — they are different documents and must be left alone (or renamed).",
            "",
            "| filename | copies | distinct contents | verdict | projects |",
            "|---|---:|---:|---|---|",
        ]
        for name, docs in sorted(dupe_families.items(), key=lambda kv: -len(kv[1])):
            distinct = len({d.content_hash for d in docs})
            verdict = "identical" if distinct == 1 else "DIVERGENT"
            projects = ", ".join(sorted({d.project for d in docs})[:8])
            more = "" if len({d.project for d in docs}) <= 8 else " …"
            lines.append(f"| `{name}` | {len(docs)} | {distinct} | {verdict} | {projects}{more} |")
        identical = sum(1 for docs in dupe_families.values() if len({d.content_hash for d in docs}) == 1)
        lines += [
            "",
            f"- collapse-safe (`identical`): **{identical}** families",
            f"- must not be touched (`DIVERGENT`): **{len(dupe_families) - identical}** families",
        ]
    else:
        lines.append("_No duplicate filename families found._")
    lines.append("")

    lines += [
        "---",
        "",
        "## 2. Incomplete whitepapers / drafts — a worklist",
        "",
        f"Flagged when they contain unsure-markers or are under {incomplete_words} words.",
        "",
    ]
    if incomplete_wp:
        lines += ["| doc | words | markers | mtime |", "|---|---:|---:|---|"]
        for e in incomplete_wp:
            lines.append(f"| `{e.path}` | {e.words} | {e.incomplete_markers} | {e.mtime} |")
    else:
        lines.append("_None flagged._")
    lines.append("")

    lines += [
        "---",
        "",
        f"## 3. Stale candidates — archive (age ≥ {stale_days}d, nothing open)",
        "",
        "Suggested (not executed): move to `._archive/sprawl_<date>/` once confirmed.",
        "",
    ]
    if stale:
        lines += ["| doc | age (days) | category |", "|---|---:|---|"]
        for e in stale[:200]:
            lines.append(f"| `{e.path}` | {e.age_days} | {e.category} |")
        if len(stale) > 200:
            lines.append(f"| … +{len(stale) - 200} more | | |")
    else:
        lines.append("_None._")
    lines.append("")

    lines += [
        "---",
        "",
        "## 4. Active queue — docs with open tasks (work these)",
        "",
    ]
    if queue:
        lines += ["| doc | open | done | category |", "|---|---:|---:|---|"]
        for e in queue[:100]:
            lines.append(f"| `{e.path}` | {e.open_count} | {e.done_count} | {e.category} |")
        if len(queue) > 100:
            lines.append(f"| … +{len(queue) - 100} more | | | |")
    else:
        lines.append("_Nothing open._")
    lines.append("")

    lines += [
        "---",
        "",
        "## 5. Ledger sprawl — one ledger per project",
        "",
        "`WHO_DID_WHAT.md` / `STANK.md` / `CURATOR.md` proliferate fastest. Prefer one",
        "canonical ledger per project, appended to (never forked).",
        "",
        "### Standalone ledgers at the repo root",
        "",
        "Consolidation targets to check: do these agree, or has one drifted?",
        "",
    ]
    root_ledgers = sorted(
        e.path for e in entries
        if e.category in {"ledger", "handoff"} and e.project == "(root)"
    )
    lines += [f"- `{p}`" for p in root_ledgers] or ["_None at root._"]
    lines += [
        "",
        "---",
        "",
        "## 6. Standing actions (low effort, keeps this file useful)",
        "",
        "1. Regenerate weekly (or after any big session):",
        "   `python3 -m core_framework.bin.sprawl_scan`",
        "2. Keep ONE canonical index + triage at the repo root; never fork `SPRAWL_*.md`.",
        "3. Collapse only `identical` duplicate families (one canonical copy + pointers).",
        "   Leave `DIVERGENT` families alone — same name, different content.",
        "4. Prefer appending to an existing ledger over creating a new `*_HANDOFF.md`.",
        "",
        "> This plan is advisory. Verify each candidate before moving anything — mtime",
        "> and marker counts are heuristics, not verdicts.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Consolidation planner
#
# "Identical" alone does not make a duplicate family safe to collapse: the
# copies may be deliberate multi-project mirrors, agent-tool config files, or
# point-in-time workspace snapshots. This planner classifies each identical
# family and only proposes a collapse for copies that sit outside the
# canonical tree (strays). Divergent families are never in scope.
# ---------------------------------------------------------------------------
def _is_stray(entry: DocEntry) -> bool:
    """True when a copy sits outside a meaningful project tree.

    Strays are root-level one-off files and path components that are clearly
    accidental (a literal ``~`` directory). These are the copies safe to
    collapse to a pointer because the canonical document lives elsewhere.
    """
    parts = Path(entry.path).parts
    if len(parts) == 1:
        return True
    return any(p in SUSPECT_PATH_PARTS for p in parts[:-1])


def family_verdict(docs: List[DocEntry]) -> tuple[str, str]:
    """Classify an identical duplicate family. Returns ``(verdict, reason)``.

    ``SAFE`` is the only verdict the applier acts on; everything else is left
    for a human because the copies carry different meanings despite equal bytes.
    """
    projects = {d.project for d in docs}
    dirs = [p.lower() for d in docs for p in Path(d.path).parts[:-1]]
    if any(p in AGENT_CONFIG_DIRS for p in dirs):
        return "CONFIG", "agent/tool config directory; tooling reads these"
    if any(marker in p for p in dirs for marker in SNAPSHOT_MARKERS):
        return "SNAPSHOT", "point-in-time workspace/snapshot; leave intact"
    if len(projects) >= 3:
        return "MIRROR", "deliberate multi-project mirror; a sync step re-creates these"
    strays = [d for d in docs if _is_stray(d)]
    if strays and len(strays) < len(docs):
        return "SAFE", "duplicate copy outside the canonical tree"
    return "REVIEW", "cross-project; confirm the canonical owner first"


def _pick_canonical(docs: List[DocEntry]) -> DocEntry:
    pool = [d for d in docs if not _is_stray(d)] or list(docs)
    return sorted(pool, key=lambda d: (len(Path(d.path).parts), d.path))[0]


def plan_consolidation(entries: List[DocEntry]) -> List[dict]:
    """One plan row per identical duplicate family (verdict + canonical + copies)."""
    families: dict[str, list[DocEntry]] = defaultdict(list)
    for entry in entries:
        if not entry.backup:
            families[entry.basename].append(entry)
    plan: List[dict] = []
    for name, docs in sorted(families.items(), key=lambda kv: -len(kv[1])):
        if len(docs) < 2 or len({d.content_hash for d in docs}) != 1:
            continue  # divergent families are explicitly out of scope
        verdict, reason = family_verdict(docs)
        canonical = _pick_canonical(docs)
        plan.append({
            "name": name,
            "verdict": verdict,
            "reason": reason,
            "canonical": canonical.path,
            "copies": sorted(d.path for d in docs),
        })
    return plan


def _pointer_stub(copy_rel: Path, canonical_rel: Path, backup_rel: str) -> str:
    link = os.path.relpath(canonical_rel, copy_rel.parent)
    return (
        "# Consolidated duplicate\n\n"
        "This file was a byte-identical duplicate. The canonical document is:\n\n"
        f"- [`{canonical_rel.as_posix()}`]({link.replace(os.sep, '/')})\n\n"
        "Do not edit this stub; edit the canonical file. The original content was\n"
        f"backed up to `{backup_rel}`.\n"
    )


def render_consolidation(plan: List[dict], root: Path, generated: str | None = None) -> str:
    generated = generated or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    counts = Counter(row["verdict"] for row in plan)
    lines = [
        "# SPRAWL_CONSOLIDATE.md — safe duplicate-collapse plan",
        "",
        "> Generated by `core_framework/bin/sprawl_scan.py`; regenerate, don't hand-edit.",
        f"> Generated: {generated} · root: `{root}`",
        ">",
        "> Only `SAFE` families are collapsed by `--apply`; every other verdict is",
        "> deliberately left for a human. `SAFE` means each extra copy is a stray",
        "> outside the canonical tree — not a mirror, config, or snapshot.",
        "",
        f"- identical families: **{len(plan)}** · "
        + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
        "",
        "| family | verdict | canonical | copies | reason |",
        "|---|---|---|---:|---|",
    ]
    for row in sorted(plan, key=lambda r: (r["verdict"] != "SAFE", r["name"])):
        lines.append(
            f"| `{row['name']}` | {row['verdict']} | `{row['canonical']}` | "
            f"{len(row['copies'])} | {row['reason']} |"
        )
    lines += ["", "## Actions", ""]
    safe = [r for r in plan if r["verdict"] == "SAFE"]
    if not safe:
        lines.append("_No SAFE families — nothing to collapse automatically._")
    for row in safe:
        lines.append(f"### `{row['name']}`")
        lines.append(f"- keep: `{row['canonical']}`")
        for copy in row["copies"]:
            if copy != row["canonical"]:
                lines.append(f"- collapse → pointer: `{copy}`")
        lines.append("")
    return "\n".join(lines)


def apply_consolidation(plan: List[dict], root: Path, backup_dir: str | Path | None = None,
                        stamp: str | None = None) -> tuple[list[str], Path]:
    """Collapse SAFE families: back up each duplicate, then write a pointer stub.

    Only ``SAFE`` rows are touched. Returns ``(actions, backup_root)``.
    """
    root = Path(root).resolve()
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_root = Path(backup_dir).resolve() if backup_dir else (Path.home() / ".sprawl_backup" / stamp)
    actions: list[str] = []
    for row in plan:
        if row["verdict"] != "SAFE":
            continue
        canonical = Path(row["canonical"])
        for copy in row["copies"]:
            if copy == row["canonical"]:
                continue
            src = root / copy
            if not src.exists() or not src.is_file():
                continue
            backup_path = backup_root / copy
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, backup_path)
            src.write_text(_pointer_stub(Path(copy), canonical, str(backup_path)), encoding="utf-8")
            actions.append(f"{copy} -> {row['canonical']}")
    return actions, backup_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sprawl_scan",
        description="Index roadmap/handoff/QRD/MRD/STANK/whitepaper docs and plan triage.",
    )
    parser.add_argument("--root", default=str(REPO_ROOT), help="root to scan")
    parser.add_argument("--depth", type=int, default=5, help="max directory depth")
    parser.add_argument("--out", default=None, help="index path (default <root>/SPRAWL_INDEX.md)")
    parser.add_argument("--triage-out", default=None, help="triage path (default <root>/SPRAWL_TRIAGE.md)")
    parser.add_argument("--no-triage", action="store_true", help="write only the index")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of writing files")
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    parser.add_argument("--incomplete-words", type=int, default=DEFAULT_INCOMPLETE_WORDS)
    parser.add_argument("--max-per-doc", type=int, default=25, help="open tasks shown per doc")
    parser.add_argument("--consolidate", action="store_true",
                        help="write SPRAWL_CONSOLIDATE.md (safe duplicate-collapse plan)")
    parser.add_argument("--apply", action="store_true",
                        help="apply SAFE consolidations (backup + pointer stubs; implies --consolidate)")
    parser.add_argument("--consolidate-out", default=None,
                        help="plan path (default <root>/SPRAWL_CONSOLIDATE.md)")
    parser.add_argument("--backup-dir", default=None,
                        help="backup root for --apply (default ~/.sprawl_backup/<stamp>)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"[sprawl] not a directory: {root}", file=sys.stderr)
        return 2

    entries = scan(root, depth=args.depth)
    totals = summarize(entries)

    if args.json:
        print(json.dumps({"totals": totals, "docs": [asdict(e) for e in entries]}, indent=2))
        return 0

    index_path = Path(args.out) if args.out else (root / "SPRAWL_INDEX.md")
    index_path.write_text(render_markdown(entries, root, max_per_doc=args.max_per_doc))
    print(f"[sprawl] index: {totals['docs']} docs, {totals['open_tasks']} open -> {index_path}")

    if not args.no_triage:
        triage_path = Path(args.triage_out) if args.triage_out else (root / "SPRAWL_TRIAGE.md")
        triage_path.write_text(render_triage(
            entries, root, stale_days=args.stale_days, incomplete_words=args.incomplete_words,
        ))
        print(f"[sprawl] triage -> {triage_path}")

    if args.consolidate or args.apply:
        plan = plan_consolidation(entries)
        plan_path = Path(args.consolidate_out) if args.consolidate_out else (root / "SPRAWL_CONSOLIDATE.md")
        plan_path.write_text(render_consolidation(plan, root))
        safe = [row for row in plan if row["verdict"] == "SAFE"]
        verdicts = Counter(row["verdict"] for row in plan)
        print(
            f"[sprawl] consolidate: {len(plan)} identical families "
            f"({', '.join(f'{k}={v}' for k, v in sorted(verdicts.items()))}) "
            f"· SAFE={len(safe)} -> {plan_path}"
        )
        if args.apply:
            actions, backup_root = apply_consolidation(plan, root, args.backup_dir)
            print(f"[sprawl] applied {len(actions)} collapse(s); backups in {backup_root}")
            for action in actions:
                print(f"[sprawl]   {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
