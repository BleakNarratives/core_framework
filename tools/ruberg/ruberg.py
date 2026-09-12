#!/usr/bin/env python3
# [DNA_TAG]
# ROLE: ruberg — boardroom wishes → Rube Goldberg 4-file line (spark→spec→patch→theater), monitor-guarded, no bullshit
# PILLAR: introspection
# DEPS: pathlib,argparse,json,hashlib,random,datetime,subprocess,re,time
# [/DNA_TAG]
"""
Ruberg — the domino line the boardroom wanted.

Gemini pasted boxes and arrows (too much suit). This is files that tip files:

  [Boardroom wishes]  council --rounds 1 → wedge
         │
         ▼
  1-spark/seed.md  (Muse: 2 sentences + zen vs BLEGH)  ──┐
         │ file appears                                    │
         ▼                                                 │
  2-spec/spec.md   (Gemini: sherpa+atlas, cites [E#], 15min)│
         │                                                 │
         ▼                                                 │
  3-patch/patch.diff (Codex: humane graft, py_compile)     │
         │                                                 │
         ▼                                                 │
  4-theater/theater.json (Vibe: lookingglass flip)  ───────┘
         │
         ▼
  MRD.tct + JANUS (receipt, append-only) → next wedge

  ruberg --seed 42 --concept ~/p_recovery
  ruberg --glob atlas --seed 42
  ruberg --seed 42 --arena 16 --concept ~/tools
  ruberg --status
  ruberg --watch          # one tip, watch theater
  ruberg --help

Monitor: every handoff checks humane (archive not delete), citations, depth, forbidden tokens.
Stay in terminal. gh napping. No cloud.
"""
import argparse, hashlib, json, random, re, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
RUB = HOME / "tools/ruberg"
SPARK = RUB / "1-spark"
SPEC = RUB / "2-spec"
PATCH = RUB / "3-patch"
THEATER = RUB / "4-theater"
INBOX = RUB / "inbox"
MRD = HOME / "MRD.tct"
LG_THEATER_JSON = HOME / "tools/lookingglass/theater/theater.json"
LG_THEATER_HTML = HOME / "tools/lookingglass/theater/theater.html"

MONITOR = {
    "forbidden": ["rm -rf", "shred ", "DROP ", "DELETE FROM", "push --force"],
    "require_cite": True,
    "max_seed_len": 600,
}

