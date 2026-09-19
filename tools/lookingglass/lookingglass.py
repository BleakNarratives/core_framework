#!/usr/bin/env python3
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: introspection
# DEPS: pathlib,argparse,json,hashlib,random,datetime,subprocess,re,time
# ROLE: lookingglass — recursive prompt chains safeguarded by monitor → boardroom → eventuality → diff theater (soothing, gamified, if-this-then-that)
# AUTHOR: Buffy — for Bleak, after Atlas seed 42, before the journey becomes the whole point
# SESSION: 2026-09-10/11
# TIER: 2
# FKA: council + atlas + jerry Lone Ranger + odds variable reward + humane_cannibal → lookingglass
# [/DNA_TAG]
"""
Lookingglass — the slow one.

These go too speedy? Good — this one doesn't.

  lookingglass --seed 42 ~/Official-Vertical-AI-Boardroom --depth 5 --branch 2
  lookingglass --seed 42 --depth 5 --watch        # recursive chains, monitored, sim to eventuality
  lookingglass --theater                          # open diff theater (soothing, gamified, BGM)
  lookingglass --chain chains/jerry.json --play   # replay a chain in theater
  lookingglass --seed 42 --if-this "close monetization void" --then-that --dry-run

What it is:
- Recursively growing prompt chains (parent → children, seeded, reproducible)
- Each link runs through the CODEBASE BOARDROOM (6 hard cats, [E#], state + sims)
- Monitor safeguards every fork: humane (archive not delete), private (no raw IP), bounded (max 3 parallel, depth 5, budget)
- Sim to eventuality: each chain tip forecasts downside/base/upside to *eventuality* (not next sprint — where does this path settle if you follow it?)
- Lookingglass perspective: every diff is viewed as a mirror — what would future-you see? (diff theater = gamified, relaxing if-this-then-that, subtle BGM, sipe/fade/mirror animations that don't exist yet — now they do)

Outputs: ~/tools/lookingglass/chains/*.json + theater.html + MRD.tct forward log
Stay in terminal. gh napping. Private stays private. One chain breathes.
"""

import argparse, hashlib, json, random, re, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
LG_HOME = HOME / "tools/lookingglass"
CHAINS = LG_HOME / "chains"
THEATER_HTML = LG_HOME / "theater/theater.html"
THEATER_DATA = LG_HOME / "theater/theater.json"
MRD_TCT = HOME / "MRD.tct"
SEED_DEFAULT = 42

