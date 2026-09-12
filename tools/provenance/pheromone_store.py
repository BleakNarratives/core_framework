#!/usr/bin/env python3
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: rootbase-syntax-swarm
# DEPS: datetime,fcntl,hashlib,itertools,json,os,pathlib,sys,time,typing
# ROLE: PheromoneStore v2 (race-safe claims via flock) — promoted from home-dir (1) copy; v1 kept as .bak_v1_20260911
# AUTHOR: Bleak
# SESSION: 2026-09-11
# TIER: 2
# [/DNA_TAG]

"""
pheromone_store.py (v2 — corrected)

Implements pheromone_schema.md. Zero external dependencies — no Redis,
no MCP SDK required to get real value tonight.

v2 fixes, per review:
  - TASK_RELEASE now actually releases (claim state is derived from the
    LATEST task event on a path, not from summing all historical claims).
  - claim_task is now race-safe on a single host via flock — read-check-
    append happens under an exclusive lock, closing the two-agents-both-
    claim window.
  - FILE_MUTATION added to the type enum (was drifting silently).
  - emit() validates type_ against the enum instead of accepting anything.
  - Paths are normalized (resolved, absolute) before keying, so
    "lib/x.py" and "./lib/x.py" collide correctly instead of not.
  - release_task verifies ownership — can't release someone else's claim.
  - IDs include a monotonic counter, not just microsecond timestamp, to
    avoid collisions when multiple events land in the same microsecond.
  - DirectoryWatcher's file extension filter is configurable, not
    hardcoded to .py.

Known remaining limitation, left as-is on purpose: every query is an
O(n) scan of the full log. Fine at tonight's scale. If this store grows
past a few thousand events, add an in-memory index of live claims keyed
by path and tail from the last read offset instead of re-reading
everything — flagged in review, not fixed here because it's premature
optimization at current scale.
"""

import fcntl
import hashlib
import itertools
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STORE_PATH = "pheromones.jsonl"

TYPES = {
    "VALIDATION_PASS",
    "VALIDATION_FAIL",
    "CONTRIBUTION",
    "TASK_CLAIM",
    "TASK_RELEASE",
    "CARD_EMIT",
    "ABSORB_DECISION",
    "FILE_MUTATION",
}

_id_counter = itertools.count()


def _normalize_path(path: str) -> str:
    if not path:
        return path
    return str(Path(path).expanduser().resolve())


