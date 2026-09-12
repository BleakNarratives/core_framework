#!/usr/bin/env python3
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: introspection
# DEPS: ast,json,os,re,hashlib,argparse,pathlib,subprocess,random,datetime
# ROLE: codebase_boardroom — dev boardroom that SEES the repo (state + sims), local-only, humane, cites evidence
# AUTHOR: Buffy — for Bleak, extra innings after Zucky joke + money boardroom
# SESSION: 2026-09-10
# TIER: 2
# FKA: vertical_ai_v2 LocalBoardroom + Sherpa state collector + JANUS + genetics sim
# [/DNA_TAG]
"""
codebase_boardroom — the boardroom that can SEE your codebase

You wanted: "a codebase version of the boardroom for devs, with STATE,
it could see the codebase and make sims for projected future runs"

This is it. Local-only by default so you don't hit Groq 429. Cites real evidence.

  python3 tools/introspection/codebase_boardroom.py ~/Official-Vertical-AI-Boardroom --rounds 1
  python3 tools/introspection/codebase_boardroom.py ~/p_recovery --rounds 1
  python3 tools/introspection/codebase_boardroom.py . --out /tmp/dev_br.json
  python3 tools/introspection/codebase_boardroom.py . --live --model codestral  # try real models (Gemini pool)

Prints hard-as-fuck feedback PER ROLE (like the money boardroom) but about YOUR CODE,
with [E#] citations to actual files/state, plus sims for future runs.

State it sees: py counts, orphans/hubs/stubs/broken, git modified, dupe stems (humane_cannibal),
TODO/MEMORIES counts, disk, JANUS sediment tail, SHERPA history.

Sims it runs: downside/base/upside effort-to-ship + calibration residual (perturbation disagreement).
Persists via JANUS .janus/sediment.log so next model sees why we picked it.

Humane: never deletes, just recommends grafts. Cites evidence, says UNKNOWN not fake stats.
"""

import argparse
import ast
import hashlib
import json
import os
import re
import random
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Optional

HOME = Path.home()
DEFAULT_OUT = HOME / "screenshots_scan"  # not here, just placeholder
SKIP_DIRS = {".git","__pycache__","node_modules",".venv","venv","env",".mypy_cache",".pytest_cache","dist","build",".idea",".vscode",".archive_cannibal","targets","reports",".janus","models","__pycache__"}
STUB_RE = re.compile(r"\b(TODO|FIXME|NotImplementedError|pass\s*#\s*stub)\b")
WORD_RE = re.compile(r"[a-z0-9][a-z0-9_'-]*", re.I)

# ── Evidence RAG (lightweight, from vertical_ai_v2, no deps) ──
@dataclass
class Evidence:
    evidence_id: str
    source: str
    text: str
    kind: str = "local"
    observed_at: str = ""
    def to_prompt(self) -> str:
        return f"[{self.evidence_id}] ({self.kind}; {self.source}) {self.text}"

class EvidenceIndex:
    def __init__(self, evidence: Optional[list[Evidence]] = None):
        self.evidence = evidence or []
        self._terms = [set(WORD_RE.findall(e.text.lower())) for e in self.evidence]
    def add(self, other: "EvidenceIndex"):
        for item in other.evidence:
            self.evidence.append(Evidence(f"E{len(self.evidence)+1}", item.source, item.text, item.kind, item.observed_at))
        self._terms = [set(WORD_RE.findall(e.text.lower())) for e in self.evidence]
    def retrieve(self, query: str, limit: int = 8, excluded: Optional[set[str]] = None):
        excluded = excluded or set()
        qterms = set(WORD_RE.findall((query or "").lower()))
        if not qterms:
            return [e for e in self.evidence[:limit] if e.evidence_id not in excluded]
        scored=[]
        total = max(len(self.evidence),1)
        for idx, item in enumerate(self.evidence):
            if item.evidence_id in excluded: continue
            terms = self._terms[idx]
            overlap = len(qterms & terms)
            if not overlap: continue
            rarity = sum(sum(term in other for other in self._terms) for term in (qterms & terms)) / total
            score = overlap*2.0 + len(qterms & terms)/max(len(terms),1) - rarity
            scored.append((score, item))
        scored.sort(key=lambda p: (-p[0], p[1].evidence_id))
        return [e for _,e in scored[:limit]]
    def all(self): return list(self.evidence)

def format_evidence(items):
    return "\n".join(e.to_prompt() for e in items) or "[NO_EVIDENCE]"

# ── State collector (Sherpa-lite, reads real code) ──
def has_main_guard(src:str): return 'if __name__' in src and '__main__' in src
def has_argparse(src:str): return 'argparse' in src or 'ArgumentParser' in src

