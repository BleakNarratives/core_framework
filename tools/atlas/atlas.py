#!/usr/bin/env python3
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: introspection
# DEPS: pathlib,argparse,ast,json,hashlib,random,subprocess,re,datetime,collections
# ROLE: atlas — Gap Atlas: gamified reproducible gap lens, market+scale first, 7 affordance voids scored together (first time), dungeon deck + heat map + pooper quests
# AUTHOR: Buffy — for Bleak, after Jerry's Ears, before the dogs come back
# SESSION: 2026-09-10
# TIER: 2
# FKA: council + sherpa + codemap + pooper + odds-of-the-gods reinforcement -> gap deck
# [/DNA_TAG]
"""
Atlas — Gap Atlas: creative, gamified, reproducible, market+scale first.

Novel lens: scores 7 AFFORDANCE VOIDS together in one seeded deck — no single-file
metric does this alone. Reproducible via seed, creative via deck metaphor.

  atlas --seed 42                    # full pan-wide gap dungeon (reproducible)
  atlas ~/tools --seed 42            # scope to one dir
  atlas --html out.html --json out.json
  atlas --quest 3                    # poop one quest card into Claude/Gemini app (15 min)

Voids (7):
  1. distribution_void — has code but no route to a user (missing /health, CLI --help, Docker, publish)
  2. monetization_void — value but no checkout (no webhook, no MRD-linked plumbing, no meter)
  3. trust_void — magical claims without receipts (no tests, no py_compile gate, no STANK/advisory)
  4. retention_void — hook but no loop (no cron/timer, no variable reward, no streak, no Janus sediment)
  5. scale_void — works for 1 but dies at 100 (no queue, no rate limit, no guard_judo, O(n^2) graph)
  6. discoverability_void — exists but can't be found (no CURATOR.md, no README, no sherpa, orphan forest)
  7. cruelty_void — ships but deletes (no archive, no humane_cannibal provenance, no .bak, hard rm)

Each project gets a monster card (CR per void) + loot (lowest-effort close) + market lens (TAM×pain×reach).
Deck is deterministic per seed, so Jerry's horse demo reproduces tomorrow.

Outputs append to MRD.tct (meatsuit rundown) so you don't have to remember.

Game: dungeon = 7 rooms. Clear rooms by closing voids. Boss = the project with highest combined CR.
"""

import argparse
import ast
import hashlib
import json
import random
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
MRD_TCT = HOME / "MRD.tct"
ATLAS_DIR = HOME / "tools/atlas"
ATLAS_DIR.mkdir(parents=True, exist_ok=True)

SEED_DEFAULT = 42
VOID_ORDER = ["distribution","monetization","trust","retention","scale","discoverability","cruelty"]
VOID_LABELS = {
    "distribution": "Distribution — can a human RUN it?",
    "monetization": "Monetization — can a human PAY for it?",
    "trust": "Trust — can a skeptic BELIEVE it?",
    "retention": "Retention — will a human COME BACK?",
    "scale": "Scale — does it survive 10→100?",
    "discoverability": "Discoverability — can a human FIND it?",
    "cruelty": "Cruelty — does it ship without deleting?",
}
VOID_ICON = {"distribution":"","monetization":"","trust":"","retention":"","scale":"","discoverability":"","cruelty":""}

# market lens weights (you said market+scaleablity first, spelling lol fuck it — keeping it)
MARKET_WEIGHTS = {
    "distribution": 1.4,
    "monetization": 1.6,
    "trust": 1.2,
    "retention": 1.3,
    "scale": 1.5,
    "discoverability": 1.1,
    "cruelty": 0.9, # humanity matters but doesn't sell Day 1
}

SKIP_DIRS = {".git","__pycache__","node_modules",".venv","venv","env",".mypy_cache",".pytest_cache","dist","build",".idea",".vscode",".archive_cannibal","targets","reports","__pycache__",".janus","models","vendor","third_party",".next",".cache",".ruff_cache",".benchmark","._archive","UNPACKED",".pooper",".sherpa"," implant ","native"}

