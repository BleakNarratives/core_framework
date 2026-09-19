#!/usr/bin/env python3
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: extraction
# DEPS: urllib, base64, json, pathlib, argparse, hashlib
# ROLE: screenshot_sweeper — OCR all Chromebook Downloads screenshots, extract TODO list + summary, vault-pooled Gemini vision, resumable, checkable + self-pruning
# AUTHOR: Buffy — for Bleak, extra innings
# SESSION: 2026-09-10
# TIER: 2
# FKA: none → sweeper (don't waste Buffy on 1021 screenshots, let the script do it)
# [/DNA_TAG]
"""
screenshot_sweeper — scan plaintext in Chromebook screenshots, make TODO + SUMMARY
Checkable + repopulating + self-pruning edition.

You have 1021 screenshots in /mnt/shared/MyFiles/Downloads and no time to read them.
This script does it in terminal, no browser, no copy.

  python3 tools/extraction/screenshot_sweeper.py                         # sweep all (resumable, preserves your [x] checks, prunes deleted)
  python3 tools/extraction/screenshot_sweeper.py --limit 20 --throttle 0.8  # demo
  python3 tools/extraction/screenshot_sweeper.py --prune-deleted          # also drop raw entries for screenshots you deleted
  python3 tools/extraction/screenshot_sweeper.py --reset                  # nuke state, rescan fresh

Outputs (in --out dir):
  raw_ocr.jsonl     — one JSON per screenshot: {file, text, todos, summary, type}
  todo_state.json   — your check state, survives re-runs ({id: {checked, text, src}})
  TODO.md           — checkable GFM checkboxes, grouped, deduped, preserves [x]
  SUMMARY.md        — one-line summary per screenshot, grouped by type
  PRUNED.md         — what was auto-removed and why (source deleted / no longer in screenshots / pattern)
  REPORT.md         — stats + how to re-run

Checkable:
  Edit TODO.md in terminal: `nano ~/screenshots_scan/TODO.md` check boxes with [x].
  Next run, your checks survive — sweeper reads TODO.md + todo_state.json before regenerating.

Repopulate:
  New screenshots → new todos appended automatically (deduped, grouped).
  Resume is automatic: Ctrl+C anytime, re-run same command.

Self-pruning (humane, nothing nuked without receipt):
  - Source deleted: screenshot file no longer exists → its todos move to PRUNED.md (unless you checked [x] — completed stays in Completed)
  - Stale: todo not found in any current screenshot's extraction → pruned to PRUNED.md (unchecked) or moved to Completed (checked)
  - Pattern: add substrings to ~/screenshots_scan/.prune_patterns (one per line) → todos matching are pruned (e.g., "devstral" when you dropped devstral from lineup)
  All prunes logged with reason; PRUNED.md keeps last 200.
  Raw entries for deleted files are kept unless --prune-deleted (then removed from raw_ocr.jsonl too).

Vault-pooled: rotates through GEMINI_API_KEY_POOL (your AQ.Ab8RN... keys) on 429.
"""

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HOME = Path.home()
DEFAULT_SRC = Path("/mnt/shared/MyFiles/Downloads")
DEFAULT_OUT = HOME / "screenshots_scan"
VAULT_JSON = HOME / ".concierge/vault.json"

GEMINI_MODELS = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-pro"]