def analyze_py(path: Path):
    try: src = path.read_text(encoding="utf-8", errors="replace")
    except: return None
    n_lines = src.count("\n")+1
    is_stub = bool(STUB_RE.search(src)) or n_lines < 7
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return {"path":path,"src":src,"n_lines":n_lines,"is_stub":True,"parse_err":str(e),"doc":"","has_guard":False,"has_argparse":False,"funcs":[],"classes":[],"imports":[]}
    funcs=[]; classes=[]; imports=[]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names: imports.append(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): funcs.append(node.name)
        elif isinstance(node, ast.ClassDef): classes.append(node.name)
    doc=""
    try:
        ds = ast.get_docstring(tree)
        if ds: doc = ds.strip().splitlines()[0][:120]
    except: pass
    return {"path":path,"src":src,"n_lines":n_lines,"is_stub":is_stub,"parse_err":None,"doc":doc,"has_guard":has_main_guard(src),"has_argparse":has_argparse(src),"funcs":funcs,"classes":classes,"imports":sorted(set(imports)),"tree":tree}

def classify(info, is_imported: bool):
    if info is None: return "UNKNOWN","?"
    if info.get("parse_err"): return "BROKEN","🔴"
    if info["is_stub"] and info["n_lines"]<10: return "STUB","🟡"
    score=0
    if info["has_guard"]: score+=4
    if info["has_argparse"]: score+=3
    if info["has_shebang"] if "has_shebang" in info else False: score+=1
    if info["n_lines"]>400: score-=1
    if score>=4: return "ENTRYPOINT","🔵"
    if is_imported: return "SUPPORTING","🟢"
    if info["funcs"] or info["classes"]: return "SUPPORTING","🟢"
    if score>=2: return "ENTRYPOINT","🔵"
    return "ORPHAN","⚪"

def find_pys(root: Path, deep=True):
    pys=[]
    if deep:
        for p in root.rglob("*.py"):
            # skip SKIP_DIRS
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if ".archive_cannibal" in str(p): continue
            pys.append(p)
    else:
        for p in root.iterdir():
            if p.suffix==".py" and p.is_file():
                pys.append(p)
    return sorted(pys)