def has_main_guard(src:str): return 'if __name__' in src and '__main__' in src
def has_argparse(src:str): return 'argparse' in src or 'ArgumentParser' in src
def has_api(src:str): return any(k in src for k in ['FastAPI','Flask','uvicorn','/health','/api/','@app.'])
def has_health(src:str): return '/health' in src or 'health' in src.lower()
def has_tests(p: Path): return any(p.glob('test_*.py')) or any(p.glob('*_test.py')) or (p/'tests').exists()
def has_readme(p: Path): return any((p/f).exists() for f in ['README.md','README','runbook.txt'])
def has_curator(p: Path): return (p/'CURATOR.md').exists()
def has_docker(p: Path): return any((p/f).exists() for f in ['Dockerfile','docker-compose.yml','fly.toml'])
def has_pyproject(p: Path): return any((p/f).exists() for f in ['pyproject.toml','setup.py','package.json','Cargo.toml'])
def has_cron(p: Path):
    try:
        txt = ' '.join(pp.read_text(errors='replace') for pp in p.rglob('*.py') if pp.is_file())
        if any(k in txt for k in ['schedule','cron','interval','Timer','celery','beat','APScheduler','RandomizedDelay']): return True
    except: pass
    return any((p/f).exists() for f in ['.timer','cron','schedule'])
def has_queue(p: Path):
    try:
        txt = ' '.join(pp.read_text(errors='replace') for pp in p.rglob('*.py') if pp.is_file())
        if any(k in txt for k in ['deque','queue','worker','threading','asyncio','BoardroomService','FIFO','celery','rq']):
            return True
    except: pass
    return False
def has_guard(path_text:str): return 'guard_judo' in path_text or 'rate' in path_text.lower() or 'limiter' in path_text.lower()
def has_archive_grace(p: Path):
    return (p/'.archive_cannibal').exists() or any('archive' in f.name for f in p.glob('.*')) or has_pyproject(p)  # weak proxy