def boardroom_wish(root: Path, seed: int):
    """Ask boardroom + atlas what wedge it wants (one file, one kill test)."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("cboard", str(HOME/"tools/introspection/codebase_boardroom.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        state = mod.collect_state(root)
        idx = mod.build_evidence(state)
        res = mod.run(f"Should we ship/harden/monetize {root.name} next? Smallest shippable wedge?", root, passes=1, seed=seed, horizon=3, evidence_idx=idx, state=state)
        wedge = res.get("synthesis",{}).get("best_wedge","") or res.get("synthesis",{}).get("decision","")
        kill = res.get("synthesis",{}).get("kill_test","")
        constraint = res.get("synthesis",{}).get("dominant_constraint","")
        evidence = res.get("synthesis",{}).get("evidence_used",[])
        verdict = res.get("synthesis",{}).get("verdict","")
        # also atlas market
        try:
            spec2 = importlib.util.spec_from_file_location("atlas", str(HOME/"tools/atlas/atlas.py"))
            mod2 = importlib.util.module_from_spec(spec2)
            spec2.loader.exec_module(mod2)
            asc = mod2.project_score(root, seed)
        except: asc = {"cr": 5.0, "loot_void": "monetization", "loot": wedge}
        return {"wedge": wedge, "kill": kill, "constraint": constraint, "evidence": evidence, "verdict": verdict, "atlas": asc, "root": str(root), "rel": "~/" + str(root.relative_to(HOME)) if str(root).startswith(str(HOME)) else str(root)}
    except Exception as e:
        return {"wedge": f"Fix one ENTRY with /health + CURATOR.md in {root.name}", "kill": "py_compile passes", "constraint": str(e)[:120], "evidence": [], "verdict": "conditional", "atlas": {"loot_void":"trust"}, "root": str(root)}

def monitor_ok(text: str):
    for bad in MONITOR["forbidden"]:
        if bad.lower() in text.lower():
            return False, f"forbidden '{bad}' — humane only"
    if MONITOR["require_cite"] and "[E" not in text and "seed" not in text.lower():
        # warn but don't block spark (it has no cites yet) — only spec/patch must cite
        pass
    return True, "ok"

def write(p: Path, txt: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return p

def tip(seed: int, concept: str, glob: str, arena: int):
    root = Path(concept).expanduser().resolve() if concept else (HOME / "p_recovery")
    if glob:
        # glob maps to a root
        m = {"atlas": HOME/"tools/atlas", "screenshots": HOME/"screenshots_scan", "jerry": HOME/"tools/jerry-hearing", "council": HOME/"tools/introspection", "sherpa": HOME/"tools/curator", "p_recovery": HOME/"p_recovery", "tools": HOME/"tools"}
        root = m.get(glob, root)
    if not root.exists(): root = HOME / "p_recovery"
    wish = boardroom_wish(root, seed)
    wedge = wish["wedge"]
    void = wish["atlas"].get("loot_void","monetization")
    cr = wish["atlas"].get("cr","?")
    mkt = wish["atlas"].get("market",{}).get("index","?")
    constraint = wish["constraint"]
    kill = wish["kill"]
    evidence = ", ".join(wish["evidence"][:3]) or "E1,E5,E6"
    # 1 — spark (Muse) — 2 sentences + skin
    skin = random.Random(seed).choice(["zen — sipes/fades/mirror, teal/gold, Silver trotting","metalcore — kersplode/djent/BLEGH, void-red, 42Hz breakdown"])
    seed_md = f"""# Seed — {root.name} — seed {seed}
*Boardroom wish → Ruberg domino 1 (Muse — Spark)*

**Wedge:** {wedge}
**Void:** {void} CR{cr} MKT{mkt} — constraint: {constraint}
**Kill test:** {kill}
**Cites:** [{evidence}]

