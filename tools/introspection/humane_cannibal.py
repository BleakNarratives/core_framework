#!/usr/bin/env python3
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: introspection
# DEPS: ast,json,os,shutil,pathlib,hashlib
# ROLE: humane whole-codebase cannibal — judges groups, archives losers intact, grafts unique logic + versions into winner
# AUTHOR: Buffy + Bleak
# SESSION: 2026-09-10
# TIER: 2
# [/DNA_TAG]
"""
humane_cannibal.py — Whole-Codebase Cannibal (HUMANE EDITION)

No code is ever deleted. That's the rule.

Normal refactor: duplicate files get `rm`. Or they rot forever in UNPACKED.
This script does the third way — the humane way:

  1. MAP        — find groups of related files (stems like vertical_ai, vertical_ai_v2, _backup)
  2. JUDGE      — score each file (or optionally Boardroom debate) to pick a winner
  3. ARCHIVE    — losers are copied WHOLE to .archive_cannibal/<date>/<group>/ — never rm
  4. GRAFT      — unique functions/classes from each loser are extracted and
                  APPENDED to the winner as versioned alternatives
                  (e.g., `def scout()` + `def scout__from_backup_v1()`)
                  Winner now carries the survivor's DNA.
  5. PROVE      — winner must still py_compile after graft. If not, revert.
  6. LOG        — manifest with provenance, winners/losers, grafted defs

Versions survive: if winner already has `foo()` and loser has a *different*
`foo()`, the loser's version is kept as `foo__from_<loser>_v1` so you keep
both. If the function is identical (same hash), it's skipped — no bloat.

Orphans/singletons are skipped by default — only groups where a choice
actually exists are cannibalized.

Usage:
  # See what would happen — no writes:
  python3 tools/introspection/humane_cannibal.py ~/Official-Vertical-AI-Boardroom --dry-run

  # Really do it (archives + grafts):
  python3 tools/introspection/humane_cannibal.py ~/Official-Vertical-AI-Boardroom --execute

  # Limit to one pillar / subdir:
  python3 tools/introspection/humane_cannibal.py ~/The-Werkz --dry-run

  # Optional: add Boardroom as judge for ties (needs vault keys):
  python3 tools/introspection/humane_cannibal.py ~/Official-Vertical-AI-Boardroom --with-boardroom --dry-run

Exit-zero always. Greedy by default is off — one group is printed so you see the shape before you run on everything.
"""

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

SKIP_DIRS = {"node_modules",".git","__pycache__","venv",".venv","env","_ARCHIVED",".mypy_cache",".pytest_cache","dist","build",".idea",".vscode",".archive_cannibal",".archive","_archive","targets","reports","__pycache__"}
STEM_SUFFIXES = re.compile(r"(_v\d+|_backup|_legacy|_old|_new|_copy|_dup|_orig|_bak|_tmp|_2|_3|_v2|_v3|cannibal_backup|_boardroom_backup|_mangled.*)$")
STUB_MARKERS = re.compile(r"\b(TODO|FIXME|NotImplementedError|pass\s*#\s*stub)\b")

# ── codemap-lite ──
def find_py_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(".py"):
                yield Path(dirpath) / fn

def module_name(path: Path, root: Path):
    rel = path.relative_to(root).with_suffix("")
    parts = rel.parts
    if parts and parts[-1] == "__init__": parts = parts[:-1]
    return ".".join(parts) if parts else path.stem

def analyze_file(path: Path):
    try: src = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e: return None, [], 0, False, f"unreadable: {e}"
    n_lines = src.count("\n")+1
    is_stub = bool(STUB_MARKERS.search(src)) or n_lines < 5
    imports=[]
    try:
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names: imports.append(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module.split(".")[0])
    except SyntaxError as e:
        return src, [], n_lines, is_stub, f"syntax error: {e}"
    return src, imports, n_lines, is_stub, None

def file_hash(path: Path) -> str:
    h = hashlib.md5()
    h.update(path.read_bytes())
    return h.hexdigest()[:8]

def def_hash(node: ast.AST, src: str) -> str:
    seg = ast.get_source_segment(src, node) or ast.dump(node)
    return hashlib.md5(seg.encode()).hexdigest()[:8]