def project_score(project: Path, seed:int):
    """Return {void->score 0..10, market, scale, evidence} where 10=void gap (needs work), 0=closed."""
    rng = random.Random(int(hashlib.sha256(f"{project}|{seed}".encode()).hexdigest()[:8],16))
    # counts
    pys = [f for f in project.rglob('*.py') if not any(part in SKIP_DIRS for part in f.parts)][:120]
    py_text = ''
    for f in pys[:40]:
        try: py_text += f.read_text(errors='replace')[:1200]
        except: pass
    py_n = len(pys)
    entry = 0
    for f in pys[:60]:
        try:
            src=f.read_text(errors='replace')
            if has_main_guard(src) or has_argparse(src) or has_api(src):
                entry+=1
        except: pass
    # voids
    v={}
    # distribution: needs one entry that a stranger can run in 2 min
    if py_n==0: v['distribution']=9
    elif entry==0: v['distribution']=8
    elif has_api(py_text) and has_health(py_text): v['distribution']=2
    elif has_pyproject(project) or has_readme(project): v['distribution']=4 + rng.randint(0,1)
    else: v['distribution']=6
    if has_docker(project): v['distribution'] = max(0, v['distribution']-2)
    # monetization: checkout / webhook / MRD link
    has_pay = any(k in py_text for k in ['saas_lemonsqueezy','lemonsqueezy','/webhooks/','FUNDING','Strike','lightning'])
    has_meter = any(k in py_text for k in ['CLOUD_SYNC','meter','entitlement','webhook'])
    if has_pay and has_meter: v['monetization']=2
    elif has_pay: v['monetization']=5
    else: v['monetization']=8 + rng.randint(-1,1)
    if project.name=='Official-Vertical-AI-Boardroom': v['monetization']=6  # parked (no KYC) — honest
    # trust
    if has_tests(project) and 'py_compile' in py_text: v['trust']=3
    elif has_tests(project): v['trust']=5
    elif py_n>40: v['trust']=8
    else: v['trust']=6 + rng.randint(-1,1)
    # retention
    loops = has_cron(project) or 'variable reward' in py_text.lower() or 'Janus' in py_text or 'sediment' in py_text
    if loops and has_queue(project): v['retention']=3
    elif loops: v['retention']=5
    else: v['retention']=7 + rng.randint(0,1)
    if project.name=='Code-City-Apocalypse': v['retention']=4  # game loop
    # scale
    if has_queue(project) and has_guard(py_text): v['scale']=3
    elif has_queue(project): v['scale']=6
    elif py_n>80 and entry>8: v['scale']=7
    else: v['scale']=5 + rng.randint(-1,1)
    # discoverability
    if has_curator(project) and has_readme(project): v['discoverability']=2
    elif has_curator(project) or has_readme(project): v['discoverability']=5
    elif py_n==0: v['discoverability']=9
    else: v['discoverability']=7 + rng.randint(-1,1)
    # cruelty
    has_archive = (project/'.archive_cannibal').exists() or 'humane_cannibal' in py_text or 'archive' in py_text.lower()
    deletes = py_text.count('rm -rf') + py_text.count('shred') >=1  # shred is ok (keys)
    if has_archive and not deletes: v['cruelty']=2
    elif has_archive: v['cruelty']=4
    elif py_n==0: v['cruelty']=5
    else: v['cruelty']=7 + rng.randint(-1,0)
    for k in VOID_ORDER:
        v[k]=max(0,min(10, int(v[k])))
    # market lens: TAM×pain×reach heuristic (creative, reproducible)
    # TAM: project domain breadth (boardroom > bench > tool?) but bench has niche high pain (Jerry)
    # We use py_n + entry + has_api + has_tests as proxies; seeded jitter for novelty but stable per seed
    tam = min(10, 2 + int((py_n**0.45)) + (2 if has_api(py_text) else 0) + (1 if has_pyproject(project) else 0))
    pain = 8 if project.name in ('Official-Vertical-AI-Boardroom','tools','Code-City-Apocalypse') else 5 + rng.randint(-1,2)
    # Jerry bench is high pain niche: 83yo, hearing aids not working, basement+dgs — low tam high pain = still sellable as story
    if project.name=='jerry-hearing': pain=9; tam=max(4, tam-1)
    reach = 8 if has_readme(project) and has_curator(project) else 5 + rng.randint(-1,1)
    market = round((tam*0.34 + pain*0.45 + reach*0.21),1)
    scale_score = v['scale']
    # combined CR (challenge rating) per project
    cr = sum(v[k]*MARKET_WEIGHTS[k] for k in VOID_ORDER) / sum(MARKET_WEIGHTS.values())
    # loot = lowest-effort close (one action that shaves most market-weighted CR)
    loot_map = {
        'distribution': 'Add one ENTRY: `python3 main.py --help` + health route that passes `curl /health` in 2 min',
        'monetization': 'Park/strip KYC: tip jar + gift path (no Stripe) — wire `/webhooks/gift` behind guard_judo',
        'trust': 'Add `python3 -m py_compile` gate + 1 test that names its receipt (STANK/JANUS)',
        'retention': 'Add one cron/timer + Janus sediment on completion (variable reward every 3rd)',
        'scale': 'Wrap entry in queue (deque FIFO) + guard_judo tarpit — 20 lines, hashed IPs',
        'discoverability': '`sherpa --write` → CURATOR.md so a cold dev finds it in 10 lines',
        'cruelty': 'Use humane_cannibal: archive losers, graft winner as `__from_*`, never rm',
    }
    # pick highest market-weighted void as loot
    ranked = sorted(VOID_ORDER, key=lambda k: v[k]*MARKET_WEIGHTS[k], reverse=True)
    loot_void = ranked[0]
    return {
        'voids': v,
        'cr': round(cr,1),
        'loot_void': loot_void,
        'loot': loot_map[loot_void],
        'market': {'tam': tam, 'pain': pain, 'reach': reach, 'index': market},
        'scale_score': scale_score,
        'py_n': py_n,
        'entry': entry,
        'evidence': {
            'has_api': has_api(py_text),
            'has_health': has_health(py_text),
            'has_tests': has_tests(project),
            'has_readme': has_readme(project),
            'has_curator': has_curator(project),
            'has_docker': has_docker(project),
            'has_queue': has_queue(project),
            'has_guard': has_guard(py_text),
        }
    }