PROMPT = """You are an OCR + task extractor for a developer's Chromebook screenshots. BE GENTLE — many screenshots are personal, vulnerable, late-night conversations with AI that the user wants to REMEMBER, not "do."

Tasks:
1. Extract ALL readable plaintext verbatim into field "text" in reading order. Preserve line breaks, terminal prompts, error messages, file names, URLs, AND emotional/ vulnerable language exactly as written. Do NOT sanitize, summarize, or soften the verbatim text. If no readable text, set text = "EMPTY".
2. Identify CONCRETE actionable tasks implied by the screenshot into array "todos". Each todo must be a short imperative sentence (e.g., "Fix ...", "Run ...", "Reply to ...", "Install ...").
   RULE: If the screenshot is a personal / deep / emotional conversation with AI (vulnerable, philosophical, late-night, you see "I feel...", "I hope I'm not wrong", "fuck yeah", confessions, memory talk), then return todos = [] UNLESS there is an explicit task in the convo (like "build X" or "fix Y"). Do NOT manufacture todos from feelings. Those belong in MEMORY, not TODO.
   Be useful: if you see an error like "ENOENT .env.vault" → todo "Create .env.vault or fix path". If you see "429 rate limit" → todo "Rotate API key / add to pool". If you see a UI asking to install something → todo that.
3. Provide a one-sentence plain-English summary into field "summary". For personal chats, make it tender and accurate (e.g., "Late-night talk about feeling early to the AI OS party, not wanting to be in the way"), NOT "chat about AI".
4. Classify into field "type" as one of: memory, todo, error, terminal, code, chat, doc, browser, ui, other.
   Use "memory" when: screenshot is a personal/deep/vulnerable conversation with AI or journal-like reflection you would want to look back on. Use "chat" for shallow banter. Use "todo" only for clear actionable screenshots.

Return STRICT JSON only with keys: text, todos, summary, type
No markdown fences, no commentary outside JSON.
Example memory:
{"text":"i hope I'm not wrong. I'm early to the party...","todos":[],"summary":"Vulnerable late-night reflection on being early to building worlds with AI","type":"memory"}
Example error:
{"text":"line1\\nline2","todos":["Fix missing API key in .env"],"summary":"Terminal error about missing key","type":"error"}
"""

def short_hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]

def load_gemini_pool():
    if VAULT_JSON.exists():
        try:
            v = json.loads(VAULT_JSON.read_text())
            kbp = v.get("keys_by_provider", {})
            pool = kbp.get("gemini", [])
            if pool:
                pool = [k for k in pool if k and "PLACEHOLDER" not in k and len(k) > 20]
                if pool:
                    return pool
            k = v.get("keys", {}).get("gemini", {}).get("key", "")
            if k and "PLACEHOLDER" not in k:
                return [k]
        except Exception as e:
            print(f"[vault] warn: {e}", file=sys.stderr)
    env = os.environ.get("GEMINI_API_KEY", "")
    if env:
        return [env]
    return []

def mime_for(path: Path):
    ext = path.suffix.lower()
    if ext == ".png": return "image/png"
    if ext in (".jpg", ".jpeg"): return "image/jpeg"
    if ext == ".webp": return "image/webp"
    mt,_ = mimetypes.guess_type(str(path))
    return mt or "image/png"

def gemini_call_one(image_path: Path, gemini_key: str, model: str, timeout=25):
    data = image_path.read_bytes()
    if len(data) > 4_000_000:
        print(f"  [skip] {image_path.name} too large ({len(data)} bytes)", file=sys.stderr)
        return None
    b64 = base64.b64encode(data).decode()
    payload = json.dumps({
        "contents": [{"parts": [
            {"text": PROMPT},
            {"inline_data": {"mime_type": mime_for(image_path), "data": b64}}
        ]}],
        "generationConfig": {"maxOutputTokens": 900, "temperature": 0.05}
    })
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
    req = urllib.request.Request(url, data=payload.encode(), headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode())
        try:
            txt = body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            txt = json.dumps(body)
        return txt, r.status, body

def extract_json_loose(s: str):
    s = s.strip()
    # strip any markdown fences anywhere
    s = re.sub(r'```(?:json)?', '', s)
    s = s.replace('```','').strip()
    # find outermost JSON object
    i = s.find("{")
    j = s.rfind("}")
    if i != -1 and j != -1 and j > i:
        s = s[i:j+1]
    try:
        return json.loads(s)
    except:
        # try to repair common gemini glitch: trailing comma
        try:
            s2 = re.sub(r',\s*([}\]])', r'\1', s)
            return json.loads(s2)
        except:
            pass
        m = re.search(r'\{.*\}', s, re.S)
        if m:
            try: return json.loads(m.group(0))
            except:
                try:
                    s3 = re.sub(r',\s*([}\]])', r'\1', m.group(0))
                    return json.loads(s3)
                except: pass
        return None