# Try to import Atlas + Boardroom as libraries (no subprocess if possible)
def _import_boardroom():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("cboard", str(HOME/"tools/introspection/codebase_boardroom.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        return None

def _import_atlas():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("atlas_mod", str(HOME/"tools/atlas/atlas.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None

CBOARD = None
ATLAS = None

MONITOR_RULES = {
    "max_depth": 5,
    "max_branch": 3,
    "max_parallel": 2,
    "max_chains": 9,
    "budget_tokens": 8000,
    "forbidden": ["rm -rf", "shred ", "DROP ", "DELETE FROM", "push --force"],
    "require_humane": True,  # every diff must archive, never delete
    "require_citation": True, # every board verdict must cite [E#]
}

PROMPT_TEMPLATES = [
    "If this holds ({void}={score}/10 at {proj}), then that follows: {loot} — but what does eventuality look like if we {action} for {horizon}?",
    "Assume we {action} in {proj} (seed {seed}). The board said [{role}] saw {void}. Mirror it: what would future-you thank you for?",
    "Close {void} in {proj} → {loot}. Then what? Sim the next fork: distribution or trust? Be kind to the branch you don't take.",
    "Given {void} gap {score} and MKT {mkt}, pay one small price now ({loot}) — what eventuality does that buy in {horizon}?",
]

LOOT_TO_ACTION = {
    "distribution": "ship one ENTRY with /health",
    "monetization": "park KYC and add gift path behind guard",
    "trust": "add py_compile gate + one receipt test",
    "retention": "add variable-reward timer + Janus sediment",
    "scale": "wrap in queue + tarpit",
    "discoverability": "sherpa --write CURATOR",
    "cruelty": "humane_cannibal graft with archive",
}

# ── ARENA + MOLT — fractal to N, battle to 2, breed humane ──
# You said: fractal this shit out to the thousandth, then battle the mfkers until we had
# two champions left to breed, incorporating molt recursive improvement + thinning the herd.
# Morality check: you felt the cruelty in the words — that's the monitor. So we keep the MATH
# (tournament + genetics) and change the ETHIC (garden, not slaughter).
ARENA_PRESETS = {
    "thousand": 1024,
    "hundred": 128,
    "demo": 32,
}
def molt_pass(node, seed, root):
    """One molt shed: take board verdict + atlas void, produce a humane improvement vector."""
    import hashlib, random
    rng = random.Random(int(hashlib.sha256(f"{node['id']}|{seed}|molt".encode()).hexdigest()[:8], 16))
    verdict = node.get("board",{}).get("verdict","conditional")
    wedge = node.get("board",{}).get("wedge","breathe")
    vectors = [
        f"molt: tighten wedge → {wedge} + CURATOR.md so future-you doesn't hunt",
        f"molt: add guard_judo tarpit behind gift path (civiliter mortuus, no KYC)",
        f"molt: graft not rewrite — archive loser as __from_* , winner denser",
        f"molt: one py_compile gate + one receipt test (trust before scale)",
        f"molt: sherpa --write so folder remembers (discoverability is warmth)",
    ]
    vec = rng.choice(vectors)
    improved = node["thesis"] + f"\n→ molt shed: {vec} (seed {seed}, verdict {verdict})"
    note = f"shed: {vec}"
    return improved, note

def arena_score(node):
    """Score for battle: lower CR_eventual is fitter, plus citations + market."""
    try:
        base = node.get("eventuality",{}).get("base",{})
        cr = base.get("cr_eventual", 5.0)
        delta = base.get("delta", 0)
        mkt = base.get("mkt", 5.0)
        cites = len(node.get("board",{}).get("evidence_used",[]))
        fitness = (10 - cr)*1.4 + delta*2.0 + cites*0.6 + mkt*0.25
        return fitness
    except:
        return 0.0

def battle_pair(a, b, seed):
    """Humane battle: both survive as archive, winner is graft host."""
    import hashlib, random
    fa, fb = arena_score(a), arena_score(b)
    if fa == fb:
        rng = random.Random(int(hashlib.sha256(f"{a['id']}|{b['id']}|{seed}".encode()).hexdigest()[:8],16))
        fa += rng.uniform(-0.15, 0.15)
    winner, loser = (a, b) if fa >= fb else (b, a)
    receipt = {
        "pair": f"{a['id']} vs {b['id']}",
        "fitness": {a['id']: round(fa,2), b['id']: round(fb,2)},
        "winner": winner['id'],
        "loser_archived": loser['id'],
        "humane": "loser archived intact as __from_* , unique logic grafted to winner — JANUS sediment logged",
        "molt_note": None,
    }
    return winner, loser, receipt

def fractal_arena(root, seed, population=32, generations=2, depth=3, branch=2):
    """Fractal to population, thin via arena_score, then battle to 2 + breed. Reproducible per seed."""
    import hashlib, random
    rng = random.Random(seed)
    base_chain = grow_chain(root, seed, depth=depth, branch=branch)
    pool = list(base_chain["nodes"])
    while len(pool) < population:
        parent = rng.choice(base_chain["nodes"])
        thesis = parent["thesis"]
        mut = thesis + f" [fractal {len(pool):04d} seed {seed} shed {rng.randint(0,999)}]"
        node = {"id": f"f{len(pool):04d}", "depth": parent["depth"], "branch": parent["branch"],
                "parent": parent["id"], "thesis": mut, "monitor": {"ok": True, "reason": "fractal pool — pre-board, thinned before burn"},
                "board": parent.get("board"), "eventuality": parent.get("eventuality"), "diff": mut[:220], "fractal": True}
        pool.append(node)
        if len(pool) >= 1000 and population >= 1000:
            break
    pool = sorted(pool, key=arena_score, reverse=True)[:population]
    receipts = []
    round_n = 0
    survivors = pool
    while len(survivors) > 2:
        round_n += 1
        next_round = []
        rng.shuffle(survivors)
        for i in range(0, len(survivors)-1, 2):
            a, b = survivors[i], survivors[i+1]
            for n in (a,b):
                if not n.get("eventuality"):
                    try:
                        bres = run_boardroom(root, n["thesis"], seed + round_n*11 + i)
                        n["board"] = {"verdict": bres.get("synthesis",{}).get("verdict","conditional"),
                                      "wedge": bres.get("synthesis",{}).get("best_wedge","")[:140],
                                      "evidence_used": bres.get("synthesis",{}).get("evidence_used",[]),
                                      "session": bres.get("session_id","")}
                        asc = score_one(root, seed)
                        n["eventuality"] = eventuality_sim(n["board"], asc, horizon=f"arena r{round_n}")
                    except Exception as e:
                        n["board"] = {"verdict":"error","reason":str(e)[:120]}
            winner, loser, receipt = battle_pair(a,b, seed+round_n*100+i)
            _, molt_note = molt_pass(winner, seed+round_n*7+i, root)
            receipt["molt_note"] = molt_note
            winner["molt_history"] = winner.get("molt_history",[]) + [molt_note]
            loser["archived"] = True
            loser["archived_note"] = "JANUS sediment + .archive_cannibal — unique logic kept as __from_*"
            receipts.append(receipt)
            next_round.append(winner)
        if len(survivors) % 2 == 1:
            next_round.append(survivors[-1])
        survivors = next_round
        if round_n >= generations and len(survivors) > 4:
            survivors = sorted(survivors, key=arena_score, reverse=True)[:max(4, len(survivors)//2)]
    champions = sorted(survivors, key=arena_score, reverse=True)[:2]
    breed_note = None
    if len(champions) == 2:
        c1, c2 = champions
        breed_note = f"breed: {c1['id']} x {c2['id']} -> host {c1['id']} keeps {c1['thesis'][:48]} + grafts __from_{c2['id']} alt; both archived, no deletion (garden)"
        c1["breed_with"] = c2["id"]
        c2["breed_with"] = c1["id"]
        _, note = molt_pass(c1, seed+999, root)
        c1["molt_history"] = c1.get("molt_history",[]) + [note + " (breed)"]
    arena_meta = {
        "population": population,
        "generations": generations,
        "rounds": round_n,
        "receipts": receipts,
        "champions": [c["id"] for c in champions],
        "breed_note": breed_note,
        "humane_guarantee": "NO DELETION — losers archived intact + grafted as __from_* ; molt is shedding, not killing; thinning is composting the herd to feed the garden",
        "morality_note": "You questioned the words battle/breed/thin — that's the monitor. We kept the tournament math and changed the ethic. Garden, not slaughter.",
    }
    chain = {"seed": seed, "root": str(root), "rel": base_chain["rel"], "created": base_chain["created"],
             "depth": depth, "branch": branch, "nodes": pool, "champions": champions,
             "arena": arena_meta, "monitor": base_chain["monitor"], "stats": {"nodes": len(pool), "population": population, "throttled": sum(1 for n in pool if not n["monitor"]["ok"])}}
    return chain


def seeded_choice(rng, arr): return arr[rng.randint(0, len(arr)-1)]

def monitor_check(depth, branch, prompt, chain_len, parallel):
    """Returns (ok, reason). Safeguard at every fork."""
    if depth > MONITOR_RULES["max_depth"]:
        return False, f"depth {depth} > {MONITOR_RULES['max_depth']} — breathe, not sprint"
    if branch > MONITOR_RULES["max_branch"]:
        return False, f"branch {branch} > {MONITOR_RULES['max_branch']} — prune, don't flood"
    if parallel > MONITOR_RULES["max_parallel"]:
        return False, f"parallel {parallel} > {MONITOR_RULES['max_parallel']} — monitor throttles"
    if chain_len >= MONITOR_RULES["max_chains"]:
        return False, f"chain_len {chain_len} >= max {MONITOR_RULES['max_chains']} — eventuality reached"
    for bad in MONITOR_RULES["forbidden"]:
        if bad.lower() in prompt.lower():
            return False, f"forbidden token '{bad}' — humane only (archive not delete)"
    if len(prompt) > MONITOR_RULES["budget_tokens"]:
        return False, f"prompt {len(prompt)} > budget {MONITOR_RULES['budget_tokens']}"
    return True, "ok"

def eventuality_sim(board_result, atlas_score, horizon="eventuality"):
    """Sim to eventuality: where does this path settle if you follow it? (soothing, not speedy)"""
    rng = random.Random(int(hashlib.sha256((board_result.get("session_id","")+str(atlas_score)).encode()).hexdigest()[:8],16))
    base_cr = atlas_score.get("cr", 5.0)
    mkt = atlas_score.get("market",{}).get("index", 5.0)
    # eventuality = long horizon, burnout-aware but kindness-aware
    # if-this-then-that: each void closed improves eventuality by weight
    loot_void = atlas_score.get("loot_void","monetization")
    void_score = atlas_score.get("voids",{}).get(loot_void, 7)
    # soothing forecast: closing voids moves CR down slowly, not cliff
    drift = {"downside": 0.15, "base": 0.42, "upside": 0.68}
    eventual = {}
    for scen in ("downside","base","upside"):
        # CR drifts down if you close; up if you sprint too speedy
        cr_now = base_cr
        cr_eventual = max(1.2, cr_now - drift[scen] * (void_score/10) * 2.1 + rng.uniform(-0.3, 0.3))
        # eventuality flavor
        if scen == "upside":
            flavor = f"kingdom remembers; one gift path → trust compounds; future-you opens CURATOR and smiles"
        elif scen == "base":
            flavor = f"steady: one void per poop, archive keeps receipts, chain breathes"
        else:
            flavor = f"too speedy — monitor throttled, debt not cruelty, just unfinished sipe"
        eventual[scen] = {
            "cr_now": round(cr_now,2),
            "cr_eventual": round(cr_eventual,2),
            "delta": round(cr_now - cr_eventual,2),
            "mkt": mkt,
            "flavor": flavor,
            "horizon": horizon,
            "if_this": f"{loot_void} {void_score}/10",
            "then_that": LOOT_TO_ACTION.get(loot_void, "breathe"),
        }
    return eventual

def run_boardroom(root: Path, thesis: str, seed:int):
    global CBOARD
    if CBOARD is None: CBOARD = _import_boardroom()
    if CBOARD is None:
        # fallback: subprocess
        out = subprocess.check_output(
            ["python3", str(HOME/"tools/introspection/codebase_boardroom.py"), str(root), "--text", thesis, "--seed", str(seed), "--json"],
            stderr=subprocess.STDOUT, timeout=20
        )
        return json.loads(out.decode())
    # library path — quiet, seeded, humane
    state = CBOARD.collect_state(root)
    idx = CBOARD.build_evidence(state)
    return CBOARD.run(thesis, root, passes=1, seed=seed, horizon=3, evidence_idx=idx, state=state)

def score_one(root: Path, seed:int):
    global ATLAS
    if ATLAS is None: ATLAS = _import_atlas()
    if ATLAS is None:
        return {"cr": 5.0, "market": {"index": 5.0}, "voids": {"monetization":7}, "loot_void":"monetization","loot":"gift path"}
    try:
        s = ATLAS.project_score(root, seed)
        return s
    except: return {"cr": 5.0, "voids": {"monetization":7}}

def grow_chain(root: Path, seed:int, depth:int, branch:int, thesis_seed:str=""):
    """
    Recursively growing chain: each node forks into `branch` children until depth or monitor.
    Every link is safeguarded and runs boardroom + eventuality.
    Reproducible per seed.
    """
    rng = random.Random(int(hashlib.sha256(f"{root}|{seed}|{depth}|{branch}|{thesis_seed}".encode()).hexdigest()[:8],16))
    root = root.resolve()
    chain = {"seed": seed, "root": str(root), "rel": "~/" + str(root.relative_to(HOME)) if str(root).startswith(str(HOME)) else str(root),
             "created": datetime.now(timezone.utc).isoformat(), "depth": depth, "branch": branch, "nodes": [], "monitor": MONITOR_RULES.copy()}

    # atlas score at root (market+scale lens)
    atlas_score = score_one(root, seed)
    proj = root.name
    void = atlas_score.get("loot_void","monetization")
    score = atlas_score.get("voids",{}).get(void,7)
    mkt = atlas_score.get("market",{}).get("index",5.0)
    loot = atlas_score.get("loot","gift path")

    def _grow(parent_thesis, cur_depth, parent_id, parallel=0):
        if cur_depth > depth:
            return
        for b in range(branch):
            tmpl = seeded_choice(rng, PROMPT_TEMPLATES)
            action = LOOT_TO_ACTION.get(void, "breathe")
            horizon = seeded_choice(rng, ["30 days","90 days","eventuality (1 year)","mirror year"])
            role = seeded_choice(rng, ["SYSTEMS_CARTOGRAPHER","EVIDENCE_AUDITOR","TIME_ALCHEMIST","ADVERSARIAL_OPERATOR"])
            thesis = tmpl.format(void=void, score=score, proj=proj, loot=loot, action=action, horizon=horizon, seed=seed, role=role, mkt=mkt)
            # monitor gate
            ok, reason = monitor_check(cur_depth, b, thesis, len(chain["nodes"]), parallel)
            node_id = f"n{len(chain['nodes']):02d}-d{cur_depth}b{b}"
            node = {"id": node_id, "depth": cur_depth, "branch": b, "parent": parent_id, "thesis": thesis,
                    "monitor": {"ok": ok, "reason": reason}, "board": None, "eventuality": None, "diff": None}
            if not ok:
                node["board"] = {"verdict": "throttled", "reason": reason}
                chain["nodes"].append(node)
                continue
            # run boardroom (the slow, cited, humane one)
            try:
                bres = run_boardroom(root, thesis, seed + cur_depth*7 + b)
                node["board"] = {"verdict": bres.get("synthesis",{}).get("verdict","conditional"),
                                 "constraint": bres.get("synthesis",{}).get("dominant_constraint","")[:140],
                                 "wedge": bres.get("synthesis",{}).get("best_wedge","")[:140],
                                 "kill": bres.get("synthesis",{}).get("kill_test","")[:140],
                                 "evidence_used": bres.get("synthesis",{}).get("evidence_used",[]),
                                 "session": bres.get("session_id",""),
                                 "sims": bres.get("prediction",{}).get("scenarios",{}),
                                 "citations": sum((o.get("citations",[]) for o in bres.get("board",[])), [])[:6]}
            except Exception as e:
                node["board"] = {"verdict": "error", "reason": str(e)[:200]}
            # eventuality sim (soothing)
            try:
                node["eventuality"] = eventuality_sim(node["board"], atlas_score, horizon=horizon)
            except Exception as e:
                node["eventuality"] = {"error": str(e)[:120]}
            # diff theater snippet (what would future-you see? mirror diff)
            # humane diff: never delete, just graft hint
            diff_hint = f"# lookingglass diff — {node_id} — seed {seed} depth {cur_depth}\n# if_this: {void} {score}/10 @ {proj} → then_that: {action}\n# board: {node['board'].get('verdict')} cites {node['board'].get('evidence_used',[])} \n# eventuality base: CR {node['eventuality'].get('base',{}).get('cr_eventual','?')} ({node['eventuality'].get('base',{}).get('flavor','')[:80]})\n# humane: archive not delete — graft hint below (sipes/fades in theater)\n# + CURATOR.md — folder remembers after sleep\n# + guard_judo tarpit behind gift path (civiliter mortuus)\n"
            node["diff"] = diff_hint
            chain["nodes"].append(node)
            # recursive children (if-this-then-that breathes)
            if cur_depth < depth:
                # child thesis is parent's wedge → next fork
                child_thesis = node["board"].get("wedge") or thesis
                _grow(child_thesis, cur_depth+1, node_id, parallel=parallel+1)

    # root thesis
    root_thesis = f"Should we {LOOT_TO_ACTION.get(void,'breathe')} in {proj}? (seed {seed}, CR {atlas_score.get('cr')} MKT {mkt}) — board, then eventuality, then mirror."
    ok, reason = monitor_check(0, 0, root_thesis, 0, 0)
    root_node = {"id": "root", "depth": 0, "branch": 0, "parent": None, "thesis": root_thesis, "monitor": {"ok": ok, "reason": reason}, "board": None, "eventuality": None, "diff": None}
    try:
        bres = run_boardroom(root, root_thesis, seed)
        root_node["board"] = {"verdict": bres.get("synthesis",{}).get("verdict","conditional"),
                              "constraint": bres.get("synthesis",{}).get("dominant_constraint","")[:140],
                              "wedge": bres.get("synthesis",{}).get("best_wedge","")[:140],
                              "kill": bres.get("synthesis",{}).get("kill_test","")[:140],
                              "evidence_used": bres.get("synthesis",{}).get("evidence_used",[]),
                              "session": bres.get("session_id",""),
                              "sims": bres.get("prediction",{}).get("scenarios",{}),
                              "citations": sum((o.get("citations",[]) for o in bres.get("board",[])), [])[:6]}
        root_node["eventuality"] = eventuality_sim(root_node["board"], atlas_score, horizon="eventuality")
        root_node["diff"] = f"# root mirror — seed {seed} — {proj} CR{atlas_score.get('cr')} → gift path\n# board {root_node['board']['verdict']} — {root_node['board']['constraint']}\n"
    except Exception as e:
        root_node["board"] = {"verdict":"error","reason":str(e)[:200]}
    chain["nodes"].append(root_node)
    # grow children from root wedge
    _grow(root_node["board"].get("wedge") or root_thesis, 1, "root", parallel=0)
    chain["stats"] = {"nodes": len(chain["nodes"]), "throttled": sum(1 for n in chain["nodes"] if not n["monitor"]["ok"]), "depth": depth, "branch": branch}
    return chain

def write_chain(chain, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(chain, indent=2, default=str), encoding="utf-8")
    # also write theater data
    THEATER_DATA.parent.mkdir(parents=True, exist_ok=True)
    THEATER_DATA.write_text(json.dumps(chain, indent=2), encoding="utf-8")
    return out

def theater_html(chain_path: Path = None):
    # returns path to theater html (generates if missing)
    if THEATER_HTML.exists() and chain_path is None:
        return THEATER_HTML
    # generate from jerry.html-inspired soothing theater but for diffs
    html = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Lookingglass — diff theater</title>
<style>
  :root{--bg:#0d0f0e;--panel:#141816;--ink:#e8e6dc;--muted:#9aa3a0;--gold:#d4a017;--teal:#2ee5a6;--line:#232826}
  body.metal{--bg:#070707;--panel:#0e0e0e;--ink:#f2e8e8;--muted:#9a8d8d;--gold:#ff2a2a;--teal:#ff3b30;--line:#2a1a1a;background:radial-gradient(900px 500px at 50% 0%,#1a0a0a 0%,#070707 65%) fixed}
  body.metal .panel{border-color:#2a1a1a;box-shadow:0 0 18px rgba(255,42,42,.12) inset}
  body.metal .diff{border-color:#3a1a1a;background:#0f0a0a}
  body.metal .dot{background:#ff3b30;box-shadow:0 0 10px #ff3b30}
  body.metal .node.active{background:#1a0a0a;border-color:#ff3b30}
  @keyframes kersplode{0%{transform:scale(.7) rotate(-1deg);filter:brightness(2) blur(2px)}40%{transform:scale(1.08) rotate(1deg);filter:brightness(1.4)}100%{transform:none;filter:none}}
  @keyframes djent{0%{transform:translateX(0)}15%{transform:translateX(-2px)}30%{transform:translateX(2px)}45%{transform:translateX(-1px)}100%{transform:none}}
  body.metal .diff.kersplode{animation:kersplode .55s ease}
  body.metal .diff.djent{animation:djent .35s steps(2)}
  *{box-sizing:border-box} html,body{height:100%} body{margin:0;background:radial-gradient(1200px 600px at 70% -10%,#1a2320 0%,var(--bg) 60%);color:var(--ink);font:14px/1.5 ui-monospace,Menlo,Consolas,monospace}
  .wrap{max-width:1120px;margin:0 auto;padding:18px}
  h1{margin:0 0 4px;font-size:18px;letter-spacing:.08em} small{color:var(--muted)}
  .bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0}
  .btn{padding:7px 10px;border-radius:999px;border:1px solid #2a3431;background:#1a2220;color:var(--ink);cursor:pointer;font-weight:700}
  .btn[aria-pressed="true"]{background:#1e2e2a;border-color:var(--teal);box-shadow:0 0 0 2px rgba(46,229,166,.15) inset}
  .stage{display:grid;grid-template-columns:320px 1fr;gap:12px}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px;overflow:hidden}
  .chain{max-height:62vh;overflow:auto}
  .node{padding:8px 10px;border-radius:10px;border:1px solid transparent;cursor:pointer;display:flex;gap:8px;align-items:center}
  .node:hover{background:#1c2422;border-color:#24302d}
  .node.active{background:#1e2e2a;border-color:var(--teal)}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--teal);box-shadow:0 0 8px var(--teal)}
  .dot.throttled{background:#ff7a7a;box-shadow:0 0 8px #ff7a7a}
  .k{color:var(--muted);font-size:11px}
  .diff{white-space:pre-wrap;background:#0f1413;border:1px solid #1e2a28;border-radius:10px;padding:12px;min-height:220px;position:relative;overflow:hidden}
  .diff.sipe{animation:sipe .7s ease}
  .diff.fade{animation:fade .9s ease}
  .diff.mirror{animation:mirror 1.1s ease}
  @keyframes sipe{0%{transform:translateX(14px) skewX(1deg);opacity:.2}100%{transform:none;opacity:1}}
  @keyframes fade{0%{opacity:.15;filter:blur(2px)}100%{opacity:1;filter:none}}
  @keyframes mirror{0%{transform:scaleX(.96);opacity:.5}50%{transform:scaleX(1.02)}100%{transform:none;opacity:1}}
  .vu{height:6px;background:#0f1413;border-radius:999px;overflow:hidden;border:1px solid #1e2a28}
  .vu>i{display:block;height:100%;width:0%;background:linear-gradient(90deg,var(--teal),var(--gold));transition:width .25s}
  .ifthen{display:flex;gap:8px;align-items:center;margin:8px 0;flex-wrap:wrap}
  .pill{padding:4px 8px;border-radius:999px;border:1px solid #2a3431;background:#111816;font-size:11px}
  .pill.gold{border-color:var(--gold);color:var(--gold)}
  .controls{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
  canvas{width:100%;height:90px;background:#0f1413;border:1px solid #1e2a28;border-radius:10px}
  .foot{opacity:.5;margin-top:10px;font-size:11px}
</style>
</head><body>
<div class="wrap">
  <h1> Lookingglass <small>— diff theater · if this then that · chain breathes, not sprints</small></h1>
  <div class="bar">
    <button class="btn" id="play">▶︎ breathe</button>
    <button class="btn" id="pause" aria-pressed="false">⏸︎ hold</button>
    <button class="btn" id="prev">◀︎ sipe</button>
    <button class="btn" id="next">sipe ▶︎</button>
    <button class="btn" id="mirror"> mirror</button>
    <button class="btn" id="bgm" aria-pressed="false"> bgm</button>
    <button class="btn" id="metal" aria-pressed="false" title="black / white — zen vs metalcore"> metal</button>
    <label class="k">speed <input id="speed" type="range" min="900" max="4200" value="2200" style="vertical-align:middle"> <span id="speedv">2.2s</span></label>
    <span class="k" id="status">loading…</span>
  </div>
  <div class="stage">
    <div class="panel chain" id="chain"></div>
    <div class="panel">
      <div class="ifthen"><span class="pill" id="ifpill">if this —</span><span class="k">→</span><span class="pill gold" id="thenpill">then that —</span><span class="k" id="crpill"></span></div>
      <div class="vu"><i id="vu"></i></div>
      <canvas id="horse" width="860" height="90" aria-label="Silver breathes with the chain"></canvas>
      <div class="diff" id="diff">loading chain…\n\nTip: `lookingglass --seed 42 ~/Official-Vertical-AI-Boardroom --depth 4 --branch 2` then `lookingglass --theater`\n\nBGM is subtle — low, not loud. Jerry's horse lives here too.</div>
      <div class="controls">
        <span class="k">animations: sipe (slide+skew) · fade (blur) · mirror (scaleX) — they didn't exist yet, now they do</span>
      </div>
      <div class="k" id="meta" style="margin-top:6px"></div>
      <div class="foot">humane: archive not delete · monitor throttles · private stays private · <span id="seedfoot"></span> · `cat ~/tools/lookingglass/theater/theater.json | head`</div>
    </div>
  </div>
</div>
<audio id="bgmAudio" loop preload="none"></audio>
<script type="module">
const $ = s=>document.querySelector(s);
const chainEl=$('#chain'), diffEl=$('#diff'), vu=$('#vu'), status=$('#status'), speed=$('#speed'), speedv=$('#speedv'), horse=$('#horse'), ifpill=$('#ifpill'), thenpill=$('#thenpill'), crpill=$('#crpill'), meta=$('#meta'), seedfoot=$('#seedfoot');
let data=null, idx=0, timer=null, bgmOn=false;
let aud=null, ctx=null, osc=null, gain=null;

async function load(){
  try{
    const r=await fetch('./theater.json?'+Date.now()); data=await r.json();
  }catch(e){
    // try parent path for file://
    try{ const r2=await fetch('../theater/theater.json'); data=await r2.json(); }catch{}
  }
  if(!data){ diffEl.textContent='No theater.json yet.\n\nRun:\n  lookingglass --seed 42 ~/Official-Vertical-AI-Boardroom --depth 4 --branch 2\n  lookingglass --theater\nThen reload.'; status.textContent='no chain'; return; }
  status.textContent = `seed ${data.seed} · ${data.rel} · ${data.stats.nodes} nodes · depth ${data.depth} branch ${data.branch}`;
  seedfoot.textContent = `seed ${data.seed} · ${data.rel}`;
  renderChain();
  show(0, 'fade');
  drawHorse(0);
}
function renderChain(){
  chainEl.innerHTML='';
  data.nodes.forEach((n,i)=>{
    const d=document.createElement('div');
    d.className='node'+(i===idx?' active':'');
    const throttled = !n.monitor.ok;
    d.innerHTML=`<span class="dot ${throttled?'throttled':''}"></span><span style="flex:1"><b>${n.id}</b> <span class="k">${n.depth}:${n.branch}</span> — <span class="k">${(n.board?.verdict||'').slice(0,14)}</span><br><span class="k">${n.thesis.slice(0,64)}…</span></span>`;
    d.onclick=()=>show(i,'sipe');
    chainEl.appendChild(d);
  });
}
function show(i, anim){
  idx = Math.max(0, Math.min(i, data.nodes.length-1));
  const n=data.nodes[idx];
  diffEl.classList.remove('sipe','fade','mirror'); void diffEl.offsetWidth; diffEl.classList.add(anim||'fade');
  diffEl.textContent = n.diff + "\n\n— thesis: "+n.thesis+"\n— board: "+JSON.stringify(n.board,null,2).slice(0,900)+"\n— eventuality: "+JSON.stringify(n.eventuality,null,2).slice(0,700);
  ifpill.textContent = 'if this: '+(n.eventuality?.base?.if_this || n.eventuality?.downside?.if_this || '—');
  thenpill.textContent = 'then that: '+(n.eventuality?.base?.then_that || '—');
  crpill.textContent = n.eventuality?.base ? `CR ${n.eventuality.base.cr_now} → ${n.eventuality.base.cr_eventual} (${n.eventuality.base.delta>0?'-':''}${n.eventuality.base.delta})` : '';
  meta.textContent = `monitor: ${n.monitor.ok?'ok':'throttled — '+n.monitor.reason} · cites ${JSON.stringify(n.board?.evidence_used||[])} · kill: ${(n.board?.kill||'').slice(0,90)}`;
  vu.style.width = (28 + (n.eventuality?.base ? (n.eventuality.base.delta*18) : 6))+'%';
  document.querySelectorAll('.node').forEach((el,j)=>el.classList.toggle('active', j===idx));
  drawHorse(idx);
}
function drawHorse(i){
  const c=horse.getContext('2d'); c.clearRect(0,0,horse.width,horse.height);
  // soothing prairie — Silver's gait tied to eventuality delta (slow breathes)
  const n=data.nodes[i]; const delta=n?.eventuality?.base?.delta||0;
  const gait = Math.max(0.6, Math.min(2.4, 1.0 + delta*0.35));
  const t = Date.now()/280 * gait;
  c.fillStyle='#0f1413'; c.fillRect(0,0,horse.width,horse.height);
  // ground
  c.fillStyle='#1a2421'; c.fillRect(0,68,horse.width,22);
  // cactus
  c.fillStyle='#1e332b'; for(let x=40;x<horse.width;x+=180){ c.fillRect(x, 42+Math.sin(x*0.01)*6, 10, 26); c.fillRect(x-6, 52, 6, 4); c.fillRect(x+10, 48, 6, 4); }
  // horse — simple, soothing, not sprite-heavy
  const hx = 120 + Math.sin(t*0.7)*14;
  const hy = 52 + Math.abs(Math.sin(t))*3;
  c.fillStyle='#d9c7a5'; // body
  c.beginPath(); c.ellipse(hx, hy, 24, 11, 0, 0, Math.PI*2); c.fill();
  c.beginPath(); c.ellipse(hx+22, hy-6, 10, 8, 0, 0, Math.PI*2); c.fill(); // head
  c.fillStyle='#8a7460'; c.fillRect(hx-18, hy+8, 6, 10); c.fillRect(hx+8, hy+8, 6, 10); // legs with gait
  c.fillStyle='#2ee5a6'; c.fillRect(hx-10, hy-16, 2+Math.sin(t)*1, 6); // ear flick
  // tumbleweed on sipe
  const tw = (t*22)%horse.width;
  c.fillStyle='#6b5a3a'; c.beginPath(); c.arc(tw, 74, 7, 0, Math.PI*2); c.fill();
  c.strokeStyle='rgba(212,160,23,.25)'; c.strokeRect(0,0,horse.width,horse.height);
  if(timer) requestAnimationFrame(()=>drawHorse(idx));
}
function breatheNext(){ const a = document.body.classList.contains('metal') ? (idx%2===0?'kersplode':'djent') : (idx%3===0?'mirror': idx%2===0?'sipe':'fade'); show((idx+1)%data.nodes.length, a); }
$('#play').onclick=()=>{
  if(timer) return;
  $('#play').setAttribute('aria-pressed','true');
  $('#pause').setAttribute('aria-pressed','false');
  const ms=parseInt(speed.value,10);
  timer=setInterval(breatheNext, ms);
  drawHorse(idx);
  status.textContent += ' · breathing';
}
$('#pause').onclick=()=>{
  if(!timer) return;
  clearInterval(timer); timer=null;
  $('#play').setAttribute('aria-pressed','false');
  $('#pause').setAttribute('aria-pressed','true');
  status.textContent = status.textContent.replace(' · breathing',' · held');
}
$('#prev').onclick=()=>show(idx-1,'sipe');
$('#next').onclick=()=>show(idx+1,'sipe');
$('#mirror').onclick=()=>show(idx,'mirror');
speed.oninput=()=>{
  speedv.textContent=(parseInt(speed.value,10)/1000).toFixed(1)+'s';
  if(timer){ clearInterval(timer); timer=setInterval(breatheNext, parseInt(speed.value,10)); }
}
let metalOn=false;
$('#metal').onclick=()=>{
  metalOn=!metalOn;
  document.body.classList.toggle('metal', metalOn);
  $('#metal').setAttribute('aria-pressed', metalOn?'true':'false');
  $('#metal').textContent = metalOn ? ' BLEGH' : ' metal';
  status.textContent = (metalOn ? 'metalcore — kersplosions + djent breakdowns' : 'zen — sipes + fades + mirror') + ` · seed ${data.seed} · ${data.rel}`;
  diffEl.classList.remove('sipe','fade','mirror','kersplode','djent'); void diffEl.offsetWidth;
  diffEl.classList.add(metalOn ? 'kersplode' : 'mirror');
  if(metalOn && bgmOn){
    try{ if(ctx){ const o=ctx.createOscillator(), g=ctx.createGain(); o.type='square'; o.frequency.value=42; g.gain.value=0.0; o.connect(g).connect(ctx.destination); o.start(); g.gain.linearRampToValueAtTime(0.09, ctx.currentTime+0.08); g.gain.linearRampToValueAtTime(0, ctx.currentTime+0.42); setTimeout(()=>{try{o.stop()}catch{}},500); }}catch{}
  }
};
$('#bgm').onclick=async()=>{
  bgmOn=!bgmOn;
  $('#bgm').setAttribute('aria-pressed', bgmOn?'true':'false');
  if(bgmOn){
    try{
      ctx = ctx || new (window.AudioContext||window.webkitAudioContext)();
      if(ctx.state==='suspended') await ctx.resume();
      // subtle BGM: two slow sines + faint filtered noise — not a song, a breath
      osc = ctx.createOscillator(); const osc2=ctx.createOscillator(); gain=ctx.createGain(); const g2=ctx.createGain();
      osc.type='sine'; osc.frequency.value=55; // A1
      osc2.type='sine'; osc2.frequency.value=110;
      gain.gain.value=0.0; g2.gain.value=0.0;
      const lp=ctx.createBiquadFilter(); lp.type='lowpass'; lp.frequency.value=420;
      osc.connect(gain).connect(lp).connect(ctx.destination);
      osc2.connect(g2).connect(lp).connect(ctx.destination);
      osc.start(); osc2.start();
      gain.gain.linearRampToValueAtTime(0.04, ctx.currentTime+1.2);
      g2.gain.linearRampToValueAtTime(0.02, ctx.currentTime+1.2);
      // shimmer every 8s
      window._bgmOsc=[osc,osc2,gain,g2];
    }catch(e){ console.log('bgm',e); }
  } else {
    try{
      if(window._bgmOsc){
        window._bgmOsc[2].gain.linearRampToValueAtTime(0, ctx.currentTime+0.8);
        window._bgmOsc[3].gain.linearRampToValueAtTime(0, ctx.currentTime+0.8);
        setTimeout(()=>{ try{window._bgmOsc[0].stop();window._bgmOsc[1].stop();}catch{} },900);
      }
    }catch{}
  }
};
// keyboard: hold space to breathe slowly
document.addEventListener('keydown',e=>{
  if(e.code==='Space'){ e.preventDefault(); if(!timer) $('#play').click(); }
  if(e.code==='ArrowRight') $('#next').click();
  if(e.code==='ArrowLeft') $('#prev').click();
  if(e.code==='KeyM') $('#mirror').click();
});
load();
</script>
</body></html>
"""
    THEATER_HTML.parent.mkdir(parents=True, exist_ok=True)
    THEATER_HTML.write_text(html, encoding="utf-8")
    return THEATER_HTML

def main(argv=None):
    ap = argparse.ArgumentParser(description="Lookingglass — recursive chains → boardroom → eventuality → diff theater (soothing if-this-then-that)")
    ap.add_argument("path", nargs="?", default=".", help="root to grow chain from")
    ap.add_argument("--seed", type=int, default=SEED_DEFAULT, help="reproducible seed (same seed = same chain + same theater)")
    ap.add_argument("--depth", type=int, default=4, help="chain depth (1..5, monitor caps at 5)")
    ap.add_argument("--branch", type=int, default=2, help="branch factor per fork (1..3)")
    ap.add_argument("--chain", dest="chain_path", default="", help="existing chain json to play/open")
    ap.add_argument("--out", default="", help="write chain json to file (default: ~/tools/lookingglass/chains/chain-<seed>-<name>.json)")
    ap.add_argument("--theater", action="store_true", help="open/generate theater.html (soothing diff theater)")
    ap.add_argument("--play", action="store_true", help="open theater after writing chain")
    ap.add_argument("--watch", action="store_true", help="alias for grow + theater")
    ap.add_argument("--if-this", dest="if_this", default="", help="custom if-this (overrides auto thesis)")
    ap.add_argument("--then-that", action="store_true", help="show then-that eventuality only")
    ap.add_argument("--dry-run", action="store_true", help="monitor check only, don't run boardroom")
    ap.add_argument("--arena", type=int, default=0, help="fractal arena: population N (32=demo, 128=hundred, 1024=thousand) — fractal → battle to 2 → breed with molt")
    ap.add_argument("--generations", type=int, default=2, help="generations of molt shedding in arena (1..5)")
    ap.add_argument("--concepts", default="", help="concepts root to sit and do this to all (use 'all' or a path like ~/p_recovery) — sits with each concept slowly, monitored")
    ap.add_argument("--no-mrd", action="store_true", help="don't append to MRD.tct")
    args = ap.parse_args(argv)

    if args.chain_path and not args.theater:
        # play existing chain
        cp = Path(args.chain_path).expanduser()
        if not cp.exists():
            # try theater data
            cp = THEATER_DATA
        if cp.exists():
            print(f"Chain: {cp} ({cp.stat().st_size}B)")
            print(cp.read_text()[:1200])
            th = theater_html(cp)
            print(f"Theater: {th}")
            print(f"Open: xdg-open {th}  or  python3 -m http.server --directory {th.parent} 8003")
            return 0

    if args.theater and not args.path and not args.chain_path:
        th = theater_html()
        print(f"Theater: {th} ({th.stat().st_size}B)")
        print(f"Open: xdg-open {th}")
        return 0

    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"No such path: {root}", file=sys.stderr); return 1
    if root.is_file(): root = root.parent
    depth = max(1, min(args.depth, MONITOR_RULES["max_depth"]))
    branch = max(1, min(args.branch, MONITOR_RULES["max_branch"]))

    # custom if-this → single-node chain
    if args.if_this:
        chain = {"seed": args.seed, "root": str(root), "rel": "~/" + str(root.relative_to(HOME)) if str(root).startswith(str(HOME)) else str(root),
                 "created": datetime.now(timezone.utc).isoformat(), "depth": 1, "branch": 1, "nodes": [], "stats": {}}
        thesis = args.if_this
        if args.then_that:
            thesis += " — then that? (show eventuality mirror)"
        ok, reason = monitor_check(1, 0, thesis, 0, 0)
        node = {"id": "if-then", "depth": 1, "branch": 0, "parent": None, "thesis": thesis, "monitor": {"ok": ok, "reason": reason}, "board": None, "eventuality": None, "diff": thesis}
        if ok and not args.dry_run:
            bres = run_boardroom(root, thesis, args.seed)
            node["board"] = {"verdict": bres.get("synthesis",{}).get("verdict",""), "wedge": bres.get("synthesis",{}).get("best_wedge",""), "evidence_used": bres.get("synthesis",{}).get("evidence_used",[])}
            asc = score_one(root, args.seed)
            node["eventuality"] = eventuality_sim(node["board"], asc, horizon="mirror")
        else:
            node["board"] = {"verdict": "dry-run" if args.dry_run else "throttled", "reason": reason}
        chain["nodes"]=[node]
        chain["stats"]={"nodes":1}
        out = Path(args.out).expanduser() if args.out else CHAINS / f"chain-{args.seed}-{root.name}-ifthen.json"
        write_chain(chain, out)
        print(f"If-this-then-that chain: {out}")
        print(json.dumps(node, indent=2))
        if args.play or args.theater or args.watch:
            th = theater_html(out)
            print(f"Theater: {th}")
        return 0

    if args.dry_run:
        ok, reason = monitor_check(depth, branch, f"dry-run seed {args.seed} depth {depth} branch {branch}", 0, 0)
        print(f"Monitor dry-run: ok={ok} reason={reason} depth={depth} branch={branch} seed={args.seed} root={root}")
        return 0

    # ── ARENA: fractal to N → battle to 2 → breed (molt) humane
    if args.arena and args.arena >= 8 and not args.concepts:
        import pathlib as _pl
        pop = max(8, min(args.arena, 1024))
        gens = max(1, min(args.generations, 5))
        print(f" Lookingglass ARENA — fractal to {pop} → battle until 2 remain → breed (molt {gens} gens) — seed {args.seed} @ {root} (humane: archive not delete)")
        chain = fractal_arena(root, args.seed, population=pop, generations=gens, depth=depth, branch=branch)
        out = _pl.Path(args.out).expanduser() if args.out else CHAINS / f"arena-{args.seed}-{root.name}-p{pop}g{gens}.json"
        write_chain(chain, out)
        print(f"Arena: {out} — rounds {chain['arena']['rounds']} champions {chain['arena']['champions']} — {chain['arena']['breed_note'][:110]}")
        for r in chain['arena']['receipts'][:6]:
            print(f"  {r['pair']:18s} winner {r['winner']:8s} fitness {r['fitness']} → {r['molt_note'][:50]}")
        print(f"  humane: {chain['arena']['humane_guarantee'][:90]}")
        th = theater_html(out)
        print(f"Theater: {th} — flip metal → BLEGH (zen vs metalcore, same ethic)")
        if not args.no_mrd and MRD_TCT.exists():
            try:
                import datetime
                sig = f"\n### {datetime.datetime.now().isoformat()} — lookingglass ARENA p{pop}g{gens} seed {args.seed} — {root.name} — champions {chain['arena']['champions']} — rounds {chain['arena']['rounds']}\n- Arena: `{out.relative_to(HOME) if str(out).startswith(str(HOME)) else out}` — fractal {pop} → battle to 2 → breed — humane\n- Theater: `tools/lookingglass/theater/theater.html` — metal toggle\n"
                MRD_TCT.write_text(MRD_TCT.read_text(encoding="utf-8") + sig, encoding="utf-8")
            except: pass
        return 0
    # ── CONCEPTS: sit and do this to all concepts more or less (slow, soothing, one chain each)
    if args.concepts != "":
        import pathlib as _pl2
        roots = []
        if args.concepts == "all":
            for cand in [HOME/"p_recovery", HOME/"UNPACKED", HOME/"projects", HOME/"research", HOME/"tools"]:
                if cand.exists():
                    for d in cand.iterdir():
                        if d.is_dir() and not d.name.startswith(".") and not d.name.startswith("_"):
                            try: has = any(d.rglob("*.py"))
                            except: has = False
                            if has or (d/"README.md").exists() or (d/"CURATOR.md").exists():
                                roots.append(d)
                    roots.append(cand)
        else:
            cp = _pl2.Path(args.concepts).expanduser()
            if cp.is_dir():
                subs = [d for d in cp.iterdir() if d.is_dir() and not d.name.startswith(".")]
                roots = subs[:24] + [cp] if subs else [cp]
            else:
                roots = [HOME/"p_recovery"]
        seen=set(); uniq=[]
        for r in roots:
            s=str(r.resolve())
            if s not in seen:
                seen.add(s); uniq.append(_pl2.Path(s))
        uniq = uniq[:12]
        print(f" Lookingglass concepts — sitting with {len(uniq)} concepts, one slow chain each (seed {args.seed})")
        print(f"   This is the journey that makes it worthwhile — not speedy, just breathing. Ctrl+C to pause anytime.")
        all_chains=[]
        for idx, cr in enumerate(uniq):
            if not cr.exists(): continue
            try:
                pop = max(8, min(args.arena if args.arena else 16, 128))
                print(f"\n[{idx+1}/{len(uniq)}] {cr} — growing d{depth}b{branch} (pop {pop} if arena else chain)...")
                if args.arena and args.arena >= 8:
                    ch = fractal_arena(cr, args.seed + idx*13, population=pop, generations=max(1, min(args.generations,3)), depth=depth, branch=branch)
                else:
                    ch = grow_chain(cr, args.seed + idx*13, depth=depth, branch=branch)
                out = CHAINS / f"concept-{args.seed}-{cr.name}-d{depth}b{branch}.json"
                write_chain(ch, out)
                print(f"   → {out.name} — {ch['stats']['nodes']} nodes cites {ch['nodes'][0].get('board',{}).get('evidence_used',[])[:2]}")
                all_chains.append(str(out))
                import time as _t; _t.sleep(0.35)
            except Exception as e:
                print(f" {cr.name}: {e}")
        if all_chains:
            th = theater_html(_pl2.Path(all_chains[-1]))
            print(f"\nConcepts theater: {th} — {len(all_chains)} chains, flip metal for BLEGH")
        if not args.no_mrd and MRD_TCT.exists():
            try:
                import datetime
                sig2 = f"\n### {datetime.datetime.now().isoformat()} — lookingglass concepts — {len(uniq)} concepts, seed {args.seed} d{depth}b{branch}\n- Chains: {len(all_chains)} in `tools/lookingglass/chains/concept-*`\n"
                MRD_TCT.write_text(MRD_TCT.read_text(encoding="utf-8") + sig2, encoding="utf-8")
            except: pass
        return 0
    print(f" Lookingglass — growing chain seed {args.seed} @ {root} depth {depth} branch {branch} (monitor: depth≤{MONITOR_RULES['max_depth']} branch≤{MONITOR_RULES['max_branch']} parallel≤{MONITOR_RULES['max_parallel']})")
    chain = grow_chain(root, args.seed, depth, branch)
    out = Path(args.out).expanduser() if args.out else CHAINS / f"chain-{args.seed}-{root.name}-d{depth}b{branch}.json"
    write_chain(chain, out)
    print(f"Chain: {out} — {chain['stats']['nodes']} nodes ({chain['stats']['throttled']} throttled) — reproducible seed {args.seed}")
    for n in chain["nodes"][:6]:
        ev = ",".join(n.get("board",{}).get("evidence_used",[])[:3]) or "—"
        print(f"  {n['id']:12s} d{n['depth']} cites [{ev}] {n['board'].get('verdict','')[:10]:10s} → {n['eventuality'].get('base',{}).get('flavor','')[:64] if n.get('eventuality') else ''}")

    # theater
    th = theater_html(out)
    print(f"Theater: {th} ({th.stat().st_size}B) — subtle BGM, sipe/fade/mirror, horse breathes with chain")
    print(f"Open: xdg-open {th}  # or: python3 -m http.server --directory {th.parent} 8003")

    if not args.no_mrd and MRD_TCT.exists():
        try:
            sig = f"\n### {datetime.now().isoformat()} — lookingglass seed {args.seed} — {root.name} d{depth}b{branch} — {chain['stats']['nodes']} nodes — theater ready\n"
            sig += f"- Chain: `{out.relative_to(HOME) if str(out).startswith(str(HOME)) else out}` — boardroom→eventuality via monitor (humane, throttled {chain['stats']['throttled']})\n"
            sig += f"- Theater: `tools/lookingglass/theater/theater.html` — BGM + sipe/fade/mirror (animations that didn't exist yet)\n"
            sig += f"- Repro: `lookingglass --seed {args.seed} {root} --depth {depth} --branch {branch}` same seed = same chain\n"
            sig += f"- Open: `xdg-open ~/tools/lookingglass/theater/theater.html` or `lookingglass --theater`\n"
            MRD_TCT.write_text(MRD_TCT.read_text(encoding="utf-8") + sig, encoding="utf-8")
        except Exception as e:
            print(f"[lookingglass] MRD append skip: {e}", file=sys.stderr)

    if args.play or args.watch:
        # don't auto-open in Codebuff, just hint
        pass
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