def discover_projects(root: Path, max_projects=28):
    # top-level dirs with >3 py, plus tools subdirs — capped fast (reproducible)
    cands=[]
    for d in root.iterdir():
        if not d.is_dir(): continue
        if d.name.startswith('.') and d.name not in ('tools',): continue
        if d.name in SKIP_DIRS: continue
        if d.name in ('_archive','vendor','third_party','node_modules','venv'): continue
        # fast capped count — stop at 80 to avoid deep UNPACKED walks (reproducible per seed still via project_score rng)
        cnt = 0
        try:
            for f in d.rglob('*.py'):
                if any(part in SKIP_DIRS for part in f.parts):
                    continue
                cnt += 1
                if cnt >= 80:
                    break
        except: cnt = 0
        if cnt>=4:
            cands.append((cnt, d))
    # sort by weight then take top, plus always include tools/atlas, jerry, boardroom
    cands = sorted(cands, key=lambda x: -x[0])[:max_projects]
    # add tools subprojects as distinct nodes for scale
    tools = HOME / 'tools'
    if tools.exists():
        for sub in tools.iterdir():
            if sub.is_dir():
                try:
                    pc = sum(1 for _ in sub.rglob('*.py'))
                    if pc>=1:
                        cands.append((min(pc,80), sub))
                except: pass
    # filter market-meaningful: skip env/lib pseudo-projects unless they have README/CURATOR
    # (lib, lib64, pdfenv, -env dirs are noise for market+scale lens)
    filtered=[]
    for cnt,d in cands:
        nm = d.name
        if nm in ('lib','lib64','bleaknarratives'): continue
        if nm.endswith('-env') or nm.endswith('env'):
            # keep only if it looks like a real product
            if not any((d/f).exists() for f in ['README.md','CURATOR.md','pyproject.toml']):
                continue
        filtered.append((cnt,d))
    cands = filtered
    # dedup by path
    seen=set(); out=[]
    for cnt,d in cands:
        if str(d) in seen: continue
        seen.add(str(d)); out.append((cnt,d))
    # also include The-Werkz Boardroom if exists
    for cand in [HOME/'The-Werkz/Official-Vertical-AI-Boardroom', HOME/'Official-Vertical-AI-Boardroom']:
        if cand.exists() and str(cand) not in seen:
            out.append((len(list(cand.rglob('*.py'))), cand))
            seen.add(str(cand))
    # tools/jerry-hearing is small but market-interesting
    pj = HOME/'tools/jerry-hearing'
    if pj.exists() and str(pj) not in seen:
        out.append((1, pj))
    return sorted(out, key=lambda x: -x[0])[:max_projects]

def render_dungeon_text(items, seed, root_label):
    lines=[]
    lines.append(f"┌─ GAP ATLAS — seed {seed} — {root_label} — reproducible dungeon (market+scale first)")
    lines.append(f"│  7 voids scored together (novel lens: affordance, not just coverage). CR = market-weighted. Loot = one close. Boss = highest CR.")
    lines.append(f"│  Icons: 🚚 distribution 💰 monetization 🧪 trust 🔁 retention 📈 scale 🗺️ discoverability 💀 cruelty")
    lines.append(f"│  Scale top = survives 10→100. Market = TAM×pain×reach (Jerry bench = low TAM, high pain → still a boss).")
    lines.append(f"│  Re-run: atlas --seed {seed} — same seed = same deck. Creative but reproducible.")
    lines.append(f"│")
    # table header
    lines.append(f"│  ROOM  PROJECT{ ' ' * 20} CR  MKT  voids (10=gap)                    LOOT → quest")
    lines.append(f"│  ─────────────────────────────────────────────────────────────────────────────────────────")
    for idx,(cnt,proj) in enumerate(items,1):
        s=project_score(proj, seed)
        v=s['voids']
        voids_str = ' '.join(f"{VOID_ICON[k]}{v[k]}" for k in VOID_ORDER)
        name = proj.name if proj.name!='tools' else f"tools/{proj.parent.name if proj.parent.name!='tools' else proj.name}"
        if proj.parent.name=='tools': name = f"tools/{proj.name}"
        else: name = proj.name
        name = name[:26].ljust(26)
        lines.append(f"│  {idx:2d}  {name} {s['cr']:3.1f} {s['market']['index']:3.1f}  {voids_str}  → {s['loot_void'][:4]}: {s['loot'][:44]}")
    # boss
    boss = max(items, key=lambda x: project_score(x[1], seed)['cr'])
    bs = project_score(boss[1], seed)
    lines.append(f"│")
    lines.append(f"│  BOSS: {boss[1].name} (CR {bs['cr']} — worst market-weighted void = {bs['loot_void']} [{bs['voids'][bs['loot_void']]}])")
    lines.append(f"│  Loot card: {bs['loot']}")
    lines.append(f"│  Spell: 15-min quest → `atlas --quest {VOID_ORDER.index(bs['loot_void'])+1}` or `pooper --glob` variant")
    lines.append(f"│  Next: `atlas --html /tmp/atlas.html --json /tmp/atlas.json` → map + MRD.tct forward log")
    lines.append(f"└─")
    return '\n'.join(lines)