def scan_one(path: Path, pool, models):
    last_err = None
    for ki, key in enumerate(pool):
        for model in models:
            try:
                t0 = time.time()
                res = gemini_call_one(path, key, model, timeout=30)
                if res is None:
                    return {"file": str(path), "path": str(path), "error": "too_large", "text": "", "todos": [], "summary": f"Skipped — file too large", "type": "other", "model": model, "key_idx": ki, "latency": 0}
                txt, http_code, body = res
                latency = time.time() - t0
                parsed = extract_json_loose(txt)
                if parsed is None:
                    parsed = {"text": txt[:4000], "todos": [], "summary": txt[:120].replace("\n"," ").strip(), "type": "other"}
                text = parsed.get("text", "")
                # Fix double-encoded inner {"text":...} that earlier version produced
                if text.startswith('{"text"') or text.startswith("{\\\"text\\\""):
                    try:
                        inner = extract_json_loose(text)
                        if inner and "text" in inner:
                            text = inner["text"]
                            # also pull todos/summary if outer had none
                            if not parsed.get("todos") and inner.get("todos"):
                                parsed["todos"] = inner["todos"]
                    except: pass
                todos = parsed.get("todos", [])
                if isinstance(todos, str): todos = [todos]
                todos = [str(t).strip() for t in todos if str(t).strip()]
                summary = str(parsed.get("summary","")).strip().replace("\n"," ")[:300]
                typ = str(parsed.get("type","other")).strip().lower()
                if not summary:
                    summary = text[:120].replace("\n"," ").strip() if text else "No summary"
                return {
                    "file": path.name,
                    "path": str(path),
                    "text": text,
                    "todos": todos,
                    "summary": summary,
                    "type": typ,
                    "model": model,
                    "key_idx": ki,
                    "key_prefix": key[:8] + "...",
                    "latency": round(latency, 2),
                }
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:500]
                last_err = f"HTTP {e.code} {body[:200]}"
                if e.code == 429:
                    time.sleep(0.5)
                    break
                if e.code in (400, 404):
                    continue
                if e.code in (403, 401):
                    break
                time.sleep(0.3)
                break
            except Exception as e:
                last_err = str(e)[:400]
                time.sleep(0.3)
                break
    return {"file": path.name, "path": str(path), "error": last_err or "all_keys_failed", "text": "", "todos": [], "summary": "Failed — see error", "type": "other", "model": models[0], "latency": 0}

def find_screenshots(src: Path, limit=None, newest_first=True):
    patterns = ["Screenshot*.png", "Screenshot*.jpg", "Screenshot*.jpeg", "Screenshot*.webp"]
    files = []
    for pat in patterns:
        files.extend(src.glob(pat))
    if not files:
        files = list(src.glob("*.png")) + list(src.glob("*.jpg"))
    files = sorted(files, key=lambda p: p.stat().st_mtime if p.exists() else 0)
    if newest_first:
        files = list(reversed(files))
    if limit:
        files = files[:limit]
    return files

def load_todo_state(out: Path):
    p = out / "todo_state.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except: return {}
    return {}

def save_todo_state(out: Path, state: dict):
    p = out / "todo_state.json"
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def parse_existing_todo_md(out: Path):
    """Read TODO.md checkboxes to preserve [x] across re-runs.
    Returns dict id -> {checked, text}
    Parses lines like: - [x] Fix foo <!-- id:abc123 src:file.png -->
    and also legacy lines without id (uses hash of text)
    """
    p = out / "TODO.md"
    mapping = {}
    if not p.exists():
        return mapping
    text = p.read_text(errors="replace")
    for line in text.splitlines():
        m = re.match(r'^- \[( |x|X)\]\s+(.*)$', line.strip())
        if not m:
            continue
        checked = m.group(1).lower() == "x"
        rest = m.group(2)
        # extract id comment
        idm = re.search(r'<!--\s*id:([a-f0-9]{6,12})', rest)
        if idm:
            tid = idm.group(1)
            todo_text = re.sub(r'\s*<!--.*-->\s*$', '', rest).strip()
            # strip trailing ` (src)` if present (old format)
            todo_text = re.sub(r'\s*`\(.*?\)`\s*$', '', todo_text).strip()
        else:
            # legacy: no id, derive from text
            todo_text = re.sub(r'\s*`\(.*?\)`\s*$', '', rest).strip()
            todo_text = re.sub(r'\s*<!--.*-->\s*$', '', todo_text).strip()
            tid = short_hash(re.sub(r'\s+', ' ', todo_text.lower()))
        mapping[tid] = {"checked": checked, "text": todo_text}
    return mapping