class PheromoneStore:
    def __init__(self, store_path: str = STORE_PATH):
        self.store_path = store_path

    def _make_id(self) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        seq = next(_id_counter)
        return f"phm_{ts}_{seq}"

    def emit(
        self,
        type_: str,
        source: str,
        path: str = "",
        strength: float = 1.0,
        decay_rate: float = 0.0,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if type_ not in TYPES:
            raise ValueError(f"Unknown pheromone type: {type_!r}. Must be one of {sorted(TYPES)}")

        event = {
            "id": self._make_id(),
            "type": type_,
            "source": source,
            "path": _normalize_path(path),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strength": strength,
            "decay_rate": decay_rate,
            "payload": payload or {},
        }
        with open(self.store_path, "a") as f:
            f.write(json.dumps(event) + "\n")
        return event

    def read_all(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.store_path):
            return []
        events = []
        skipped = 0
        with open(self.store_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    skipped += 1
                    continue
        if skipped:
            # Surfaced, not silently swallowed — per review, corrupted
            # events should be visible even though we keep going.
            print(f"[pheromone_store] WARNING: skipped {skipped} corrupt line(s) in {self.store_path}")
        return events

    def current_strength(self, event: Dict[str, Any]) -> float:
        """Decay-adjusted strength right now. decay_rate=0.0 means never decays."""
        if event.get("decay_rate", 0.0) <= 0.0:
            return event.get("strength", 1.0)
        ts = datetime.fromisoformat(event["timestamp"])
        hours_elapsed = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        remaining = event.get("strength", 1.0) - (event["decay_rate"] * hours_elapsed)
        return max(0.0, remaining)

    def active_by_type(self, type_: str, min_strength: float = 0.05) -> List[Dict[str, Any]]:
        return [
            e for e in self.read_all()
            if e["type"] == type_ and self.current_strength(e) >= min_strength
        ]

    def latest_task_event(self, path: str) -> Optional[Dict[str, Any]]:
        """The authoritative claim state for a path is its LATEST claim/release
        event, not a sum over history. This is what makes release actually work."""
        norm = _normalize_path(path)
        events = [
            e for e in self.read_all()
            if e["type"] in ("TASK_CLAIM", "TASK_RELEASE") and e["path"] == norm
        ]
        events.sort(key=lambda e: e["timestamp"])
        return events[-1] if events else None

    def regenerate_stank_md(self, out_path: str = "STANK.md"):
        fails = [e for e in self.read_all() if e["type"] == "VALIDATION_FAIL"]
        with open(out_path, "w") as f:
            for e in fails:
                reason = e.get("payload", {}).get("reason", "unspecified")
                f.write(f"- [DEAD LIMB] {e['path']} flagged: {reason}\n")

    def regenerate_who_did_what(self, out_path: str = "WHO_DID_WHAT.md"):
        contribs = [e for e in self.read_all() if e["type"] == "CONTRIBUTION"]
        with open(out_path, "w") as f:
            for e in contribs:
                date = e["timestamp"][:10]
                desc = e.get("payload", {}).get("description", "")
                f.write(f"{date}: {desc}\n")


# --- Task claiming: race-safe, and release actually releases ---

def claim_task(store: PheromoneStore, agent_id: str, path: str, ttl_hours: float = 1.0) -> bool:
    """Race-safe claim. Locks the store file for the duration of the
    read-check-append sequence so two agents can't both pass the check
    before either writes — the exact bug flagged in review."""
    norm = _normalize_path(path)
    with open(store.store_path, "a") as lockfile:
        fcntl.flock(lockfile, fcntl.LOCK_EX)
        try:
            latest = store.latest_task_event(norm)
            if latest and latest["type"] == "TASK_CLAIM" and latest["source"] != agent_id:
                if store.current_strength(latest) >= 0.05:
                    return False  # still live, held by someone else
            decay_rate = 1.0 / ttl_hours if ttl_hours > 0 else 0.0
            store.emit("TASK_CLAIM", source=agent_id, path=norm, decay_rate=decay_rate)
            return True
        finally:
            fcntl.flock(lockfile, fcntl.LOCK_UN)


def release_task(store: PheromoneStore, agent_id: str, path: str) -> bool:
    """Only the claim holder can release. Returns False if you don't own it."""
    norm = _normalize_path(path)
    latest = store.latest_task_event(norm)
    if not latest or latest["type"] != "TASK_CLAIM" or latest["source"] != agent_id:
        return False
    store.emit("TASK_RELEASE", source=agent_id, path=norm, decay_rate=0.0)
    return True


# --- Directory watcher: polling-based, safe on FUSE/SD-card mounts ---

class DirectoryWatcher:
    """Polls a directory tree for file changes and emits FILE_MUTATION
    pheromones. Polling instead of inotify on purpose — inotify is
    unreliable on FUSE-mounted SD card paths."""

    def __init__(
        self,
        root_dir: str,
        store: PheromoneStore,
        source: str = "DirectoryWatcher",
        extensions: Optional[List[str]] = None,
    ):
        self.root_dir = root_dir
        self.store = store
        self.source = source
        self.extensions = tuple(extensions) if extensions else (".py",)
        self._known: Dict[str, str] = {}

    def _hash_file(self, path: str) -> Optional[str]:
        try:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except (OSError, PermissionError):
            return None

    def scan_once(self):
        current: Dict[str, str] = {}
        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "node_modules"}]
            for fname in filenames:
                if fname.endswith(self.extensions):
                    fpath = os.path.join(dirpath, fname)
                    h = self._hash_file(fpath)
                    if h:
                        current[fpath] = h

        for fpath, h in current.items():
            if fpath not in self._known:
                self.store.emit("FILE_MUTATION", source=self.source, path=fpath,
                                 payload={"kind": "created", "hash": h})
            elif self._known[fpath] != h:
                self.store.emit("FILE_MUTATION", source=self.source, path=fpath,
                                 payload={"kind": "modified", "hash": h})

        for fpath in self._known:
            if fpath not in current:
                self.store.emit("FILE_MUTATION", source=self.source, path=fpath,
                                 payload={"kind": "deleted"})

        self._known = current

    def run(self, interval_seconds: int = 30):
        print(f"Watching {self.root_dir}, polling every {interval_seconds}s. Ctrl+C to stop.")
        try:
            while True:
                self.scan_once()
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("Watcher stopped.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python3 pheromone_store.py /path/to/watch")
        sys.exit(1)
    store = PheromoneStore()
    watcher = DirectoryWatcher(sys.argv[1], store)
    watcher.run()