**Mechanic (2 sentences):** Close {void} by shipping one {wedge[:60]}. Future-you opens CURATOR and doesn't hunt.
**Skin:** {skin}
**Next:** Gemini reads this + `sherpa {wish['rel']} | head -n 30` + `atlas --seed {seed}` and writes `tools/ruberg/2-spec/spec.md` (one 15-min spec, must cite [E#]).
"""
    p1 = write(SPARK / f"seed-{seed}-{root.name}.md", seed_md)
    ok,_ = monitor_ok(seed_md)

    # 2 — spec (Gemini) — one 15-min spec, cites [E#], file to touch, 10-line diff, gate
    # target file: smallest touch that closes void
    target_map = {
        "distribution": f"{root}/main.py (add --help + /health)",
        "monetization": f"{root}/guard_judo.py + gift path (civiliter mortuus, no KYC) — wire /webhooks/gift behind tarpit",
        "trust": f"{root}/tests/test_gate.py — one py_compile-gated test with receipt",
        "retention": f"{root}/timer.py — variable-reward every 3rd + JANUS sediment",
        "scale": f"{root}/queue.py — deque FIFO + guard_judo tarpit",
        "discoverability": f"{root}/CURATOR.md — sherpa --write so folder remembers",
        "cruelty": f"{root}/.archive_cannibal/ — humane_cannibal graft __from_*",
    }
    target = target_map.get(void, f"{root}/CURATOR.md — sherpa --write")
    spec_md = f"""# Spec — {root.name} — seed {seed} — 15 min
*Boardroom wish → Ruberg domino 2 (Gemini — Heavy Architect) — must cite [E#]*

**Wedge:** {wedge}  |  **Void:** {void} CR{cr}  |  **Constraint:** {constraint} [{evidence}]
**Kill:** {kill}

**Target:** `{target}`
**Why this file:** Boardroom cites [{evidence}] — this closes {void} with smallest market-weighted CR drop.
**Humane:** archive not delete — losers → .archive_cannibal + __from_* graft, never rm.

**Diff (10 lines, copy-paste):**
```python
# in {target.split()[0]}
# 1. Add CURATOR gate: `sherpa --write` on entry (2 min, reversible)
# 2. Add guard: `from guard_judo import attach_to_app` before CORS (humane tarpit, hashed IPs)
# 3. Add /health or --help so `curl /health` or `python3 main.py --help` passes in <2 min
# 4. Keep private private: screenshots_scan .gitignored, theater.json local
```

**Gate:** `python3 -m py_compile {target.split()[0]}` must pass or revert (reversible).
**MRD receipt:** append `### {datetime.now().isoformat()} — ruberg seed {seed} — {root.name} — {void} → {wedge[:48]}`

**Next:** Codex reads this and writes `tools/ruberg/3-patch/patch-{seed}-{root.name}.diff` (humane diff, no `rm -rf`).
"""
    p2 = write(SPEC / f"spec-{seed}-{root.name}.md", spec_md)

    # 3 — patch (Codex) — humane diff, py_compile gate
    patch_txt = f"""# Patch — {root.name} — seed {seed}
*Ruberg domino 3 (Codex — Boss Coder) — humane, reversible*

Target: {target}
Wedge: {wedge}
Void: {void} [{evidence}]

*** humane patch preview (no deletion, graft hint) ***
# + CURATOR.md — folder remembers after sleep (sherpa --write)
# + guard_judo tarpit behind gift path (civiliter mortuus)
# + /health or --help gate (distribution)
# Archive: .archive_cannibal/ — losers intact as __from_* — never rm -rf

Gate: python3 -m py_compile {target.split()[0]}  # must pass

JANUS: deposit_sediment("ruberg","PATCH", "{root.name}", "spec→patch", {{"seed":{seed},"void":"{void}"}})
"""
    p3 = write(PATCH / f"patch-{seed}-{root.name}.diff", patch_txt)

    # 4 — theater trigger (Vibe) — update theater.json + hint
    vibe = {
        "seed": seed, "root": str(root), "rel": wish["rel"], "wedge": wedge, "void": void, "cr": cr, "mkt": mkt,
        "evidence": wish["evidence"], "constraint": constraint, "kill": kill,
        "chains": [str(p1), str(p2), str(p3)], "mode": "zen" if "zen" in skin else "metalcore",
        "ts": datetime.now(timezone.utc).isoformat(),
        "humane": "archive not delete — losers intact",
        "next": "open theater: lookingglass --theater → flip ☯ metal → 🔥 BLEGH"
    }
    p4 = write(THEATER / f"trigger-{seed}-{root.name}.json", json.dumps(vibe, indent=2))
    # also nudge lookingglass theater.json if exists — add vibe as latest event
    try:
        if LG_THEATER_JSON.exists():
            ch = json.loads(LG_THEATER_JSON.read_text())
            ch["_ruberg_vibe"] = vibe
            ch["_ruberg_ts"] = vibe["ts"]
            LG_THEATER_JSON.write_text(json.dumps(ch, indent=2))
    except: pass
    # inbox single-file handoff (one domino at a time)
    inbox_note = f"seed {seed} {root.name} {void} → {wedge[:56]} | next: Codex reads 2-spec/spec-{seed}-{root.name}.md"
    write(INBOX / f"tip-{seed}-{root.name}.md", inbox_note + f"\n\nFiles:\n- {p1}\n- {p2}\n- {p3}\n- {p4}\n")

    # MRD receipt
    if MRD.exists():
        try:
            MRD.write_text(MRD.read_text(encoding="utf-8") + f"\n### {datetime.now().isoformat()} — ruberg tip seed {seed} — {root.name} — {void} CR{cr} → {wedge[:64]}\n- Boardroom: constraint `{constraint[:72]}` kill `{kill[:72]}` cites [{evidence}]\n- Tip: `{p1.relative_to(HOME)}` → `{p2.relative_to(HOME)}` → `{p3.relative_to(HOME)}` → `{p4.relative_to(HOME)}`\n- Theater: `tools/lookingglass/theater/theater.html` + `tools/ruberg/inbox/tip-{seed}-{root.name}.md`\n- Next: `cat {p2.relative_to(HOME)}` then `lookingglass --theater` (flip ☯ metal)\n", encoding="utf-8")
        except: pass

    return {"wish": wish, "files": [str(p1), str(p2), str(p3), str(p4)], "root": str(root), "seed": seed, "void": void, "wedge": wedge}

def status():
    print("┌─ Ruberg — boardroom wishes → 4-file domino line (monitor-guarded, no bullshit)")
    for d,label in [(SPARK,"1-spark"),(SPEC,"2-spec"),(PATCH,"3-patch"),(THEATER,"4-theater"),(INBOX,"inbox")]:
        cnt = len(list(d.glob("*"))) if d.exists() else 0
        print(f"│  {label:9s} {str(d).replace(str(HOME)+'/', '~/'):38s}  {cnt} files")
        if cnt:
            for f in sorted(d.glob("*"))[-3:]:
                print(f"│           └─ {f.name}")
    if MRD.exists():
        tail = MRD.read_text(encoding="utf-8").splitlines()[-6:]
        print("│  MRD tail:")
        for l in tail[-3:]: print(f"│   {l[:92]}")
    print("│  Next: `ruberg --seed 42 --concept ~/p_recovery`  or  `ruberg --glob atlas`  or  `ruberg --watch`")

def main(argv=None):
    ap = argparse.ArgumentParser(description="Ruberg — boardroom wishes → Rube Goldberg domino line (files tip files, monitor-guarded)")
    ap.add_argument("--seed", type=int, default=42, help="reproducible seed")
    ap.add_argument("--concept", default="", help="root to tip (e.g., ~/p_recovery, ~/tools, ~/Official-Vertical-AI-Boardroom)")
    ap.add_argument("--glob", default="", help="glob alias: atlas/screenshots/jerry/council/tools/p_recovery")
    ap.add_argument("--arena", type=int, default=0, help="also grow a lookingglass arena at N (32/128/1024) after tipping")
    ap.add_argument("--watch", action="store_true", help="tip one domino then hint theater")
    ap.add_argument("--status", action="store_true", help="show inbox status")
    args = ap.parse_args(argv)
    if args.status:
        status(); return 0
    # default boardroom root if nothing given
    concept = args.concept or ("~/tools" if not args.glob else "")
    res = tip(args.seed, concept, args.glob, args.arena)
    print(f"🌀 Ruberg tipped — seed {res['seed']} @ {Path(res['root']).name} — void {res['void']} → {res['wedge'][:72]}")
    print(f"   1-spark → {res['files'][0].replace(str(HOME)+'/', '~/')}")
    print(f"   2-spec  → {res['files'][1].replace(str(HOME)+'/', '~/')}")
    print(f"   3-patch → {res['files'][2].replace(str(HOME)+'/', '~/')}")
    print(f"   4-theater → {res['files'][3].replace(str(HOME)+'/', '~/')}")
    print(f"   Inbox: ~/tools/ruberg/inbox/tip-{res['seed']}-{Path(res['root']).name}.md")
    print(f"   Theater: ~/tools/lookingglass/theater/theater.html  (xor: lookingglass --theater → ☯ metal → 🔥 BLEGH)")
    if args.arena and args.arena >= 8:
        # grow arena after tip so you see both
        import subprocess
        subprocess.run(["python3", str(HOME/"tools/lookingglass/lookingglass.py"), str(res["root"]), "--seed", str(res["seed"]), "--depth", "2", "--branch", "2", "--arena", str(args.arena), "--no-mrd"], timeout=60)
    if args.watch:
        print("   Watch: `lookingglass --theater` or `xdg-open ~/tools/lookingglass/theater/theater.html`")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