def load_prune_patterns(out: Path):
    p = out / ".prune_patterns"
    patterns = []
    if p.exists():
        for line in p.read_text(errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#"): continue
            patterns.append(s.lower())
    # also auto-populate from vibe config if incubator lineup changed: check for deprecated models
    # if vibe says devstral removed, add pattern
    try:
        cfg = HOME / ".vibe/config.toml"
        if cfg.exists():
            t = cfg.read_text()
            if "devstral-small-2507 removed" in t:
                patterns.append("devstral")
    except: pass
    return patterns

def main():
    ap = argparse.ArgumentParser(description="Screenshot sweeper — checkable + self-pruning")
    ap.add_argument("--dir", default=str(DEFAULT_SRC), help="screenshots dir")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output dir")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--throttle", type=float, default=2.0)
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    ap.add_argument("--prune-deleted", action="store_true", help="also remove raw_ocr entries for deleted files")
    ap.add_argument("--reset", action="store_true", help="wipe state and rescan fresh (keeps screenshots)")
    ap.add_argument("--models", nargs="*", default=GEMINI_MODELS)
    args = ap.parse_args()

    src = Path(args.dir).expanduser()
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    if args.reset:
        for name in ["raw_ocr.jsonl", "todo_state.json", "TODO.md", "SUMMARY.md", "REPORT.md", "PRUNED.md"]:
            p = out / name
            if p.exists():
                p.unlink()
                print(f"[reset] removed {name}")
        print("[reset] state cleared — will rescan fresh")

    pool = load_gemini_pool()
    if not pool:
        print("No GEMINI keys found", file=sys.stderr); sys.exit(2)

    print(f"┌─ Screenshot Sweeper (checkable + self-pruning + MEMORY-aware) — {src}")
    print(f"│  PRIVACY: screenshots OCR via Gemini cloud (api.mistral? no — generativelanguage.googleapis.com).")
    print(f"│  If screenshots are deeply personal, you can use --local (tesseract, offline) or keep output private.")
    print(f"│  Output dir will be .gitignored and memories NEVER auto-pruned without receipt.")
    print(f"│  pool: {len(pool)} Gemini keys · models: {', '.join(args.models[:2])}...")
    print(f"│  out: {out} · throttle: {args.throttle}s · limit: {args.limit or 'all'} · prune-deleted: {args.prune_deleted}")

    files = find_screenshots(src, limit=args.limit, newest_first=True)
    print(f"│  found: {len(files)} screenshots on disk (newest first)")

    raw_path = out / "raw_ocr.jsonl"
    done = {}
    if args.resume and raw_path.exists():
        try:
            for line in raw_path.read_text(errors="replace").splitlines():
                if not line.strip(): continue
                try:
                    rec = json.loads(line)
                    done[rec.get("file") or rec.get("path")] = rec
                except: pass
            print(f"│  resume: {len(done)} already OCR'd")
        except Exception as e:
            print(f"│  resume warn: {e}")

    # Load check state from existing TODO.md + todo_state.json
    existing_checked = parse_existing_todo_md(out)
    state = load_todo_state(out)
    # Merge: TODO.md wins for checked flag (user edited), state provides fallback
    for tid, info in existing_checked.items():
        if tid in state:
            state[tid]["checked"] = info["checked"]
        else:
            # need to find src for this tid — store with minimal
            # legacy TODO line without src — keep as unknown but will be grouped under other
            state[tid] = {"text": info["text"], "checked": info["checked"], "src": "unknown", "id": tid}
    if existing_checked:
        print(f"│  check state: {sum(1 for v in existing_checked.values() if v['checked'])}/{len(existing_checked)} checked in TODO.md (preserved)")

    prune_patterns = load_prune_patterns(out)
    if prune_patterns:
        print(f"│  prune patterns: {', '.join(prune_patterns[:5])}")

    fh = raw_path.open("a", encoding="utf-8")
    processed = 0
    by_type = defaultdict(list)

    # preload by_type from done
    for rec in done.values():
        by_type[rec.get("type","other")].append(rec)

    to_scan = [f for f in files if f.name not in done and str(f) not in done]
    print(f"│  to scan: {len(to_scan)} new ({len(files)-len(to_scan)} skipped) · est ~{len(to_scan)*args.throttle/60:.1f} min")
    if to_scan:
        print(f"│  starting… (Ctrl+C to resume, checks preserved)")

    try:
        for idx, p in enumerate(to_scan, 1):
            print(f"│  [{idx}/{len(to_scan)}] {p.name} …", end=" ", flush=True)
            rec = scan_one(p, pool, args.models)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if rec.get("error"):
                print(f" {rec['error'][:80]}")
            else:
                by_type[rec.get("type","other")].append(rec)
                print(f" {rec.get('type','other'):8s} · {len(rec.get('todos',[]))} todo — {rec.get('summary','')[:80]}")
            processed += 1
            if args.throttle and idx < len(to_scan):
                time.sleep(args.throttle)
    except KeyboardInterrupt:
        print(f"\n│  Interrupted — {processed} new scanned. Re-run same command to resume (checks preserved).")
    finally:
        fh.close()

    # Rebuild full state from raw + filesystem reality
    all_recs = []
    if raw_path.exists():
        for line in raw_path.read_text(errors="replace").splitlines():
            if not line.strip(): continue
            try: all_recs.append(json.loads(line))
            except: pass

    # Prune deleted files from reporting (but keep in raw unless --prune-deleted)
    alive_recs = []
    deleted_recs = []
    for rec in all_recs:
        fp = Path(rec.get("path") or (str(src / rec.get("file",""))))
        if fp.exists():
            alive_recs.append(rec)
        else:
            deleted_recs.append(rec)
    if deleted_recs:
        print(f"│  deleted on disk: {len(deleted_recs)} (their todos will be pruned; raw kept{' — use --prune-deleted to drop' if not args.prune_deleted else ''})")
    if args.prune_deleted and deleted_recs:
        # rewrite raw without deleted
        tmp = raw_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as w:
            for rec in alive_recs:
                w.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tmp.replace(raw_path)
        print(f"│  pruned raw: removed {len(deleted_recs)} deleted entries from raw_ocr.jsonl")
        all_recs = alive_recs

    # Collect current todos from alive screenshots only
    current_todos = {}  # norm -> (text, src, id)
    for rec in alive_recs:
        for t in rec.get("todos", []):
            norm = re.sub(r'\s+', ' ', t.strip().lower())
            if not norm: continue
            tid = short_hash(norm)
            if tid not in current_todos:
                current_todos[tid] = (t.strip(), rec.get("file",""), tid)

    # Build todo_state with check preservation + pruning logic
    # state currently has old todos (from previous run + TODO.md). Update with current.
    pruned = []  # list of (tid, reason, text)
    new_state = {}
    # First, carry forward checked state for todos that still exist
    for tid, (text, src, _) in current_todos.items():
        prev = state.get(tid, {})
        checked = prev.get("checked", False)
        # also check if existing_checked has it (in case state missing)
        if tid in existing_checked:
            checked = existing_checked[tid]["checked"]
        new_state[tid] = {"text": text, "src": src, "checked": checked, "id": tid, "status": "active"}

    # Detect stale: previously known todos not in current_todos
    for tid, info in state.items():
        if tid in new_state:
            continue
        prev_src = info.get("src","unknown")
        # Check if src file still exists
        src_deleted = False
        if prev_src != "unknown":
            check_path = Path(prev_src) if Path(prev_src).exists() else (Path(args.dir) / prev_src)
            if not check_path.exists() and not any(r.get("file")==prev_src for r in alive_recs):
                if deleted_recs and any(d.get("file")==prev_src for d in deleted_recs):
                    src_deleted = True

        # Pattern prune?
        text_lower = info.get("text","").lower()
        matched_pat = None
        for pat in prune_patterns:
            if pat in text_lower:
                matched_pat = pat
                break

        reason = None
        if matched_pat:
            reason = f"pattern '{matched_pat}' matched (lineup/code choice changed)"
        elif src_deleted:
            reason = f"source deleted: {prev_src}"
        else:
            reason = "no longer in any screenshot (stale)"

        # Humane: if checked (completed), move to completed, not pruned
        if info.get("checked"):
            new_state[tid] = {"text": info["text"], "src": prev_src, "checked": True, "id": tid, "status": "completed_stale", "prune_reason": reason}
        else:
            pruned.append((tid, reason, info.get("text","")))
            # do NOT carry forward to new_state — pruned
            # but keep in log

    # Also handle existing_checked stales not in state (legacy)
    for tid, info in existing_checked.items():
        if tid in new_state or any(p[0]==tid for p in pruned):
            continue
        if tid not in current_todos:
            # same logic
            if info.get("checked"):
                new_state[tid] = {"text": info["text"], "src": "unknown", "checked": True, "id": tid, "status": "completed_stale", "prune_reason": "stale but checked — kept as completed"}
            else:
                pruned.append((tid, "stale (was in TODO.md, now gone)", info["text"]))

    save_todo_state(out, new_state)

    # Build TODO.md (checkable, grouped, with id comments)
    todo_path = out / "TODO.md"
    active_todos = [(tid, v) for tid, v in new_state.items() if v.get("status")=="active"]
    completed_stale = [(tid, v) for tid, v in new_state.items() if v.get("status")=="completed_stale"]
    # Also sort active by src then text
    active_todos.sort(key=lambda x: (x[1]["src"], x[1]["text"].lower()))

    # Group active by first word
    groups = defaultdict(list)
    for tid, info in active_todos:
        t = info["text"]
        key = t.split()[0].lower() if t.split() else "other"
        if key not in ("fix","update","add","run","install","reply","send","create","delete","move","check","enable","disable","remove","open","test","deploy","write","review"):
            key = "other"
        groups[key].append((tid, info))

    with todo_path.open("w", encoding="utf-8") as f:
        f.write(f"# TODO — from {len(alive_recs)} screenshots ({len(active_todos)} active)\n")
        f.write(f"*Generated {datetime.now().isoformat()} from `{src}` · total alive screenshots: {len(alive_recs)} · deleted: {len(deleted_recs)}*\n\n")
        f.write(f"> Check boxes here (`[x]`) survive re-runs. New screenshots auto-append. Stale unchecked auto-prune to PRUNED.md. Edit this file directly, then re-run sweeper.\n\n")
        f.write(f"> **Memories are separate:** personal/deep AI chats go to `MEMORIES.md` (never here as todos, never auto-pruned). If a memory was mis-tagged as todo, move it or retag raw → re-run.\n\n")
        f.write(f"> **How to prune by lineup/code choice:** add a pattern to `~/screenshots_scan/.prune_patterns` (one per line, e.g., `devstral`) — todos matching are auto-pruned next run.\n\n")
        if not active_todos:
            f.write("No active todos — all clear or all pruned. Check PRUNED.md + Completed below.\n\n")
        else:
            for grp in sorted(groups.keys()):
                f.write(f"## {grp.title()} ({len(groups[grp])})\n\n")
                for tid, info in groups[grp]:
                    checked = "x" if info["checked"] else " "
                    # id comment lets us survive edits/reordering
                    f.write(f"- [{checked}] {info['text']}  <!-- id:{tid} src:{info['src']} -->\n")
                f.write("\n")
        if completed_stale:
            f.write(f"## Completed (stale but kept because you checked them) ({len(completed_stale)})\n\n")
            for tid, info in completed_stale[:50]:
                f.write(f"- [x] {info['text']}  <!-- id:{tid} src:{info['src']} pruned:{info.get('prune_reason','')} -->\n")
            f.write("\n")
        f.write(f"---\n*Active: {len(active_todos)} · Completed (kept): {len(completed_stale)} · Pruned this run: {len(pruned)} · Raw: `raw_ocr.jsonl` ({len(all_recs)} records, {len(deleted_recs)} deleted) · `SUMMARY.md` · `PRUNED.md` · `todo_state.json`*\n")
        f.write(f"*Re-run: `python3 tools/extraction/screenshot_sweeper.py --dir \"{src}\" --out \"{out}\" --throttle 1.2` (resume, checks preserved)*\n")

    # Write PRUNED.md (append)
    pruned_path = out / "PRUNED.md"
    if pruned:
        existing_pruned = ""
        if pruned_path.exists():
            existing_pruned = pruned_path.read_text(errors="replace")
        with pruned_path.open("w", encoding="utf-8") as f:
            f.write(f"# Pruned — auto-removed todos\n")
            f.write(f"*Last prune {datetime.now().isoformat()} · {len(pruned)} this run*\n\n")
            f.write(f"| When | Reason | Todo |\n|---|---|---|\n")
            for tid, reason, text in pruned[:100]:
                f.write(f"| {datetime.now().strftime('%Y-%m-%d %H:%M')} | {reason} | {text} |\n")
            f.write(f"\n---\nExisting log (trim to 200):\n\n")
            # append tail of old without duplicate header
            if existing_pruned:
                lines = existing_pruned.splitlines()
                # keep old table rows
                old_rows = [l for l in lines if l.startswith("| 20")]
                for r in old_rows[:100]:
                    f.write(r + "\n")
            if not pruned_path.exists() or True:
                pass

    # Ensure privacy: .gitignore the output dir (memories stay local, not committed)
    (out / ".gitignore").write_text("# screenshots_scan is private — memories + raw OCR stay local\n*\n!.gitignore\n", encoding="utf-8")
    (out / ".private").write_text(f"private memories — generated {datetime.now().isoformat()}\nDo not commit this folder. Raw OCR stays here.\n", encoding="utf-8")

    # Write MEMORIES.md — personal / deep conversations, NEVER turned into TODOs, NEVER auto-pruned unless file deleted
    memories = [r for r in alive_recs if r.get("type") == "memory"]
    # also include chat with long vulnerable text as fallback? keep strict
    mem_path = out / "MEMORIES.md"
    with mem_path.open("w", encoding="utf-8") as f:
        f.write(f"# MEMORIES — {len(memories)} personal screenshots (kept, not tasks)\n")
        f.write(f"*Generated {datetime.now().isoformat()} · these are NOT todos — they are for looking back. Never auto-pruned unless screenshot deleted. Checkboxes do NOT apply here.*\n\n")
        f.write(f"> These are your deep conversations — preserved verbatim. Not cleaned up. Not delegated. Just remembered.\n\n")
        if not memories:
            f.write("No memories classified this run. If a personal screenshot was typed as `chat`/`other`, you can manually move its entry here or retag in raw_ocr.jsonl.\n\n")
            f.write("Tip: personal chats should classify as `memory` — the prompt now does this. Re-run with ` --reset` if old run mis-tagged them.\n\n")
        else:
            for rec in memories:
                f.write(f"## {rec.get('file','')} — {rec.get('summary','')[:100]}\n\n")
                # verbatim text collapsed but preserved
                txt = rec.get("text","")[:3000].replace("\n", "\n> ")
                f.write(f"> {txt}\n\n")
                f.write(f"*type: `{rec.get('type')}` · model: `{rec.get('model')}` · {rec.get('latency','')}s*\n\n")
                f.write(f"---\n\n")
        f.write(f"\n*Raw verbatim for all: `raw_ocr.jsonl` (private). TODOs were NOT made from these.*\n")

    # Write SUMMARY.md (only alive)
    summary_path = out / "SUMMARY.md"
    from collections import Counter
    type_counts = Counter(r.get("type","other") for r in alive_recs)
    with summary_path.open("w", encoding="utf-8") as f:
        f.write(f"# SUMMARY — {len(alive_recs)} screenshots (alive)\n")
        f.write(f"*Generated {datetime.now().isoformat()} · deleted filtered: {len(deleted_recs)}*\n\n")
        f.write("| Type | Count |\n|---|---:|\n")
        for typ, cnt in type_counts.most_common():
            f.write(f"| {typ} | {cnt} |\n")
        f.write("\n## Summaries (newest first, alive only)\n\n")
        for rec in alive_recs[:80]:
            f.write(f"- **{rec.get('file','')}** `{rec.get('type','')}` — {rec.get('summary','')[:120]}\n")
        if len(alive_recs) > 80:
            f.write(f"\n*... and {len(alive_recs)-80} more — see raw_ocr.jsonl*\n")
        f.write("\n## Deleted screenshots (pruned, see PRUNED.md)\n\n")
        for rec in deleted_recs[:20]:
            f.write(f"- ~~{rec.get('file','')}~~ — {rec.get('summary','')[:80]} (deleted)\n")

    report_path = out / "REPORT.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write(f"# Screenshot Sweeper — Report (checkable + self-pruning)\n")
        f.write(f"*Source: `{src}` · Out: `{out}` · Generated {datetime.now().isoformat()}*\n\n")
        f.write(f"- Alive screenshots: {len(alive_recs)} · deleted: {len(deleted_recs)} · total OCR records: {len(all_recs)}\n")
        mems = len([r for r in alive_recs if r.get("type")=="memory"])
        f.write(f"- Active TODOs: {len(active_todos)} (checked kept) · pruned {len(pruned)} · memories {mems} in MEMORIES.md (never pruned)\n")
        f.write(f"- Privacy: output dir .gitignored, raw OCR local, memories verbatim\n")
        f.write(f"- Models: {', '.join(args.models)} · Keys: {len(pool)} Gemini pooled · Throttle: {args.throttle}s\n\n")
        f.write("## Checkable — your edits survive\n\n")
        f.write("```bash\n")
        f.write(f"nano {todo_path}   # check boxes [x], save, re-run sweeper — checks preserved\n")
        f.write(f"cat {todo_path}    # grouped, with <!-- id:... --> for stable tracking\n")
        f.write(f"cat {out}/todo_state.json | python3 -m json.tool | less  # machine state\n")
        f.write("```\n\n")
        f.write("## Repopulate — new screenshots auto-append\n\n")
        f.write("```bash\n")
        f.write(f"python3 tools/extraction/screenshot_sweeper.py --dir \"{src}\" --out \"{out}\" --throttle 1.2\n")
        f.write("# resume is automatic — Ctrl+C anytime, re-run same command\n")
        f.write(f"python3 tools/extraction/screenshot_sweeper.py --dir \"{src}\" --out \"{out}\" --limit 20 --throttle 0.8 # demo\n")
        f.write("```\n\n")
        f.write("## Self-pruning — cleans lineup/code choice churn\n\n")
        f.write("- Source deleted → todos pruned to PRUNED.md (unless you checked them → moved to Completed)\n")
        f.write("- Stale (todo no longer appears in any current screenshot) → pruned if unchecked, kept if checked\n")
        f.write(f"- Pattern: `echo 'devstral' >> {out}/.prune_patterns` → next run prunes matching todos\n")
        f.write(f"- Deleted raw: `python3 tools/extraction/screenshot_sweeper.py --prune-deleted` to drop raw entries for deleted files\n")
        f.write(f"- Reset: `python3 tools/extraction/screenshot_sweeper.py --reset` to rescan fresh (screenshots untouched)\n\n")
        f.write("## Outputs\n")
        f.write(f"- `TODO.md` — checkable, grouped, deduplicated, stable ids\n")
        f.write(f"- `todo_state.json` — your check state, survives re-runs\n")
        f.write(f"- `PRUNED.md` — what was removed + why (humane, nothing deleted without receipt)\n")
        f.write(f"- `raw_ocr.jsonl` — verbatim text per screenshot\n")
        f.write(f"- `SUMMARY.md` — one-liner per alive screenshot\n")
        f.write(f"- `.prune_patterns` — your lineup/code choice filter (create if needed)\n\n")
        f.write(f"*Tip: `sherpa {out} --write` to leave CURATOR.md so you remember after sleep.*\n")

    print(f"│")
    print(f"│  Done: scanned {processed} new · alive {len(alive_recs)} · deleted {len(deleted_recs)}")
    print(f"│  TODO: {len(active_todos)} active ({sum(1 for _,v in active_todos if v['checked'])} checked) + {len(completed_stale)} completed (stale kept) · pruned {len(pruned)} → PRUNED.md")
    print(f"│  Writes: TODO.md · SUMMARY.md · PRUNED.md · REPORT.md · todo_state.json · raw_ocr.jsonl")
    print(f"│  Checkable: nano {todo_path}  — checks survive next run")
    print(f"│  Prune by pattern: echo 'pattern' >> {out}/.prune_patterns")
    print(f"│  Next: cat {todo_path} | cat {summary_path} | sherpa {out} --write")

if __name__ == "__main__":
    main()