def to_json(items, seed, root):
    out=[]
    for cnt,proj in items:
        s=project_score(proj, seed)
        out.append({
            'project': str(proj),
            'name': proj.name,
            'py': s['py_n'],
            'entry': s['entry'],
            'cr': s['cr'],
            'market': s['market'],
            'voids': s['voids'],
            'loot_void': s['loot_void'],
            'loot': s['loot'],
            'evidence': s['evidence'],
            'seed': seed,
        })
    return {'seed': seed, 'root': str(root), 'generated_at': datetime.now(timezone.utc).isoformat(), 'void_order': VOID_ORDER, 'void_labels': VOID_LABELS, 'market_weights': MARKET_WEIGHTS, 'items': out}

def to_html(data):
    # skeuomorphic but lightweight — heat map + deck
    items = data['items']
    html = ["""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gap Atlas — seed %d</title><style>
body{margin:0;background:#0f0f0f;color:#e9e6de;font:13px/1.5 ui-monospace,monospace;padding:18px}
.wrap{max-width:1120px;margin:0 auto}
h1{font-size:18px;letter-spacing:.08em;margin:0 0 6px} small{opacity:.6}
.grid{display:grid;grid-template-columns:220px 1fr;gap:12px;margin-top:12px}
.card{background:#1c1c1c;border:1px solid #2a2a2a;border-radius:10px;padding:10px}
.heat{border-collapse:collapse;width:100%%;font-size:11px}
.heat th,.heat td{border:1px solid #222;padding:5px 6px;text-align:center}
.heat th{position:sticky;top:0;background:#1c1c1c}
.v0{background:#142a18;color:#7ee89a}.v3{background:#2a3414;color:#d7e68a}.v6{background:#3a2814;color:#ffb86a}.v8{background:#3a1818;color:#ff8a8a}
.badge{display:inline-block;padding:2px 7px;border-radius:999px;background:#2a2110;border:1px solid #5c3a18;font-size:11px}
.btn{padding:6px 10px;border-radius:8px;border:1px solid #444;background:#222;color:#e9e6de;font-weight:800;cursor:pointer}
.deck{display:flex;gap:10px;flex-wrap:wrap}
.monster{width:220px;background:linear-gradient(#2a2110,#1a1200);border:1px solid #5c3a18;border-radius:10px;padding:10px}
.monster h3{margin:0 0 4px;font-size:12px} .cr{float:right;background:#3a1818;color:#ff8a8a;padding:2px 6px;border-radius:999px;font-size:11px}
</style><div class="wrap"><h1>Gap Atlas — seed %d <small>/ market+scale first / reproducible deck / 7 affordance voids</small></h1><div class="small" style="opacity:.6">CR = market-weighted voids (10=gap). Loot = one close that moves market most. Boss = highest CR. Spelling lol fuck it — scaleablity is the spirit.</div>""" % (data['seed'], data['seed'])]
    html.append('<div class="grid"><div class="card"><h3>Legend</h3>')
    for k in VOID_ORDER:
        html.append(f'<div>{VOID_ICON[k]} <b>{k}</b> — {VOID_LABELS[k]} <span style="opacity:.5">(w {MARKET_WEIGHTS[k]})</span></div>')
    html.append('<div style="margin-top:10px"><span class="badge">Reproducible: seed %d</span> <span class="badge">MRD.tct logged</span></div>' % data['seed'])
    html.append('<div style="margin-top:10px"><button class="btn" onclick="window.print()">print / save PDF</button></div></div>')
    html.append('<div class="card"><h3>Heat Map — CR sorted (market-weighted)</h3><table class="heat"><thead><tr><th>project</th><th>CR</th><th>MKT</th>')
    for k in VOID_ORDER: html.append(f'<th title="{VOID_LABELS[k]}">{VOID_ICON[k]}<br><span style="font-size:9px">{k[:4]}</span></th>')
    html.append('<th>loot</th></tr></thead><tbody>')
    ranked = sorted(items, key=lambda x: -x['cr'])
    for it in ranked[:24]:
        cls = lambda v: 'v0' if v<=2 else 'v3' if v<=5 else 'v6' if v<=7 else 'v8'
        html.append(f'<tr><td style="text-align:left"><b>{it["name"]}</b> <span style="opacity:.5">({it["py"]}py)</span></td><td class="{cls(it["cr"])}">{it["cr"]}</td><td>{it["market"]["index"]}</td>')
        for k in VOID_ORDER:
            html.append(f'<td class="{cls(it["voids"][k])}">{it["voids"][k]}</td>')
        html.append(f'<td style="text-align:left;font-size:10px">{VOID_ICON[it["loot_void"]]} {it["loot"][:56]}</td></tr>')
    html.append('</tbody></table></div></div>')
    html.append('<div class="card" style="margin-top:12px"><h3>Deck — Monster Cards (boss first)</h3><div class="deck">')
    for it in ranked[:8]:
        voids = ' '.join(f'{VOID_ICON[k]}{it["voids"][k]}' for k in VOID_ORDER)
        html.append(f'<div class="monster"><span class="cr">CR {it["cr"]}</span><h3>{it["name"]}</h3><div style="opacity:.7;font-size:10px">{it["py"]}py · {it["entry"]} entry · MKT {it["market"]["index"]} (TAM{it["market"]["tam"]} P{it["market"]["pain"]} R{it["market"]["reach"]})</div><div style="font-size:10px;margin:6px 0">{voids}</div><div style="font-size:11px"><b>Loot:</b> {it["loot"]}</div><div style="font-size:10px;opacity:.6;margin-top:4px">Evid: {",".join(k for k,v in it["evidence"].items() if v)}</div></div>')
    html.append('</div></div>')
    html.append(f'<div style="opacity:.5;margin-top:12px;font-size:11px">Generated {data["generated_at"]} — atlas --seed {data["seed"]} — MRD.tct forward log + pooper quest hooked. Not medical. Not bank. Just a lens.</div></div>')
    return '\n'.join(html)