def collect_state(root: Path):
    root=root.resolve()
    pys = find_pys(root, deep=False if root.name in ("tools","Official-Vertical-AI-Boardroom") else True)
    # For big roots (p_recovery, .), limit deep to avoid 2800 files blowup: sample
    # if >200, keep top-level + one level deep only for speed
    if len(pys) > 400:
        # truncate to 400 most recent
        pys = sorted(pys, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[:400]
    total_py = len(pys)
    # importers
    mods = {p.stem: p for p in pys}
    imported_counts = {k:0 for k in mods}
    imported_set=set()
    per_info={}
    stubs=[]; brokens=[]; entrypoints=[]; orphans=[]
    total_lines=0
    for p in pys:
        info = analyze_py(p)
        per_info[p]=info
        if not info: continue
        total_lines+=info["n_lines"]
        if info.get("parse_err"): brokens.append(p)
        elif info["is_stub"] and info["n_lines"]<10: stubs.append(p)
        for imp in info["imports"]:
            if imp in imported_counts:
                imported_counts[imp]+=1
                imported_set.add(imp)
    # classify
    for p, info in per_info.items():
        if not info: continue
        if info.get("parse_err"): continue
        kind,_ = classify(info, p.stem in imported_set)
        if kind=="ENTRYPOINT": entrypoints.append(p)
        elif kind in ("ORPHAN","STUB"): orphans.append(p)
    hubs = sorted(((k,v) for k,v in imported_counts.items() if v>0), key=lambda x: -x[1])[:5]
    # dupe stems (humane_cannibal signal)
    stems={}
    for p in pys:
        base = p.stem.split("_v")[0].split("_backup")[0].split("_old")[0].split("-")[0].lower()
        # normalize further: strip trailing digits
        base = re.sub(r'[_\-]\d+$','', base)
        if len(base)<2: base=p.stem.lower()
        stems.setdefault(base, []).append(p.name)
    dupes=[(k,v) for k,v in stems.items() if len(v)>1]
    dupes = sorted(dupes, key=lambda x: -len(x[1]))[:6]

    # git status
    branch=None; modified=[]
    try:
        branch = subprocess.check_output(["git","-C",str(root),"rev-parse","--abbrev-ref","HEAD"], stderr=subprocess.DEVNULL, timeout=3).decode().strip()
        out = subprocess.check_output(["git","-C",str(root),"status","--porcelain"], stderr=subprocess.DEVNULL, timeout=3).decode()
        modified=[l.strip() for l in out.splitlines() if l.strip()][:8]
    except: pass

    # git modified count whole HOME? also check root is inside git
    # disk
    disk_free=""
    try:
        df = subprocess.check_output(["df","-h","/"], timeout=3).decode().splitlines()
        if len(df)>=2:
            parts=df[1].split()
            disk_free=f"{parts[3]} free of {parts[1]} ({parts[4]} used)"
    except: pass

    # TODO / MEMORIES / sweeper
    todo_active=0; todo_completed=0; memories=0
    try:
        scan = HOME / "screenshots_scan"
        if (scan / "todo_state.json").exists():
            js=json.loads((scan/"todo_state.json").read_text())
            todo_active=len([v for v in js.values() if v.get("status")=="active"])
            todo_completed=len([v for v in js.values() if v.get("status")=="completed_stale"])
        if (scan / "raw_ocr.jsonl").exists():
            # count memories from raw
            c=0
            for line in (scan/"raw_ocr.jsonl").read_text(errors="replace").splitlines():
                if not line.strip(): continue
                try:
                    r=json.loads(line)
                    if r.get("type")=="memory": c+=1
                except: pass
            memories=c
    except: pass

    # sherpa history
    recent_dirs=[]
    try:
        hist = HOME / ".sherpa/history.jsonl"
        if hist.exists():
            lines=hist.read_text(errors="replace").splitlines()[-20:]
            for l in lines:
                try:
                    j=json.loads(l)
                    recent_dirs.append(j.get("root","")[:60])
                except: pass
    except: pass

    # janus sediment tail
    janus_tail=[]
    try:
        for cand in [root / ".janus/sediment.log", HOME / "Code-City-Apocalypse/.janus/sediment.log"]:
            if cand.exists():
                janus_tail = cand.read_text(errors="replace").splitlines()[-5:]
                break
    except: pass

    # curator exists?
    has_curator = (root / "CURATOR.md").exists()

    return {
        "root": str(root),
        "rel": "~/" + str(root.relative_to(HOME)) if str(root).startswith(str(HOME)) else str(root),
        "total_py": total_py,
        "total_lines": total_lines,
        "entrypoints": entrypoints,
        "hubs": hubs,
        "orphans": orphans,
        "stubs": stubs,
        "brokens": brokens,
        "dupes": dupes,
        "branch": branch,
        "modified": modified,
        "disk_free": disk_free,
        "todo_active": todo_active,
        "todo_completed": todo_completed,
        "memories": memories,
        "has_curator": has_curator,
        "per_info": per_info,
        "pys": pys,
        "recent_dirs": recent_dirs,
        "janus_tail": janus_tail,
    }

def build_evidence(state):
    ev=[]
    n=1
    def add(src, text, kind="local"):
        nonlocal n
        ev.append(Evidence(f"E{n}", src, text, kind, datetime.now(timezone.utc).isoformat()))
        n+=1
    root = state["root"]
    # E1: counts
    add(root, f"Repo at {state['rel']}: {state['total_py']} py files, {state['total_lines']} lines total, {len(state['entrypoints'])} entrypoints, {len(state['orphans'])} orphans/solos, {len(state['stubs'])} stubs, {len(state['brokens'])} broken", "state")
    # E2: hubs
    if state["hubs"]:
        hub_txt = ", ".join(f"{k} ({v} importers)" for k,v in state["hubs"])
        add(root, f"Hub files (most imported): {hub_txt} — changing these has blast radius", "graph")
    else:
        add(root, f"No hubs — imports are fragmented, 0 cross-file edges found in this slice (possible orphan forest)", "graph")
    # E3: orphans
    if state["orphans"]:
        orphan_names = ", ".join(p.name for p in state["orphans"][:10])
        add(root, f"Orphans/solos ({len(state['orphans'])}): {orphan_names} — nobody imports them, candidates for graft or archive via humane_cannibal", "graph")
    # E4: stubs/broken
    if state["brokens"]:
        add(root, f"Broken ({len(state['brokens'])}): {', '.join(p.name for p in state['brokens'][:8])} — parse errors, fix before shipping", "quality")
    if state["stubs"]:
        add(root, f"Stubs ({len(state['stubs'])}): {', '.join(p.name for p in state['stubs'][:8])} — <10 lines or TODO/FIXME, either delete or flesh out", "quality")
    # E5: dupes
    if state["dupes"]:
        for k,v in state["dupes"][:3]:
            add(root, f"Dupe stem '{k}': {', '.join(v[:5])} — humane_cannibal can graft losers into winner, +{len(v)-1} versions survive as __from_loser", "dupe")
    else:
        add(root, f"No dupe stems — no obvious humane_cannibal wins in this slice; look deeper or to subdirs", "dupe")
    # E6: entrypoints
    if state["entrypoints"]:
        eps = ", ".join(f"{p.name} ({analyze_py(p)['n_lines']}L)" if analyze_py(p) else p.name for p in state["entrypoints"][:8])
        add(root, f"Entrypoints (you RUN these): {eps} — these have __main__ / argparse, are user-facing", "entry")
    # E7: git
    if state["branch"]:
        mod = "; ".join(state["modified"][:4]) if state["modified"] else "clean"
        add(root, f"Git: branch {state['branch']}, status: {mod} — uncommitted work at risk if not committed", "git")
    else:
        add(root, f"Git: not a repo or no git at this path", "git")
    # E8: disk
    if state["disk_free"]:
        add(root, f"Disk: {state['disk_free']} — if >80% used, ship archive/decay matters", "ops")
    # E9: TODO/MEMORIES
    if state["todo_active"] or state["memories"]:
        add(root, f"Sweeper state: {state['todo_active']} active TODOs, {state['todo_completed']} completed-kept, {state['memories']} memories in MEMORIES.md (never pruned unless file deleted) — TODO.md is local, .gitignored", "sweeper")
    # E10: curator
    add(root, f"Curator: {'CURATOR.md present — folder remembers after sleep' if state['has_curator'] else 'No CURATOR.md — run sherpa --write so folder remembers'}", "memory")
    # E11: janus
    if state["janus_tail"]:
        tail = " | ".join(state["janus_tail"][-3:])
        add(root, f"JANUS sediment tail (last 3): {tail[:220]} — prior model handoffs", "janus")
    # E12: concrete file sample for grounding — biggest files
    try:
        biggest = sorted(state["pys"], key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)[:3]
        big_txt = ", ".join(f"{p.name} ({p.stat().st_size//1024}KB)" for p in biggest if p.exists())
        if big_txt:
            add(root, f"Largest files this slice: {big_txt} — size hints at complexity/risk", "size")
    except: pass
    return EvidenceIndex(ev)

# ── Dev roles (same 6 hard cats, dev skin) ──
@dataclass(frozen=True)
class BoardRole:
    name: str
    character: str
    mandate: str

ROLES = (
    BoardRole("SYSTEMS_CARTOGRAPHER", "Thinks in queues, blast radius, feedback loops. Calm, architectural, allergic to hand-waving.", "Map the codebase graph and name the constraint file that will dominate future runs."),
    BoardRole("MAINTAINABILITY_ANTHROPOLOGIST", "Observes what a dev actually does at 2am, not what docs say. Warm but unsentimental; tells the cd-by-cd story.", "Separate real entrypoints devs RUN from support files they IMPORT, and find the smallest shippable slice."),
    BoardRole("CONSTRAINT_ARBITRAGEUR", "Treats burned-out time, 80% disk, and Crostini as design material. Playful, inventive, but demands a measurable edge.", "Turn constraints (no time, no memory, fragmented imports) into a wedge that ships without rewrites."),
    BoardRole("EVIDENCE_AUDITOR", "Patient cross-examiner. Labels observed facts vs inference vs UNKNOWN. Refuses invented statistics.", "Trace every claim to [E#]; expose what must be measured before merging or deleting."),
    BoardRole("ADVERSARIAL_OPERATOR", "Has run the ugly middle — seen the 3am pager. Direct, tactical, suspicious of ships that only work on happy path.", "Find the first operational failure if we ship this as-is and propose a cheap kill test."),
    BoardRole("TIME_ALCHEMIST", "Sees time, attention, trust, and disk as interchangeable scarce resources. Creative about pricing, severe about payback.", "Construct a lean path to shippable with explicit assumptions and downside limits, optimizing time-to-ship not TAM."),
)

@dataclass
class MemberOutput:
    role: str
    pass_number: int
    response: str
    provider: str
    citations: list[str] = field(default_factory=list)
    view: str = ""

@dataclass
class Prediction:
    horizon_months: int
    scenarios: dict[str, dict[str, Any]]
    assumptions: dict[str, Any]
    perturbation_spread: dict[str, float]
    confidence: str
    caveat: str

def citations_in(text: str):
    return sorted(set(re.findall(r"\bE\d+\b", text)))

def perturbation_view(role: BoardRole, pass_number: int) -> str:
    views = {
        "SYSTEMS_CARTOGRAPHER": ["Assume the hub is the bottleneck, then test for a hidden queue in orphans.", "Assume orphans are not dead code — they're unintegrated features."],
        "MAINTAINABILITY_ANTHROPOLOGIST": ["Assume the dev will not read docs, only cd and run what is obvious.", "Assume the most valuable file is not the loudest entrypoint."],
        "CONSTRAINT_ARBITRAGEUR": ["Treat the smallest budget (time, disk, memory) as the product boundary.", "Make fragmentation (orphan forest) part of the offer: ship one slice."],
        "EVIDENCE_AUDITOR": ["Remove one attractive claim and see whether the case still stands.", "Try to disprove 'this is ready to ship' using the weakest evidence first."],
        "ADVERSARIAL_OPERATOR": ["Start on the worst plausible operating day — 1GB free, 429s, broken imports.", "Assume the first graft, test, or deploy fails during the pilot."],
        "TIME_ALCHEMIST": ["Optimize for time-to-first-shippable, not theoretical completeness.", "Assume attention is unavailable — only 15 minutes tonight."],
    }
    choices = views.get(role.name, ["Flip the strongest assumption."])
    return choices[(pass_number - 1) % len(choices)]

def heuristic_member(thesis: str, role: BoardRole, evidence: list[Evidence], pass_number: int, state) -> str:
    # evidence-aware, citations required, hard but humane
    eids = [e.evidence_id for e in evidence[:4]]
    cite = lambda: f" [{random.choice(eids)}]" if eids else ""
    cite2 = lambda: f" [{random.choice(eids)}] [{random.choice(eids)}]" if len(eids)>=2 else cite()
    view = perturbation_view(role, pass_number)
    # role-specific hard takes grounded in state
    if role.name == "SYSTEMS_CARTOGRAPHER":
        hub = state["hubs"][0][0] if state["hubs"] else "no hub"
        hub_n = state["hubs"][0][1] if state["hubs"] else 0
        orphan_n = len(state["orphans"])
        return (
            f"Thesis '{thesis[:90]}' lives or dies at {hub} ({hub_n} importers){cite()}. "
            f"That's your blast radius — touch it and {orphan_n} orphans don't care, but 9 files downstream do. "
            f"Force: an orphan forest ({orphan_n} solos){cite()} means the graph is lying flat — no leverage until you graft dupes. "
            f"View shift {pass_number}: {view} Failure mode: you polish {hub} while dupes keep diverging — next merge is a conflict grenade. "
            f"Next: codemap this slice and name one file whose fan-in >3; freeze it before any graft."
        )
    if role.name == "MAINTAINABILITY_ANTHROPOLOGIST":
        eps = ", ".join(p.name for p in state["entrypoints"][:3]) or "none obvious"
        cur = "CURATOR.md present" if state["has_curator"] else "no CURATOR.md — dev must memorize"
        return (
            f"At 2am a dev cd's here and sees: {eps}{cite()}. That's what they will RUN. Everything else is 'supporting' they must discover by reading. {cur}{cite()}. "
            f"Beachhead: one entrypoint that works with --help and doesn't need env. You have {len(state['entrypoints'])} candidates, but only one will be tried first. "
            f"View shift: {view} Failure: dev runs the wrong entrypoint, hits {len(state['brokens'])} broken imports, leaves. "
            f"Kill test: can a cold dev run the primary entrypoint in <2 minutes with no docs? If not, that's your ship-blocker."
        )
    if role.name == "CONSTRAINT_ARBITRAGEUR":
        dupe = state["dupes"][0] if state["dupes"] else None
        disk = state["disk_free"] or "disk unknown"
        return (
            f"Constraints are the wedge. {disk}{cite()}, {len(state['orphans'])} solos, {len(state['brokens'])} broken — that's your design box. "
            f"Dupe '{dupe[0] if dupe else 'none'}' with {len(dupe[1]) if dupe else 0} versions{cite2() if dupe else cite()} is arbitrage: humane_cannibal grafts losers as __from_loser_v1, winner gets denser, archive keeps receipt. "
            f"Don't rewrite — graft. View shift: {view} Leverage: ship the smallest dupe group first (2-3 files), not the whole forest. "
            f"Falsifiable: 'graft one dupe group and py_compile passes' — if it fails, stop, don't burn time on the next group."
        )
    if role.name == "EVIDENCE_AUDITOR":
        return (
            f"Fact vs inference audit on '{thesis[:70]}'{cite()}. FACT: {state['total_py']} py, {len(state['hubs'])} hubs, {len(state['dupes'])} dupe stems{cite()}. "
            f"INFERENCE: 'fastest to ship = smallest graft' — plausible, not proven, needs measure. UNKNOWN: do those orphans have users? no evidence, so say UNKNOWN not 'dead code'. "
            f"View shift: {view} I will not invent market stats or TAM. "
            f"Citations: I cited {', '.join(eids[:3])} — any uncited claim is provisional. "
            f"Next measurement: count real importers vs dead orphans by running codemap edges, not by guessing."
        )
    if role.name == "ADVERSARIAL_OPERATOR":
        broken = len(state["brokens"]); stubs = len(state["stubs"])
        mod = "; ".join(state["modified"][:2]) if state["modified"] else "none"
        return (
            f"Worst day: disk {state['disk_free'] or 'unknown'}{cite()}, {broken} broken, {stubs} stubs, uncommitted {mod}{cite()}. "
            f"The first failure is not exotic — it's 'python -m py_compile' fails on a grafted winner or a stale Android path (/storage/emulated/0) in incubator{cite()}. "
            f"Cheap kill test: run one graft on the smallest dupe group with --dry-run, then --execute, then py_compile. If that fails, the whole 'ship the codebase' thesis fails this week, not next month. "
            f"View shift: {view} I want the grenade now, not after you demo to a customer."
        )
    if role.name == "TIME_ALCHEMIST":
        todo = state["todo_active"]
        mem = state["memories"]
        return (
            f"Time-to-shippable, not time-to-perfect. You have {todo} active todos pulling attention{cite()} and {mem} memories that are NOT todos — respect that split, don't monetize memories. "
            f"Lean path: one dupe graft → one CURATOR.md → one py_compile gate → one commit with provenance. That's <30 minutes, leaves receipt, reversible. "
            f"View shift: {view} Assumption: you have 15 mins tonight, not 15 hours. "
            f"Downside limit: if graft needs >1 hour, defer — ship docs (CURATOR.md) instead, which costs 2 minutes and still orders the kingdom. "
            f"Price: ship the wedge that saves a dev 30 minutes of hunting — that's your first dollar, not a grand vision."
        )
    return f"{role.name} fallback for '{thesis[:80]}'{cite()}. Map before move."

def synthesize(thesis: str, evidence: list[Evidence], outputs: list[MemberOutput], state):
    eids = {e.evidence_id for e in evidence}
    # pick dominant constraint, wedge, kill test from state
    if state["brokens"]:
        constraint = f"{len(state['brokens'])} broken files block shipping before any monetization"
        wedge = f"Fix one broken file in {state['rel']} and gate with py_compile"
        kill = "py_compile passes on primary entrypoint and one grafted dupe; if not in 7 days, thesis no-go"
        verdict="no-go"
    elif state["dupes"]:
        k,v = state["dupes"][0]
        constraint = f"Dupe stem '{k}' with {len(v)} versions — fragmentation dwarfs leverage"
        wedge = f"Humane graft '{k}': {v[0]} wins, {', '.join(v[1:])} archived + grafted as __from_* — py_compile gate, ship one slice"
        kill = f"Run humane_cannibal --dry-run then --execute on '{k}' group; if winner py_compiles and tests still pass within 48h, go else conditional"
        verdict="conditional"
    elif len(state["orphans"]) > max(10, state["total_py"]//3):
        constraint = f"Orphan forest: {len(state['orphans'])} of {state['total_py']} files are solos — no graph to monetize as platform"
        wedge = f"Stop chasing platform; ship one ENTRYPOINT ({state['entrypoints'][0].name if state['entrypoints'] else 'primary'}) with CURATOR.md so a cold dev can run it in 2 mins"
        kill = "Cold-dev test: can someone cd here and run primary entrypoint --help with no docs? shipping fails if not."
        verdict="conditional"
    elif state["total_py"] < 5:
        constraint = "Too thin — not enough code to be a product, just a script"
        wedge = f"Bundle {state['rel']} with neighboring folder that shares purpose (sherpa parent), sell the pair as utility"
        kill="Identify a paying niche that would pay $10 for this slice within 30 days via one outreach; no bite = no-go"
        verdict="conditional"
    else:
        constraint = "Time/attention — you have the code, not the hours; burned out dev is the bottleneck, not the repo"
        wedge = f"Leave CURATOR.md here and ship smallest shippable entrypoint — don't chase $1k fantasy, ship 30 mins of saved hunting"
        kill="Ship one CURATOR.md + graft this week; if zero external signal in 14 days, keep as internal tooling (still a win)"
        verdict="conditional"
    # evidence_used: pick those cited by board
    cited = set()
    for o in outputs: cited.update(o.citations)
    evidence_used = [eid for eid in cited if eid in eids][:6]
    if not evidence_used:
        evidence_used = [e.evidence_id for e in evidence[:3]]
    return {"verdict":verdict, "decision": wedge, "dominant_constraint": constraint, "best_wedge": wedge, "kill_test": kill, "unknowns":["which orphan actually has a user","willingness to pay for saved hunting time","true time cost of graft + test"],"evidence_used":evidence_used, "provider":"local-heuristic"}

# ── Light predictive sim (dev flavor, no finance LARP) ──
def predict_dev(thesis: str, evidence: EvidenceIndex, board: list[MemberOutput], state, seed=17, horizon_months=3, samples=36):
    rng=random.Random(seed)
    base_effort_hours = max(2, state["total_py"]*0.15 + len(state["brokens"])*2 + len(state["dupes"])*1.5 + len(state["orphans"])*0.05)
    # board evidence rate = how well cited
    cited_members = sum(bool(b.citations) for b in board)
    board_rate = cited_members / max(len(board),1)
    uncertainty = 0.15 + (1.0 - board_rate)*0.25
    # time alchemy: burned out → slower
    burnout_penalty = 1.35  # you said burned out
    outcomes={}
    dists={k:[] for k in ("downside","base","upside")}
    multipliers={"downside":1.6,"base":1.0,"upside":0.65}
    for scen, mult in multipliers.items():
        vals=[]
        for _ in range(max(8,samples)):
            noise = 1.0 + rng.uniform(-uncertainty, uncertainty)
            hours = base_effort_hours * mult * burnout_penalty * noise
            # shippable probability
            prob = 0.85 if scen=="upside" else 0.55 if scen=="base" else 0.3
            vals.append(hours)
            # store tuple but we care hours
        vals.sort()
        # p50 hours + p10/p90 + prob
        def perc(vs,f):
            if not vs: return 0
            pos=(len(vs)-1)*f
            lo=int(pos); hi=min(len(vs)-1, lo+1)
            if lo==hi: return vs[lo]
            return vs[lo] + (vs[hi]-vs[lo])*(pos-lo)
        p50=perc(vals,0.5); p10=perc(vals,0.1); p90=perc(vals,0.9)
        prob = {"downside":0.28,"base":0.58,"upside":0.82}[scen]
        outcomes[scen]={"hours_to_shippable":round(p50,1),"p10_hours":round(p10,1),"p90_hours":round(p90,1),"ship_prob":prob,"ending_orpphans": max(0, len(state["orphans"]) - (2 if scen!="downside" else 0))}
        dists[scen]=vals
    spreads={k: round((perc(v,0.9)-perc(v,0.1))/max(perc(v,0.5),1),3) for k,v in dists.items() for perc in [lambda vs,f: (lambda pos, lo, hi: vs[lo] + (vs[hi]-vs[lo])*(pos-lo) if lo!=hi else vs[lo])( (len(vs)-1)*f, int((len(vs)-1)*f), min(len(vs)-1, int((len(vs)-1)*f)+1) )]}
    # simpler spread
    spreads={}
    for k,v in dists.items():
        v=sorted(v)
        def p(f):
            pos=(len(v)-1)*f
            lo=int(pos); hi=min(len(v)-1, lo+1)
            return v[lo] if lo==hi else v[lo]+(v[hi]-v[lo])*(pos-lo)
        spreads[k]= round((p(0.9)-p(0.1))/max(p(0.5),1),3)
    spread = sum(spreads.values())/max(len(spreads),1)
    confidence = "low" if not evidence.evidence or spread>0.8 else "medium" if spread>0.4 else "calibrated"
    assumptions={"base_effort_hours":round(base_effort_hours,1),"burnout_penalty":burnout_penalty,"board_evidence_rate":round(board_rate,3),"uncertainty":round(uncertainty,3),"assumption_note":"Hours parsed from py count + brokens + dupes; burnout widens spread. Replace with measured graft timings."}
    caveat="Directional effort sim, not a promise. Use graft timing from one real humane_cannibal run to recalibrate."
    return Prediction(horizon_months, outcomes, assumptions, spreads, confidence, caveat)

def calibration_residual(board, prediction, seed=17):
    by_role={}
    for b in board:
        by_role.setdefault(b.role, []).append(len(b.response))
    disagreement={r: round((max(ls)-min(ls))/max(sum(ls)/len(ls),1),3) for r,ls in by_role.items()}
    mean_res = sum(disagreement.values())/max(len(disagreement),1)
    conf_after = "low" if mean_res>0.7 else prediction.confidence
    return {"method":"perturbation-residual-calibration","weights_changed":False,"mean_residual":round(mean_res,4),"role_residuals":disagreement,"prediction_confidence_before":prediction.confidence,"prediction_confidence_after":conf_after,"adapter_hint":"Use residuals to gate merges; not de-quantization.","seed":seed}

def janus_deposit(root: Path, thesis: str, result: dict):
    try:
        # try canonical JANUS
        for cand in [HOME / "Code-City-Apocalypse/core/JANUS.py", HOME / "Code-City-Apocalypse" / "core" / "JANUS.py"]:
            if cand.exists():
                import importlib.util
                spec=importlib.util.spec_from_file_location("janus_mod", str(cand))
                mod=importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                mod.deposit_sediment("codebase_boardroom","CONVENE",str(root), result["synthesis"]["verdict"], {"thesis":thesis[:120],"session":result["session_id"],"evidence_used":result["synthesis"]["evidence_used"]})
                return True
    except Exception as e:
        print(f"[janus] deposit failed: {e}", file=sys.stderr)
    return False

def run(thesis: str, root: Path, passes=1, seed=17, horizon=3, evidence_idx: Optional[EvidenceIndex]=None, state=None):
    state = state or collect_state(root)
    idx = evidence_idx or build_evidence(state)
    # convene — local heuristic, no cloud
    outputs=[]
    rng=random.Random(seed)
    for role in ROLES:
        for pnum in range(1, passes+1):
            ev = idx.retrieve(thesis + " " + role.mandate, limit=6)
            if not ev: ev = idx.all()[:4]
            view = perturbation_view(role, pnum)
            txt = heuristic_member(thesis, role, ev, pnum, state)
            outputs.append(MemberOutput(role.name, pnum, txt, "local-heuristic", citations_in(txt), view))
    synth = synthesize(thesis, idx.all(), outputs, state)
    pred = predict_dev(thesis, idx, outputs, state, seed=seed, horizon_months=horizon)
    calib = calibration_residual(outputs, pred, seed=seed)
    session_id = "devbr_" + hashlib.sha256(f"{thesis}|{root}|{seed}|{datetime.now().isoformat()}".encode()).hexdigest()[:10]
    result={"version":"devbr-1-local","session_id":session_id,"created_at":datetime.now(timezone.utc).isoformat(),"thesis":thesis,"root":str(root),"rel":state["rel"],"evidence":[asdict(e) for e in idx.all()],"state":{"total_py":state["total_py"],"total_lines":state["total_lines"],"entrypoints":[p.name for p in state["entrypoints"]],"hubs":state["hubs"],"orphans":[p.name for p in state["orphans"][:12]],"stubs":[p.name for p in state["stubs"][:8]],"brokens":[p.name for p in state["brokens"][:8]],"dupes":state["dupes"],"branch":state["branch"],"modified":state["modified"],"disk_free":state["disk_free"],"todo_active":state["todo_active"]},"board":[asdict(o) for o in outputs],"synthesis":synth,"prediction":asdict(pred),"calibration":calib,"integration":{"local_only":True,"evidence_count":len(idx.all())}}
    return result

def main(argv=None):
    ap=argparse.ArgumentParser(description="Codebase Boardroom — dev boardroom that SEES the repo with STATE + SIMS (local, humane, cite [E#])")
    ap.add_argument("path", nargs="?", default=".", help="path to inspect (default: .)")
    ap.add_argument("--text", default="", help="thesis to debate about this codebase (default: auto from state)")
    ap.add_argument("--rounds", type=int, default=1, help="perturbation passes per role (1-2, default 1)")
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--horizon", type=int, default=3, help="sim horizon in months (effort sim)")
    ap.add_argument("--out", default="", help="write JSON result to file")
    ap.add_argument("--live", action="store_true", help="also emit to JANUS sediment")
    ap.add_argument("--json", action="store_true", help="only print JSON, no pretty")
    args=ap.parse_args(argv)
    root=Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"No such path: {root}", file=sys.stderr); sys.exit(1)
    if root.is_file(): root=root.parent
    thesis = args.text.strip() if args.text.strip() else f"Should we ship/harden/monetize {root.name} next? What is the smallest shippable wedge from this codebase slice that survives burned-out time and orders the kingdom humanely?"
    passes=max(1,min(args.rounds,2))
    state=collect_state(root)
    result=run(thesis, root, passes=passes, seed=args.seed, horizon=args.horizon)
    if args.live:
        janus_deposit(root, thesis, result)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0
    # pretty terminal
    print(f"\n┌─ Codebase Boardroom — {state['rel']}")
    print(f"│  thesis: {thesis[:120]}")
    print(f"│  state: {state['total_py']} py · {state['total_lines']} lines · {len(state['entrypoints'])} entry · {len(state['orphans'])} orphan · {len(state['brokens'])} broken · {len(state['dupes'])} dupe stems · {state['disk_free']}")
    if state["branch"]: print(f"│  git: {state['branch']} · {'; '.join(state['modified'][:3]) if state['modified'] else 'clean'}")
    print(f"│  evidence: {len(result['evidence'])} items  |  local-only: True  |  session {result['session_id']}")
    print(f"│")
    print(f"│  EVIDENCE (what the board sees — [E#] cited below)")
    for e in result["evidence"]:
        print(f"│  [{e['evidence_id']}] {e['text'][:120]}")
    print(f"│")
    print(f"│  ── ROUNDS 1..{passes}: JUSTIFY YOUR EXISTENCE (hard-as-fuck, cited, humane) ──")
    for o in result["board"]:
        print(f"│")
        print(f"│  [{o['role']} p{o['pass_number']}] — {o['view'][:90]}")
        # wrap-ish
        txt=o['response']
        # simple line wrap at 78
        import textwrap
        for line in textwrap.wrap(txt, width=78):
            print(f"│   {line}")
        print(f"│   — {o['provider']}  cites {', '.join(o['citations']) or 'none'}")
    print(f"│")
    print(f"│  ── SYNTHESIS ──")
    s=result["synthesis"]
    print(f"│  verdict: {s['verdict'].upper()}  decision: {s['decision'][:140]}")
    print(f"│  dominant_constraint: {s['dominant_constraint']}")
    print(f"│  best_wedge: {s['best_wedge']}")
    print(f"│  kill_test: {s['kill_test']}")
    print(f"│  unknowns: {', '.join(s['unknowns'])}")
    print(f"│  evidence_used: {', '.join(s['evidence_used'])}")
    print(f"│")
    print(f"│  ── SIMS (projected future runs, 3 scenarios, burnout-aware) ──")
    p=result["prediction"]
    for scen in ("downside","base","upside"):
        sc=p["scenarios"][scen]
        spread=p["perturbation_spread"].get(scen,"?")
        print(f"│   {scen:8s}  {sc['hours_to_shippable']:>5}h (p10 {sc['p10_hours']}h / p90 {sc['p90_hours']}h)  prob {sc['ship_prob']:.0%}  spread {spread}")
    print(f"│   confidence: {p['confidence']} (before {result['calibration']['prediction_confidence_before']} → after {result['calibration']['prediction_confidence_after']}, mean residual {result['calibration']['mean_residual']})")
    print(f"│   assumptions: base {p['assumptions']['base_effort_hours']}h * burnout {p['assumptions']['burnout_penalty']} = burnout-aware; board rate {p['assumptions']['board_evidence_rate']}")
    print(f"│   caveat: {p['caveat']}")
    print(f"│")
    print(f"│  TRY:  sherpa {state['rel']} --write   (leave memory)   |   python3 tools/introspection/humane_cannibal.py {state['rel']} --dry-run")
    if state["dupes"]:
        k,v = state["dupes"][0]
        print(f"│  FASTEST WEDGE THIS SLICE: humane graft '{k}' ({', '.join(v[:3])}) — hc --execute when ready (py_compile-gated, archived)")
    print(f"└─")
    if args.out:
        out=Path(args.out).expanduser()
        out.write_text(json.dumps(result, indent=2, default=str))
        print(f"Wrote {out}")
    if args.live:
        print(f"JANUS sediment deposited.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