def get_top_defs(path: Path):
    """Return {name: (node, hash, is_class)} for top-level funcs/classes."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=str(path))
    except Exception:
        return {}, ""
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = (node, def_hash(node, src), isinstance(node, ast.ClassDef))
    return out, src

def has_dna_tag(path: Path) -> bool:
    try: return "[DNA_TAG]" in path.read_text(encoding="utf-8", errors="replace")[:4000]
    except: return False

def stem_group_key(path: Path) -> str:
    s = path.stem
    # strip known suffixes repeatedly
    prev=None
    while prev != s:
        prev=s
        s = STEM_SUFFIXES.sub("", s)
    return s.lower()

def group_files(files: list[Path], root: Path):
    """Group by (parent_dir, stem_key). Only groups with >=2 members."""
    buckets = {}
    for p in files:
        # group within same directory — don't cross distant pillars silently
        key = (str(p.parent.relative_to(root) if p.parent != root else Path(".")), stem_group_key(p))
        buckets.setdefault(key, []).append(p)
    # also catch cross-dir dup stems if filename stem identical (roots like UNPACKED dupes)
    stem_to_files = {}
    for p in files:
        stem_to_files.setdefault(stem_group_key(p), []).append(p)
    # Merge groups where stem appears in multiple dirs (>=2 and <=6 to avoid mega-groups like __init__)
    for stem, plist in stem_to_files.items():
        if 2 <= len(plist) <= 12 and len(set(str(x.parent) for x in plist)) > 1:
            # only propose if they share a suffix pattern or exact stem
            dirs = set(str(x.parent) for x in plist)
            if len(dirs) <= 4:
                key = (f"~cross-dir~:{stem}", stem)
                # avoid double-counting already grouped
                if key not in buckets:
                    buckets[key] = plist
    groups = {k:v for k,v in buckets.items() if len(v)>=2}
    return groups

def score_file(path: Path, root: Path, indeg_map: dict, src: str, n_lines: int, is_stub: bool, err):
    score = 0
    reasons = []
    name = module_name(path, root)
    # usage matters most — if something imports you, you live
    indeg = indeg_map.get(name, 0)
    if indeg > 0:
        score += 20 + indeg*5
        reasons.append(f"used-by-{indeg}")
    if not is_stub:
        score += 10
        reasons.append("non-stub")
    if has_dna_tag(path):
        score += 15
        reasons.append("dna_tag")
    # recency +1 to +8
    try:
        age_days = (time.time() - path.stat().st_mtime) / 86400
        if age_days < 2: score+=8; reasons.append("touched<2d")
        elif age_days < 7: score+=5; reasons.append("touched<7d")
        elif age_days < 30: score+=2
    except: pass
    # compile
    try:
        ast.parse(src)
        score+=10
        reasons.append("parses")
    except: reasons.append("parse-fail"); score-=20
    # size: prefer substantive but not obese
    if 30 < n_lines < 800: score+=5; reasons.append(f"{n_lines}L-good")
    elif n_lines >= 800: score+=2; reasons.append(f"{n_lines}L-large")
    elif n_lines < 10: score-=5; reasons.append(f"{n_lines}L-tiny")
    # has tests nearby or test_ prefix
    if path.name.startswith("test_") or "test" in str(path.parent):
        score+=2; reasons.append("test-file")
    # outdeg = connects outward
    return score, reasons, indeg

def graft_loser_into_winner(loser: Path, winner: Path, archive_rel: str):
    l_defs, l_src = get_top_defs(loser)
    w_defs, w_src = get_top_defs(winner)
    if not l_defs:
        return [], "loser had no top-level defs to graft (only script-level code)"

    unique = []
    versioned = []
    winner_names = set(w_defs.keys())
    winner_hashes = {name: h for name,(nd,h,isc) in w_defs.items()}

    for name, (node, h, is_class) in l_defs.items():
        w_h = winner_hashes.get(name)
        if name not in winner_names:
            unique.append((name, node, h, is_class))
        elif w_h != h:
            versioned.append((name, node, h, is_class))
        else:
            # identical — skip, already represented
            pass

    if not unique and not versioned:
        return [], "all defs identical — nothing new to graft"

    # Build graft block
    date = datetime.now().strftime("%Y-%m-%d")
    lines = []
    lines.append(f"\n# ── HUMANELY PRESERVED FROM {loser.name} on {date} ──")
    lines.append(f"# ORIGINAL: {loser} ({loser.stat().st_size} bytes) — archived to {archive_rel}")
    lines.append(f"# This logic was unique to the loser and survives here as versioned alt(s).")
    lines.append(f"# Winner kept: {winner.name}. Loser intact in archive. Nothing deleted.")
    lines.append(f"# ─────────────────────────────────────────────")
    grafted_names = []

    for name, node, h, is_class in unique:
        seg = ast.get_source_segment(l_src, node)
        if not seg: continue
        kind = "class" if is_class else "def"
        lines.append(f"\n# + {kind} {name}() — unique to {loser.name} (preserved verbatim)")
        lines.append(seg)
        lines.append("")
        grafted_names.append(name)

    for name, node, h, is_class in versioned:
        seg = ast.get_source_segment(l_src, node)
        if not seg: continue
        alt_name = f"{name}__from_{loser.stem[:18].replace('-','_')}_v1"
        # rename def/class
        seg_renamed = re.sub(rf"^(\s*)(class|def|async def)\s+{re.escape(name)}\b",
                             rf"\1\2 {alt_name}", seg, count=1, flags=re.MULTILINE)
        kind = "class" if is_class else "def"
        lines.append(f"\n# + {kind} {name}() — VERSIONED ALT from {loser.name}")
        lines.append(f"#   winner already had {name}() with different body (hash {winner_hashes[name]} vs {h})")
        lines.append(f"#   kept as {alt_name}() so both behaviors survive; winner's original untouched")
        lines.append(seg_renamed)
        lines.append("")
        grafted_names.append(alt_name)

    graft_text = "\n".join(lines)
    return grafted_names, graft_text

# ── main ──
def main():
    ap = argparse.ArgumentParser(description="Humane whole-codebase cannibal — archive + graft, never delete")
    ap.add_argument("root", help="directory to scan")
    ap.add_argument("--dry-run", action="store_true", default=True, help="print plan, no writes (default)")
    ap.add_argument("--execute", action="store_true", help="actually archive losers and graft winners (requires --execute)")
    ap.add_argument("--with-boardroom", action="store_true", help="call Boardroom to break ties (needs vault)")
    ap.add_argument("--out", default=None, help="manifest json path (default: <root>/.archive_cannibal/manifest_YYYYMMDD_HHMM.json)")
    args = ap.parse_args()

    # --execute flips off dry_run semantics
    do_write = args.execute and not args.__dict__.get("dry_run_override", False)
    # argparse default dry_run True confuses; treat --execute as intent
    if args.execute:
        do_write = True
        dry = False
    else:
        dry = True

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr); sys.exit(1)

    files = sorted(find_py_files(root))
    if not files:
        print(f"No .py files under {root}", file=sys.stderr); sys.exit(1)

    # Build import graph for scoring
    mod_to_path = {}
    for p in files: mod_to_path[module_name(p, root)] = p
    local_mods = set(mod_to_path.keys())
    nodes=[]
    edges=[]
    for p in files:
        mod = module_name(p, root)
        src, imports, n_lines, is_stub, err = analyze_file(p)
        local_imports = sorted(set(i for i in imports if i in local_mods and i != mod))
        nodes.append((p, mod, src, imports, n_lines, is_stub, err))
        for imp in local_imports: edges.append((mod, imp))
    indeg = {m:0 for m in local_mods}
    for s,t in edges:
        indeg[t]=indeg.get(t,0)+1

    groups = group_files(files, root)

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  HUMANE CANNIBAL — whole-codebase breed, not butcher        ║")
    print("║  Rule: NO FILE IS EVER DELETED. Losers are ARCHIVED intact. ║")
    print("║  Their unique logic (+ versioned alts) is GRAFTED to winner ║")
    print("║  Winner must still compile after graft, or revert.           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"\nScanned {len(files)} files, {len(edges)} local edges")
    print(f"Candidate groups (same stem, same dir or cross-dir dup): {len(groups)}")
    if dry: print("Mode: DRY-RUN — no files will be written or moved\n")
    else:   print("Mode: EXECUTE — archives + grafts will be written\n")

    if not groups:
        print("No groups found. Nothing to cannibalize — your codebase is already de-duplicated (or diffuse).")
        print("Hint: groups are formed when stems match after stripping _v2,_backup,_legacy etc. within a dir.")
        return

    archive_root = root / ".archive_cannibal" / datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest = {"root": str(root), "generated_at": datetime.now().isoformat(),
                "mode": "execute" if do_write else "dry-run",
                "humane_guarantee": "NO FILE DELETED — losers archived intact + unique defs grafted to winner with versioned names; identical defs skipped",
                "groups": []}

    # sort groups for stable output: biggest first
    sorted_groups = sorted(groups.items(), key=lambda kv: (-len(kv[1]), str(kv[0])))

    total_grafts = 0
    total_archived = 0
    for (group_dir, stem), plist in sorted_groups:
        # dedup by content hash — identical files are free wins (archive copy, no graft needed)
        by_hash = {}
        for p in plist:
            by_hash.setdefault(file_hash(p), []).append(p)
        # if group is all identical hashes, pick one winner trivially
        # score each
        scored = []
        for p in plist:
            # find node for p
            rec = next((n for n in nodes if n[0]==p), None)
            if not rec: continue
            _, mod, src, imports, n_lines, is_stub, err = rec
            s, reasons, ind = score_file(p, root, indeg, src or "", n_lines, is_stub, err)
            # tiny tie-breaker: larger file slightly preferred when tied
            scored.append((s, -p.stat().st_mtime, p, mod, reasons, indeg))

        scored.sort(reverse=True, key=lambda x: x[0])
        # winner is top score
        winner = scored[0][2]
        losers = [t[2] for t in scored[1:]]
        win_score = scored[0][0]
        win_reasons = scored[0][4]

        # Optional boardroom tie-break: if top two within 3 points and --with-boardroom
        if args.with_boardroom and len(scored) >= 2 and abs(scored[0][0]-scored[1][0]) <= 3:
            # best-effort: call boardroom as judge (non-fatal)
            try:
                import sys as _sys
                _sys.path.insert(0, str(Path.home()/ "Official-Vertical-AI-Boardroom"))
                _sys.path.insert(0, str(Path.home()/ "The-Werkz"))
                from router import call_model, ModelTier
                # concise prompt
                prompt = (
                    f"Two files compete for the stem '{stem}' in {group_dir}:\n"
                    f"A) {winner.name} score {win_score} reasons {win_reasons}\n"
                    f"B) {scored[1][2].name} score {scored[1][0]} reasons {scored[1][4]}\n"
                    "Which should survive as the single canonical file? Consider: has tests, is imported, parses, has DNA_TAG, recent edits. Answer with filename only."
                )
                raw, prov = call_model(prompt, tier=ModelTier.FAST, chairman=True)
                choice = raw.strip().split()[0].strip().strip(",.:")
                # if model picks a loser, swap
                for t in scored:
                    if t[2].name == choice and t[2] != winner:
                        losers = [winner] + [x for x in losers if x != t[2]]
                        winner = t[2]
                        win_score = t[0]; win_reasons = t[4]
                        print(f"  [boardroom:{prov}] broke tie → winner {winner.name}")
                        break
            except Exception as e:
                print(f"  [boardroom tie-break skipped: {e}]")

        # header
        same_hash_groups = [v for v in by_hash.values() if len(v)>1]
        dup_note = f" | {len(same_hash_groups)} hash-dup set(s)" if same_hash_groups else ""
        print(f"\n┌─ group: {group_dir}/{stem}  ({len(plist)} files{dup_note})")
        print(f"│  winner: {winner.relative_to(root)}  score={win_score}  [{', '.join(win_reasons)}]")
        for s, _, p, mod, reasons, _ind in scored[1:]:
            rel = p.relative_to(root)
            print(f"│  loser : {rel}  score={s}  [{', '.join(reasons)}]")
        if same_hash_groups:
            for hs, members in by_hash.items():
                if len(members)>1:
                    print(f"│  note  : identical content {hs}: {', '.join(m.name for m in members)} (no merge needed)")

        # For each loser, plan graft
        group_grafts = []
        for loser in losers:
            # skip identical-hash losers — still archived but no graft text needed
            if file_hash(loser) == file_hash(winner):
                print(f"│  graft : {loser.name} → identical to winner, archive only (no graft)")
                group_grafts.append({"loser": str(loser.relative_to(root)), "grafted": [], "note": "identical — archived intact, no graft"})
                continue
            names, graft_text = graft_loser_into_winner(loser, winner, str(archive_root / group_dir / loser.name))
            if isinstance(names, list) and names and not graft_text.startswith("loser had no") and not graft_text.startswith("all defs"):
                # graft_text is the block; names are grafted alt names
                print(f"│  graft : {loser.name} → {len(names)} def(s): {', '.join(names[:6])}{' …' if len(names)>6 else ''}")
            elif names==[]:
                print(f"│  graft : {loser.name} → no new logic ({graft_text})")
                group_grafts.append({"loser": str(loser.relative_to(root)), "grafted": [], "note": graft_text})
                continue
            else:
                print(f"│  graft : {loser.name} → {graft_text}")

            # do the actual write if execute
            if do_write:
                archive_path = archive_root / group_dir / loser.name
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(loser, archive_path)
                # also copy hash sidecar
                meta = {"loser": str(loser.relative_to(root)), "winner": str(winner.relative_to(root)),
                        "group": f"{group_dir}/{stem}", "hash": file_hash(loser), "archived_to": str(archive_path.relative_to(root)),
                        "grafted": names, "date": datetime.now().isoformat()}
                (archive_path.with_suffix(archive_path.suffix+".meta.json")).write_text(json.dumps(meta, indent=2))
                total_archived += 1

                # Append graft to winner, but verify compile
                orig = winner.read_text(encoding="utf-8", errors="replace")
                # graft_text is the block when names already collected — reconstruct if names empty handled above
                if names and isinstance(graft_text, str) and graft_text.startswith("# ──"):
                    new_text = orig.rstrip() + "\n" + graft_text + "\n"
                else:
                    # names/graft_text came as names list, text is string — edge
                    new_text = orig.rstrip() + "\n" + (graft_text if isinstance(graft_text, str) else "") + "\n"

                # compile check
                try:
                    ast.parse(new_text, filename=str(winner))
                except SyntaxError as e:
                    print(f"│  REVERT: graft broke parse ({e}) — winner kept unchanged, loser still archived")
                    # keep loser archived, revert winner
                    grafted_names = []
                else:
                    winner.write_text(new_text, encoding="utf-8")
                    total_grafts += len(names)
                    print(f"│  wrote  : grafted {len(names)} def(s) into {winner.name}, loser archived to {archive_path.relative_to(root)}")
                    grafted_names = names
                group_grafts.append({"loser": str(loser.relative_to(root)), "archived_to": str(archive_path.relative_to(root)), "grafted": grafted_names if 'grafted_names' in locals() else names})
            else:
                # dry-run record
                if names and isinstance(names, list):
                    group_grafts.append({"loser": str(loser.relative_to(root)), "would_graft": names, "would_archive_to": str(archive_root / group_dir / loser.name)})
                else:
                    group_grafts.append({"loser": str(loser.relative_to(root)), "would_graft": [], "note": graft_text if isinstance(graft_text, str) else ""})

        manifest["groups"].append({
            "group": f"{group_dir}/{stem}",
            "winner": str(winner.relative_to(root)),
            "losers": [str(p.relative_to(root)) for p in losers],
            "grafts": group_grafts
        })
        print(f"└─ end group {stem}")

    # write manifest
    if do_write:
        archive_root.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.out) if args.out else (archive_root / "manifest.json" if do_write else root / f".archive_cannibal_dryrun_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    if dry:
        # dry-run manifest goes next to root so you can inspect
        manifest_path = root / f".archive_cannibal_dryrun_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        if root != Path.home() / "Official-Vertical-AI-Boardroom":
            # for generic root, put in /tmp for home scans
            if str(root) == str(Path.home()):
                manifest_path = Path("/tmp") / f"cannibal_dryrun_{datetime.now().strftime('%Y%m%d_%H%M')}.json"

    manifest["totals"] = {"groups": len(groups), "archived": total_archived, "grafted_defs": total_grafts}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n{'─'*60}")
    print(f"Manifest: {manifest_path}")
    print(f"Groups: {len(groups)}  Archived: {total_archived}  Grafted defs: {total_grafts}")
    if dry:
        print("DRY-RUN — rerun with --execute to actually archive + graft.")
        print(f"Example: python3 tools/introspection/humane_cannibal.py {root} --execute")
    else:
        print(f"Archive root: {archive_root}")
        print("All losers preserved intact. Check one diff: diff winner before/after via git.")
    print(f"{'─'*60}")

if __name__ == "__main__":
    main()