QUEST_MAP = {
    1: ("distribution", "Make one PATH to run in 2 min: add `python3 main.py --help` + `/health` that prints 200"),
    2: ("monetization", "Park KYC, add gift path: `/gift` behind guard_judo that writes JANUS + MRD.tct"),
    3: ("trust", "Gate it: `python3 -m py_compile` + 1 test with a receipt file (STANK/JANUS)"),
    4: ("retention", "Loop it: one variable-reward + cron that logs every 3rd win (like Jerry's wheelie)"),
    5: ("scale", "Queue it: wrap entry in deque FIFO + guard_judo tarpit/background worker"),
    6: ("discoverability", "Find it: `sherpa --write` + one-line HOW TO RUN at top of README"),
    7: ("cruelty", "Be humane: never rm — humane_cannibal graft `__from_*` + .archive"),
}

def quest_text(quest_n:int, seed:int, boss_name:str):
    if quest_n not in QUEST_MAP:
        return f"No quest {quest_n} — try 1..7 or boss. Seed {seed}, boss {boss_name}."
    void, title = QUEST_MAP[quest_n]
    return f"""You are my Gap Atlas quest coach for 15 min (seed {seed}, boss {boss_name}, void {void}). Market+scale first, gamified but reproducible.

GOAL: Close ONE void: {VOID_LABELS[void]} — quest: {title}

STEPS (one at a time, wait for my paste):
1. Tell me to run: `atlas --seed {seed} --json /tmp/atlas.json` and paste the boss line + its CR + loot void
2. Name the boss's evidence row: which `has_*` are true vs gap vs cruelty vs discoverability — say what one close moves market most
3. Walk me through the loot in 15 min max: give me the exact file to touch, the 10-line diff, and how to verify (`curl /health`, `py_compile`, or `sherpa --write` depending on void)
4. Have me verify and paste the receipt line. If I finish early, offer a 2nd bite: next highest market-weighted void

RULES: Stay reproducible (same seed = same deck). Praise closure, not perfection. If I ask for non-boss project, do it but note boss is where market scale lives.
Start with step 1 now.
"""

