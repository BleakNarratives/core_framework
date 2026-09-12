#!/usr/bin/env python3
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: introspection
# DEPS: ast,os,json,pathlib,re,sys
# ROLE: Sherpa — humane codebase tour guide, stays in terminal, remembers for you (entry vs support, use cases, edge cases, CURATOR.md)
# AUTHOR: Buffy — named Sherpa by Bleak (honor)
# SESSION: 2026-09-10
# TIER: 2
# FKA: bardildo+fartographer+loomy → Sherpa (the one that actually hooks cd)
# [/DNA_TAG]
"""
Sherpa — your humane curator. The one that finally sticks.

You cd somewhere and have no idea what you're holding?
  sherpa          — tell me about HERE, in terminal, no browser
  c               — same, short (c = curate/see)
  tour ~/tools    — tour any path
  sherpa --write  — leave a CURATOR.md in this folder so you remember after sleep
  where-was-i     — what did I touch today? (no memory needed)

It answers the question you actually asked early on:
  "which scripts are for WHAT? which ones do I RUN vs which ones SUPPORT the runners?
   what are the 3 use cases? alternate uses? edge cases?"

No file ever deleted. CURATOR.md is the folder's memory, not yours.
Uses codemap (imports) + ast (entrypoint) + docstring, all stdlib.
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path

HOME = Path.home()
SHERPA_HOME = HOME / ".sherpa"
SHERPA_HOME.mkdir(exist_ok=True)
HISTORY = SHERPA_HOME / "history.jsonl"
TODAY = SHERPA_HOME / f"today_{date.today().isoformat()}.md"

SKIP_DIRS = {".git","__pycache__","node_modules",".venv","venv","env",".mypy_cache",".pytest_cache","dist","build",".idea",".vscode",".archive_cannibal","targets","reports","__pycache__"}
STUB_RE = re.compile(r"\b(TODO|FIXME|NotImplementedError|pass\s*#\s*stub)\b")

LANG_BY_EXT = {".py":"python",".js":"js",".ts":"ts",".rs":"rust",".go":"go",".sh":"shell",".md":"docs",".json":"json"}

def has_main_guard(src: str) -> bool:
    return 'if __name__' in src and '__main__' in src
def has_argparse(src: str) -> bool:
    return 'argparse' in src or 'click' in src or 'ArgumentParser' in src
def has_main_func(tree) -> bool:
    try:
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in ("main","cli","run","execute"):
                return True
    except: pass
    return False
def has_shebang(src: str) -> bool:
    return src.startswith("#!")
def doc_first_line(src: str, tree) -> str:
    try:
        ds = ast.get_docstring(tree)
        if ds: return ds.strip().splitlines()[0][:120]
    except: pass
    # fallback first comment
    for line in src.splitlines()[:15]:
        s=line.strip()
        if s.startswith("#") and len(s)>4 and "DNA_TAG" not in s and "!" not in s:
            return s.lstrip("# ").strip()[:120]
    return ""

def analyze_py(path: Path):
    try: src = path.read_text(encoding="utf-8", errors="replace")
    except: return None
    n_lines = src.count("\n")+1
    is_stub = bool(STUB_RE.search(src)) or n_lines < 7
    try: tree = ast.parse(src, filename=str(path))
    except SyntaxError as e: return {"path":path,"src":src,"n_lines":n_lines,"is_stub":True,"parse_err":str(e),"doc":"","has_guard":False,"has_argparse":False,"has_main":False,"has_shebang":has_shebang(src),"funcs":[],"classes":[],"imports":[]}
    # funcs/classes
    funcs=[]; classes=[]
    imports=[]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names: imports.append(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): funcs.append(node.name)
        elif isinstance(node, ast.ClassDef): classes.append(node.name)
    return {"path":path,"src":src,"n_lines":n_lines,"is_stub":is_stub,"parse_err":None,"doc":doc_first_line(src,tree),"has_guard":has_main_guard(src),"has_argparse":has_argparse(src),"has_main":has_main_func(tree),"has_shebang":has_shebang(src),"funcs":funcs,"classes":classes,"imports":sorted(set(imports)),"tree":tree}

def classify(info, is_imported: bool):
    """ENTRYPOINT = you run it. SUPPORTING = others import it. ORPHAN = neither. STUB = tiny."""
    if info is None: return "UNKNOWN","?"
    if info.get("parse_err"): return "BROKEN","🔴"
    if info["is_stub"] and info["n_lines"]<10: return "STUB","🟡"
    score=0
    if info["has_guard"]: score+=4
    if info["has_argparse"]: score+=3
    if info["has_main"]: score+=2
    if info["has_shebang"]: score+=1
    if info["n_lines"]>400: score-=1 # large libs less likely entrypoint
    # decision
    if score>=4: return "ENTRYPOINT","🔵"
    if is_imported: return "SUPPORTING","🟢"
    if info["funcs"] or info["classes"]: return "SUPPORTING","🟢"
    if score>=2: return "ENTRYPOINT","🔵"
    return "ORPHAN","⚪"

def infer_use_cases(info):
    if not info or info.get("parse_err"): return ["(broken — needs fix before use)"]
    doc=(info["doc"] or "").lower()
    funcs=info["funcs"]+info["classes"]
    uses=[]
    # from doc
    if "boardroom" in doc or "boardroom" in " ".join(funcs).lower(): uses.append("Run a boardroom debate on an idea (vertical_ai.py --text)")
    if "router" in doc or "call_model" in funcs: uses.append("Route a prompt to Groq/Gemini/OpenRouter with failover")
    if "codemap" in doc: uses.append("Map import graph + find orphans/stubs (codemap.py <dir>)")
    if "cannibal" in doc: uses.append("Humane merge of duplicate stems (archive losers, graft into winner)")
    if "curator" in doc or "sherpa" in doc: uses.append("Tour current folder — see entry vs support + where to cd next")
    if "dna_tag" in doc: uses.append("Stamp provenance tag so folder remembers origin/pillar/role")
    if "scout" in doc or "intel" in doc: uses.append("Scout a business/vertical for enrichment data")
    if not uses:
        # fallback from func names
        if info["has_argparse"] or info["has_guard"]:
            uses.append(f"Run directly: python3 {info['path'].name} --help")
        if funcs:
            uses.append(f"Import & call: from {info['path'].stem} import {funcs[0]}")
            if len(funcs)>1: uses.append(f"Also provides: {', '.join(funcs[1:3])}")
        if not uses: uses.append("Supporting library — imported by others, not run standalone")
    # pad to 3
    while len(uses)<3:
        if "ENTRY" in classify(info, False)[0]: uses.append("Alternate: wire as subcommand in a larger CLI")
        else: uses.append("Alternate: reuse its helpers in a new script")
        if len(uses)>=3: break
    return uses[:3]

def infer_alternate(info):
    if not info: return "-"
    alts=[]
    if info["has_argparse"]: alts.append("Can be imported as library (skip CLI, call functions directly)")
    if not info["has_argparse"] and info["funcs"]: alts.append("Can be wrapped with argparse to become a CLI")
    if "scout" in info["doc"].lower(): alts.append("Use offline with cached data (no API needed)")
    if not alts: alts.append("Copy its pattern to scaffold a new tool in same pillar")
    return alts[0]

def infer_edges(info):
    if not info: return "-"
    if info.get("parse_err"): return f"Parse fail: {info['parse_err'][:80]} — fix syntax before running"
    edges=[]
    src=info["src"]
    if "api_key" in src.lower() or "API_KEY" in src: edges.append("Needs API keys (vault-env) — fails gracefully if missing")
    if "/storage/emulated" in src or "/data/data/com.termux" in src: edges.append("Has old Android paths — will fail on Crostini until patched")
    if "rclone" in src.lower(): edges.append("Needs rclone remote configured + network")
    if "try:" not in src and info["n_lines"]>50: edges.append("Few try/excepts — may crash on bad input (add guard)")
    if "TODO" in src or "FIXME" in src: edges.append("Has TODO/FIXME — incomplete path")
    if not edges: edges.append("No obvious edge case — check `python3 -m py_compile file.py` before trusting")
    return edges[0]

def find_py_here(root: Path):
    files=[]
    try:
        for p in root.iterdir():
            if p.is_file() and p.suffix==".py": files.append(p)
    except: pass
    return sorted(files)

def find_subdirs(root: Path):
    dirs=[]
    try:
        for p in root.iterdir():
            if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith("."):
                # quick check if it has code
                has_code = any(p.glob("*.py")) or any(p.glob("*.md")) or (p / "package.json").exists() or (p / "Cargo.toml").exists()
                dirs.append(p)
    except: pass
    return sorted(dirs)

def importers_of(root: Path, files):
    """Which files are imported by others (via codemap-lite)."""
    # build mod names for files in this dir only
    mods={}
    for f in files:
        mods[f.stem]=f
    imported=set()
    for f in files:
        info=analyze_py(f)
        if not info: continue
        for imp in info["imports"]:
            if imp in mods: imported.add(imp)
    return imported

def git_status(root: Path):
    try:
        out=subprocess.check_output(["git","-C",str(root),"status","--porcelain"], stderr=subprocess.DEVNULL, timeout=3).decode()
        lines=[l for l in out.splitlines() if l.strip()]
        branch=subprocess.check_output(["git","-C",str(root),"rev-parse","--abbrev-ref","HEAD"], stderr=subprocess.DEVNULL, timeout=3).decode().strip()
        return branch, lines[:8]
    except: return None, []

def readme_blurb(root: Path):
    for name in ["README.md","README","CLAUDE.md","runbook.txt","CURATOR.md"]:
        p=root / name
        if p.exists():
            try:
                t=p.read_text(encoding="utf-8", errors="replace")
                first=[l.strip() for l in t.splitlines() if l.strip() and not l.startswith("# [")][:3]
                return " ".join(first)[:180]
            except: pass
    return ""

def render_terminal(root: Path, write=False):
    root=root.resolve()
    rel = "~/" + str(root.relative_to(HOME)) if str(root).startswith(str(HOME)) else str(root)
    # collect
    files=find_py_here(root)
    subdirs=find_subdirs(root)
    imported_stems=importers_of(root, files)
    branch, git_lines = git_status(root)
    blurb=readme_blurb(root)

    # header
    print("┌─ Sherpa —", rel)
    print(f"│  {blurb or 'No README yet — I will describe what I can from the code itself.'}")
    print(f"│  {len(files)} .py here · {len(subdirs)} subdirs · last tour {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if branch: print(f"│  git: {branch} · {len(git_lines)} modified" + (f" — {git_lines[0][:60]}" if git_lines else ""))

    if not files and not subdirs:
        print("│  (empty — no .py, no subdirs with code. `ls -la` to see hidden?)")
        return

    if files:
        print("│")
        print("│  SCRIPTS — what runs vs what supports you")
        print("│  ─────────────────────────────────────────")
        # sort: entrypoints first, then supporting, then orphans
        scored=[]
        for f in files:
            info=analyze_py(f)
            is_imp = f.stem in imported_stems
            kind, emoji = classify(info, is_imp)
            # rank for display
            rank = {"ENTRYPOINT":0,"SUPPORTING":1,"ORPHAN":2,"STUB":3,"BROKEN":4}.get(kind, 2)
            scored.append((rank, f, info, kind, emoji, is_imp))
        scored.sort(key=lambda x: (x[0], x[1].name.lower()))
        for _, f, info, kind, emoji, is_imp in scored:
            if info is None: continue
            doc = (info["doc"] or "")[:70]
            how = ""
            if kind=="ENTRYPOINT": how = f"→ python3 {f.name} --help"
            elif kind=="SUPPORTING": how = f"→ from {f.stem} import {info['funcs'][0] if info['funcs'] else '...'}"
            elif kind=="ORPHAN": how = "→ solo (nobody imports it yet)"
            elif kind=="BROKEN": how = "→ fix syntax first"
            elif kind=="STUB": how = "→ stub (<10L or TODO)"
            print(f"│  {emoji} {f.name:<28} {kind:<11} {info['n_lines']:>4}L  {how}")
            if doc: print(f"│     {doc}")
            # only verbose for entrypoints/supporting — keep compact
    if subdirs:
        print("│")
        print("│  WHERE TO CD NEXT — subdirs worth touring")
        print("│  ─────────────────────────────────────────")
        for d in subdirs[:12]:
            count = len(list(d.glob("*.py"))) + len(list(d.glob("**/*.py")))
            # peek curator
            has_cur = (d / "CURATOR.md").exists()
            tag = "📖 CURATOR" if has_cur else "  "
            # quick one-liner
            b = readme_blurb(d)[:55] if d else ""
            if not b:
                # fallback: most recent py
                pys=list(d.glob("*.py"))
                if pys: b = analyze_py(pys[0])["doc"][:55] if analyze_py(pys[0]) else ""
            print(f"│  cd {d.name:<22} {count:>3} .py  {tag}  {b}")

    # bottom help
    print("│")
    print("│  USE CASES (how you actually use this folder)")
    if files:
        # pick most important entrypoint or supporting as example
        example = None
        for _, f, info, kind, _, _ in scored:
            if kind in ("ENTRYPOINT","SUPPORTING"):
                example=(f,info); break
        if example:
            f, info = example
            uses=infer_use_cases(info)
            print(f"│  Primary: {uses[0]}")
            print(f"│  Second : {uses[1]}")
            print(f"│  Third  : {uses[2]}")
            print(f"│  Alt    : {infer_alternate(info)}")
            print(f"│  Edge   : {infer_edges(info)}")
        else:
            print("│  No runnable script here — this folder is docs/archive/subdirs. cd into a subdir.")
    else:
        print("│  cd into a subdir above, then `sherpa` again.")

    # force multiplier — detect duplicate stems (humane cannibal signal)
    stems={}
    for f in files:
        stem=f.stem.rsplit("_v")[0].rsplit("_")[0].lower() if "_v" in f.stem or f.stem.count("_")>1 else f.stem.lower()
        # simpler: group by base before _v or _backup
        base=f.stem.split("_v")[0].split("_backup")[0].split("_old")[0]
        stems.setdefault(base, []).append(f.name)
    dupes=[(k,v) for k,v in stems.items() if len(v)>1]
    if dupes:
        print("│")
        print("│  ⚡ FORCE MULTIPLIER — dupe stems found (humane_cannibal can graft):")
        for k,v in dupes[:3]:
            print(f"│     {k}: {', '.join(v[:4])} → hc --dry-run to preview graft")
    print("│")
    print("│  TRY:  sherpa --write   (leave CURATOR.md so you remember after sleep)")
    print("│       where-was-i       (today\'s trail so you don\'t have to remember)")
    print("│       c                 (short for sherpa)")
    print("│       sherpa --egg      (fartographer + loomy live here 🥚)")
    if write and files:
        print("│  ✓ CURATOR.md written below (folder now remembers for you)")

def write_curator_md(root: Path):
    root=root.resolve()
    rel = "~/" + str(root.relative_to(HOME)) if str(root).startswith(str(HOME)) else str(root)
    files=find_py_here(root)
    subdirs=find_subdirs(root)
    imported_stems=importers_of(root, files)
    branch, git_lines = git_status(root)
    blurb=readme_blurb(root)

    md=[]
    md.append(f"# CURATOR — {root.name}")
    md.append(f"*Sherpa left this so you don't have to remember. Last tour: {datetime.now().isoformat()}*")
    md.append(f"*Path: `{rel}`*")
    md.append("")
    if blurb: md.append(f"> {blurb}")
    md.append("")
    md.append(f"**{len(files)} .py here, {len(subdirs)} subdirs.**" + (f" Git: `{branch}` with {len(git_lines)} modified files." if branch else ""))
    md.append("")

    if files:
        md.append("## What runs vs what supports")
        md.append("")
        md.append("| Script | Type | Lines | How to use | What it does |")
        md.append("|---|---|---:|---|---|")
        for f in sorted(files, key=lambda x: x.name.lower()):
            info=analyze_py(f)
            if not info: continue
            kind,_ = classify(info, f.stem in imported_stems)
            doc = (info["doc"] or "(see file)").replace("|","/")[:80]
            how = ""
            if kind=="ENTRYPOINT": how = f"`python3 {f.name} --help`"
            elif kind=="SUPPORTING": how = f"`from {f.stem} import {info['funcs'][0] if info['funcs'] else '...'}`"
            elif kind=="ORPHAN": how = "`solo — not imported`"
            elif kind=="BROKEN": how = "`fix syntax first`"
            else: how = "`stub`"
            md.append(f"| `{f.name}` | {kind} | {info['n_lines']} | {how} | {doc} |")
        md.append("")
        md.append("## Use cases, alternates, edges (per most important script)")
        # pick example
        scored=[]
        for f in files:
            info=analyze_py(f)
            kind,_ = classify(info, f.stem in imported_stems)
            rank={"ENTRYPOINT":0,"SUPPORTING":1}.get(kind, 9)
            scored.append((rank,f,info))
        scored.sort(key=lambda x: x[0])
        if scored and scored[0][0]<9:
            f,info=scored[0][1], scored[0][2]
            md.append(f"**Example: `{f.name}`** — {info['doc'] or ''}")
            md.append("")
            for i,u in enumerate(infer_use_cases(info),1): md.append(f"{i}. {u}")
            md.append("")
            md.append(f"- **Alternate use:** {infer_alternate(info)}")
            md.append(f"- **Edge / gotcha:** {infer_edges(info)}")
            md.append("")
        md.append("## Folder use cases")
        if any("boardroom" in (analyze_py(f)["doc"] or "").lower() for f in files if analyze_py(f)):
            md.append("- Primary: run a strategic boardroom (`vertical_ai.py --text \"idea\" --rounds 2 --cannibal`)")
            md.append("- Second: map or merge code (`codemap.py .` / `humane_cannibal.py . --dry-run`)")
            md.append("- Third: leave memory (`sherpa --write` → CURATOR.md so tomorrow-you remembers)")
        else:
            md.append("- Primary: tour here (`sherpa`), then `cd` into a subdir that looks useful")
            md.append("- Second: run the ENTRYPOINT script with `--help`")
            md.append("- Third: import a SUPPORTING script from a new script you write")
        md.append("")
    if subdirs:
        md.append("## Where to cd next")
        md.append("")
        for d in subdirs[:15]:
            has_cur = "📖" if (d / "CURATOR.md").exists() else "·"
            b = readme_blurb(d)[:90] or "(no blurb yet)"
            md.append(f"- `{d.name}/` {has_cur} — {b}")
        md.append("")
    md.append("## ⚡ Force multiplier (extra innings)")
    md.append("")
    md.append("- `hc --dry-run` — preview humane merge (winner grafted, losers archived — never deleted)")
    md.append("- `cm` — codemap stats right here, no html/browser")
    md.append("- `sherpa --egg` — fartographer/loomy easter egg (you were right both times)")
    md.append("")

    md.append("## How to stay in terminal (no copy, no browser)")
    md.append("")
    md.append("```bash")
    md.append("sherpa          # tour here")
    md.append("c               # short for sherpa")
    md.append("sherpa --write  # leave CURATOR.md (this file) — folder remembers for you")
    md.append("where-was-i     # today's trail (no memory needed)")
    md.append("tour ~/tools    # tour any path without cd")
    md.append("```")
    md.append("")
    md.append(f"*Generated by Sherpa on {date.today().isoformat()} — named by Bleak, built humane (no delete, just tour). Previous fartographer/cartographer/Loomy ideas merged here so one name sticks: `sherpa`.*")
    md.append("")

    out = root / "CURATOR.md"
    out.write_text("\n".join(md), encoding="utf-8")
    # also log
    try:
        HISTORY.parent.mkdir(exist_ok=True)
        with open(HISTORY,"a") as fh: fh.write(json.dumps({"ts":datetime.now().isoformat(),"root":str(root),"files":len(files),"subdirs":len(subdirs)})+"\n")
        with open(TODAY,"a") as fh: fh.write(f"- {datetime.now().strftime('%H:%M')} `{rel}` — {len(files)} py, {len(subdirs)} subdirs — {blurb[:60]}\n")
    except: pass
    return out

def log_visit(root: Path):
    try:
        HISTORY.parent.mkdir(exist_ok=True)
        with open(HISTORY,"a") as fh: fh.write(json.dumps({"ts":datetime.now().isoformat(),"root":str(root.resolve()),"files":len(list(root.glob('*.py')))})+"\n")
        with open(TODAY,"a") as fh:
            rel = "~/" + str(root.resolve().relative_to(HOME)) if str(root.resolve()).startswith(str(HOME)) else str(root.resolve())
            fh.write(f"- {datetime.now().strftime('%H:%M')} `{rel}`\n")
    except: pass

def main():
    ap=argparse.ArgumentParser(description="Sherpa — humane codebase tour guide (stays in terminal)")
    ap.add_argument("path", nargs="?", default=".", help="path to tour (default: .)")
    ap.add_argument("--write", action="store_true", help="also write CURATOR.md in that folder")
    ap.add_argument("--json", action="store_true", help="machine-json output")
    args=ap.parse_args()
    root=Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"No such path: {root}", file=sys.stderr); sys.exit(1)
    if args.json:
        files=find_py_here(root)
        data={"root":str(root),"files":[{"name":f.name,"n_lines":analyze_py(f)["n_lines"] if analyze_py(f) else 0,"doc":analyze_py(f)["doc"] if analyze_py(f) else "", "kind":classify(analyze_py(f), f.stem in importers_of(root, files))[0]} for f in files]}
        print(json.dumps(data, indent=2))
        return
    render_terminal(root, write=args.write)
    if args.write:
        out=write_curator_md(root)
        print(f"\nWrote {out} — folder now remembers for you after sleep.")
    else:
        log_visit(root)

if __name__=="__main__": main()