def main(argv=None):
    ap=argparse.ArgumentParser(description="Atlas — gamified reproducible gap lens, market+scale first (7 affordance voids, dungeon deck)")
    ap.add_argument("path", nargs="?", default=str(HOME), help="root to index (default: ~)")
    ap.add_argument("--seed", type=int, default=SEED_DEFAULT, help="reproducible seed (default 42, same seed = same deck)")
    ap.add_argument("--max-projects", type=int, default=26, help="cap projects to scan")
    ap.add_argument("--html", dest="html_out", default="", help="write HTML heat map")
    ap.add_argument("--json", dest="json_out", default="", help="write JSON deck")
    ap.add_argument("--quest", type=int, default=None, help="poop a quest card for this void (1..7) into Claude/Gemini app (also prints quest prompt)")
    ap.add_argument("--out", default="", help="write terminal dungeon to file")
    ap.add_argument("--mrd", action="store_true", help="append boss + seed to MRD.tct (meatsuit rundown) automatically")
    ap.add_argument("--no-mrd", dest="no_mrd", action="store_true", help="don't touch MRD.tct")
    args=ap.parse_args(argv)

    root=Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"No such path: {root}"); return 1

    # scope routing — pan-wide only when root == HOME (reproducible, capped), else single-project (fast)
    if root.is_file(): root=root.parent
    items=[]
    is_pan = (root == HOME)
    if is_pan:
        items = discover_projects(root, max_projects=args.max_projects)
    else:
        try:
            _rcnt = len([f for f in root.rglob('*.py') if not any(part in SKIP_DIRS for part in f.parts)])
        except: _rcnt = 0
        items = [(_rcnt, root)]
        if _rcnt < 6:
            for sib in root.parent.iterdir():
                if sib.is_dir() and sib!=root and len(list(sib.rglob('*.py')))>=4:
                    items.append((len(list(sib.rglob('*.py'))), sib))
            items = sorted(items, key=lambda x: -x[0])[:args.max_projects]

    text = render_dungeon_text(items, args.seed, str(root) if root!=HOME else "~ (pan-wide)")
    if args.out:
        Path(args.out).expanduser().write_text(text, encoding='utf-8')
        print(f"Wrote {args.out}")
    print(text)

    data = to_json(items, args.seed, root)
    if args.json_out:
        Path(args.json_out).expanduser().write_text(json.dumps(data, indent=2), encoding='utf-8')
        print(f"Wrote {args.json_out}")
    if args.html_out:
        Path(args.html_out).expanduser().write_text(to_html(data), encoding='utf-8')
        print(f"Wrote {args.html_out}")

    # MRD.tct forward log (meatsuit rundown) — on by default unless --no-mrd or single-file scope tiny
    if not args.no_mrd and (root==HOME or 'tools' in str(root) or 'Official-Vertical-AI-Boardroom' in str(root)):
        try:
            boss = max(items, key=lambda x: project_score(x[1], args.seed)['cr'])
            bs = project_score(boss[1], args.seed)
            line = f"\n### {datetime.now().isoformat()} — Atlas seed {args.seed} — boss {boss[1].name} CR {bs['cr']} MKT {bs['market']['index']} — void {bs['loot_void']} ({bs['voids'][bs['loot_void']]}) — {bs['loot'][:72]}\n"
            # also show top 3 voids
            top3 = sorted(VOID_ORDER, key=lambda k: bs['voids'][k]*MARKET_WEIGHTS[k], reverse=True)[:3]
            line += f"- Rooms: {len(items)} projects, dungeon CR sorted, top voids this boss: {', '.join(f'{k}={bs['voids'][k]}' for k in top3)}\n"
            line += f"- Repro: `atlas --seed {args.seed}` • map `atlas --html /tmp/atlas.html --json /tmp/atlas.json` • quest `atlas --quest {VOID_ORDER.index(bs['loot_void'])+1}`\n"
            if MRD_TCT.exists():
                MRD_TCT.write_text(MRD_TCT.read_text(encoding='utf-8') + line, encoding='utf-8')
        except Exception as e:
            print(f"[atlas] MRD.tct append skipped: {e}")

    if args.quest is not None:
        boss = max(items, key=lambda x: project_score(x[1], args.seed)['cr'])
        boss_name = boss[1].name
        prompt = quest_text(args.quest, args.seed, boss_name)
        print("\n--- QUEST CARD — paste this into Claude / Gemini app (copy-all) ---\n")
        print(prompt)
        print("\n--- end quest ---")
        # also write quest to globs
        qpath = ATLAS_DIR / f"quest-{args.quest}.md"
        qpath.write_text(f"# Quest {args.quest} — seed {args.seed} boss {boss_name}\n\n```\n{prompt}\n```\n", encoding='utf-8')
        print(f"Wrote {qpath}")

    return 0

if __name__=="__main__":
    import sys
    raise SystemExit(main())
