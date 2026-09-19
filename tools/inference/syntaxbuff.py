#!/usr/bin/env python3
"""
SYNTAXBUFF — Puter-powered CLI Agent
BleakNarratives / SyntaxIntelligence
Anchor provides memory. Puter provides inference. Grimoire provides context.
DNA_TAG: ORIGIN=BleakNarratives/SyntaxIntelligence | PILLAR=inference-cli | ROLE=syntaxbuff | LAST_SYNC=2026-08-08

Usage:
    syntaxbuff "your prompt"
    syntaxbuff --model glm "your prompt"
    syntaxbuff --model deepseek --task code "your prompt"
    syntaxbuff --recall          # show anchor memory summary
    syntaxbuff --scry            # pull latest grimoire bus entries
    syntaxbuff --models          # list available models
    syntaxbuff --boardroom "topic"  # fire boardroom at topic
    syntaxbuff --chain <name>    # cast a grimoire chain
    syntaxbuff --boot            # you asked for it
"""

import os
import sys
import json
import sqlite3
import hashlib
import argparse
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
HOME = Path.home()
ANCHOR_DB = HOME / ".anchor.db"
ANCHOR_PERF = HOME / ".anchor_model_perf.json"
GRIMOIRE_BUS = HOME / ".grimoire" / "bus"
GRIMOIRE_WARDS = HOME / ".grimoire" / "wards"
SYNTAX_ROOT = HOME / "SyntaxIntelligence"
MIKEY_SWARM = HOME / "MikeySwarm"
PERSONA_SEED = MIKEY_SWARM / "personas" / "persona_seed.json"
PUTER_TOKEN = HOME / ".puter_token"
SESSION_LOG = HOME / ".syntaxbuff_session.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# MODEL ROSTER — Puter-powered, zero billing to operator
# ─────────────────────────────────────────────────────────────────────────────
MODELS = {
    # ── Primary ──────────────────────────────────────────────────────────────
    "anchor":    {"provider": "puter", "id": "claude-sonnet-4-6",    "role": "memory+reasoning"},
    "deepseek":  {"provider": "openai_compatible", "id": "deepseek-chat", "base_url": "https://api.deepseek.com/v1", "role": "code+architecture"},
    "glm":       {"provider": "puter", "id": "glm-4",                 "role": "lateral+weird"},
    "luna":      {"provider": "puter", "id": "luna",                  "role": "creative+synthesis"},
    "gemini":    {"provider": "puter", "id": "gemini-2.0-flash",      "role": "long-context"},
    "gpt4o":     {"provider": "puter", "id": "gpt-4o",                "role": "general"},
    # ── New Providers ────────────────────────────────────────────────────────
    "cohere":    {"provider": "openai_compatible", "id": "command-r-plus", "base_url": "https://api.cohere.com/v2", "role": "reasoning"},
    "eleven":    {"provider": "media_api", "id": "eleven-turbo", "role": "tts"},
    "stability": {"provider": "media_api", "id": "stable-diffusion-3", "role": "image"},
    "samba":     {"provider": "openai_compatible", "id": "llama3-70b", "base_url": "https://api.sambanova.ai/v1", "role": "fast-reasoning"},
    "aimlapi":   {"provider": "openai_compatible", "id": "meta-llama/Llama-3-70b-Instruct-Turbo", "base_url": "https://api.aimlapi.com/v1", "role": "general"},
    # ── Fallback (OpenRouter direct) ─────────────────────────────────────────
    "qwen":      {"provider": "openrouter", "id": "qwen/qwen3-235b-a22b:free", "role": "fallback"},
    "groq":      {"provider": "groq",       "id": "openai/gpt-oss-120b",      "role": "fast-fallback"},
}

DEFAULT_MODEL = "anchor"

# ─────────────────────────────────────────────────────────────────────────────
# TASK → MODEL routing (FORCE MULTIPLIER HOOK #1)
# Add task types here to auto-route to best model without user thinking about it
# ─────────────────────────────────────────────────────────────────────────────
TASK_ROUTER = {
    "code":        "deepseek",
    "architecture":"deepseek",
    "legal":       "anchor",
    "memory":      "anchor",
    "weird":       "glm",
    "lateral":     "glm",
    "creative":    "luna",
    "synthesis":   "luna",
    "long":        "gemini",
    "context":     "gemini",
    "fast":        "groq",
    "boardroom":   "anchor",  # chairman always anchor
}

# ─────────────────────────────────────────────────────────────────────────────
# EASTER EGG — you asked instead of doing
# ─────────────────────────────────────────────────────────────────────────────
DICKBUTT = r"""
    ▄▀▀▀▄▄▄▄▄▄▄▀▀▀▄
    █▒▒░░░░░░░░░▒▒█
     █░░█░░░░░█░░█
   ▄▄ █░░░▀█▀░░░█ ▄▄
  █░░█ ▀▄░░░░░▄▀ █░░█
  █░░░▀▄▄▄▄▄▄▄▀░░░█
  ▀▄▄░░░░░░░░░░░▄▄▀
    ▀▀▀▀▀▀▀▀▀▀▀▀▀
  SYNTAXBUFF v1.0 — ONLINE
  Puter-powered. Anchor-memoried.
  Built instead of ported.
  Non-negotiable.
"""

# ─────────────────────────────────────────────────────────────────────────────
# ANCHOR MEMORY INTERFACE
# ─────────────────────────────────────────────────────────────────────────────
def anchor_recall(limit=5):
    """Pull recent memory from Anchor's SQLite db."""
    if not ANCHOR_DB.exists():
        return "No anchor.db found. Is this Crostini? Copy from A9 first."
    try:
        conn = sqlite3.connect(ANCHOR_DB)
        cur = conn.cursor()
        # FORCE MULTIPLIER HOOK #2 — extend this query as anchor.db schema is known
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
        summary = [f"Anchor tables: {tables}"]
        for table in tables[:3]:
            cur.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT {limit}")
            rows = cur.fetchall()
            summary.append(f"\n[{table}]")
            for row in rows:
                summary.append(f"  {row}")
        conn.close()
        return "\n".join(summary)
    except Exception as e:
        return f"Anchor recall error: {e}"

def anchor_write(key, value):
    """Write to Anchor memory — persist across sessions."""
    # FORCE MULTIPLIER HOOK #3
    # When anchor.db schema is known, write structured memory here
    # For now, append to session log
    entry = {"ts": datetime.now().isoformat(), "key": key, "value": value}
    with open(SESSION_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

# ─────────────────────────────────────────────────────────────────────────────
# GRIMOIRE BUS INTERFACE
# ─────────────────────────────────────────────────────────────────────────────
def scry_bus(limit=3):
    """Read latest agent bus entries."""
    GRIMOIRE_BUS.mkdir(parents=True, exist_ok=True)
    files = sorted(GRIMOIRE_BUS.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return "Bus is empty. No agents have written yet."
    out = []
    for f in files[:limit]:
        try:
            d = json.loads(f.read_text())
            out.append(f"[{d.get('agent','?')}] {d.get('insight','no insight')[:120]}")
            if d.get('flag'):
                out.append(f" FLAG: {d['flag']}")
        except:
            out.append(f"[unreadable] {f.name}")
    return "\n".join(out)

def write_bus(insight, completed=None, next_suggestion=""):
    """Write SyntaxBuff session to grimoire bus."""
    GRIMOIRE_BUS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    entry = {
        "agent": "syntaxbuff",
        "timestamp": datetime.now().isoformat(),
        "task": "inference session",
        "insight": insight,
        "next_suggestion": next_suggestion,
        "completed": completed or []
    }
    path = GRIMOIRE_BUS / f"syntaxbuff_{ts}.json"
    path.write_text(json.dumps(entry, indent=2))
    return str(path)

# ─────────────────────────────────────────────────────────────────────────────
# PERSONA INJECTION (FORCE MULTIPLIER HOOK #4)
# Loads Mikey persona seed and injects as system prompt prefix
# ─────────────────────────────────────────────────────────────────────────────
def load_persona(path=PERSONA_SEED):
    if not path.exists():
        return ""
    try:
        seed = json.loads(path.read_text())
        weights = seed.get("weights", {})
        style = seed.get("communication_register", "")
        reasoning = seed.get("reasoning_style", "")
        return (
            f"You are operating under the Mikey persona. "
            f"Domain weights: {weights}. "
            f"Reasoning style: {reasoning}. "
            f"Communication: {style}. "
            f"Bias: {', '.join(seed.get('bias_profile', []))}. "
            f"Error handling: {seed.get('error_handling', '')}."
        )
    except:
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# PUTER INFERENCE
# ─────────────────────────────────────────────────────────────────────────────
def call_puter(prompt, model_id, system=None):
    """Call Puter.js inference via Node bridge."""
    bridge = HOME / "bin" / "puter_bridge.js"
    if not bridge.exists():
        bridge = HOME / "tools" / "puter_bridge.js"
    if not bridge.exists():
        raise RuntimeError("puter_bridge.js not found")

    payload = json.dumps({
        "prompt": prompt,
        "model": model_id,
        "system": system or ""
    })

    result = subprocess.run(
        ["node", str(bridge)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"Puter bridge error: {result.stderr[:200]}")
    return result.stdout.strip()

def call_openrouter(prompt, model_id, system=None):
    """Direct OpenRouter fallback."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = json.dumps({"model": model_id, "messages": messages}).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=data, headers=headers
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]

def call_groq(prompt, model_id, system=None):
    """Groq fallback."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = json.dumps({"model": model_id, "messages": messages}).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=data, headers=headers
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]

def call_openai_compatible(prompt, model_id, base_url, system=None):
    """Generic OpenAI-compatible API call."""
    # Derive API key env name based on model ID or provider prefix
    provider_prefix = model_id.split('-')[0].split('/')[0].upper()
    api_key = os.environ.get(f"{provider_prefix}_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(f"API key not set for {model_id} (Expected {provider_prefix}_API_KEY)")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = json.dumps({"model": model_id, "messages": messages}).encode()
    
    # Append chat/completions endpoint suffix
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    req = urllib.request.Request(endpoint, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]

# ─────────────────────────────────────────────────────────────────────────────
# MAIN INFERENCE DISPATCHER (FORCE MULTIPLIER HOOK #5)
# Add new providers here. Model router above auto-selects.
# ─────────────────────────────────────────────────────────────────────────────
def dispatch(prompt, model_key=DEFAULT_MODEL, system=None, inject_persona=False):
    model = MODELS.get(model_key, MODELS[DEFAULT_MODEL])
    provider = model["provider"]
    model_id = model["id"]

    if inject_persona:
        persona = load_persona()
        system = f"{persona}\n\n{system}" if system else persona

    print(f"[syntaxbuff] model={model_key} provider={provider}", file=sys.stderr)

    try:
        if provider == "puter":
            return call_puter(prompt, model_id, system)
        elif provider == "media_api":
            raise NotImplementedError(
                f"Model '{model_id}' is an audio/image model and is not supported in the chat-focused SyntaxBuff interface."
            )
        elif provider == "openai_compatible":
            base_url = model.get("base_url")
            return call_openai_compatible(prompt, model_id, base_url, system)
        elif provider == "openrouter":
            return call_openrouter(prompt, model_id, system)
        elif provider == "groq":
            return call_groq(prompt, model_id, system)
    except Exception as e:
        print(f"[syntaxbuff] {provider} failed: {e} — trying groq fallback", file=sys.stderr)
        try:
            return call_groq(prompt, MODELS["groq"]["id"], system)
        except Exception as e2:
            print(f"[syntaxbuff] groq also failed: {e2} — trying qwen fallback", file=sys.stderr)
            return call_openrouter(prompt, MODELS["qwen"]["id"], system)

# ─────────────────────────────────────────────────────────────────────────────
# LOG SESSION OUTPUT
# ─────────────────────────────────────────────────────────────────────────────
def log_session(prompt, model_key, response):
    entry = {
        "ts": datetime.now().isoformat(),
        "model": model_key,
        "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()[:12],
        "response_hash": hashlib.sha256(response.encode()).hexdigest()[:12],
        "response_preview": response[:100]
    }
    with open(SESSION_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

# ─────────────────────────────────────────────────────────────────────────────
# BOARDROOM SHORTCUT (FORCE MULTIPLIER HOOK #6)
# ─────────────────────────────────────────────────────────────────────────────
def run_boardroom(topic):
    boardroom = HOME / "RootBase" / "Official-Vertical-AI-Boardroom" / "boardroom.py"
    if not boardroom.exists():
        print("boardroom.py not found at canonical location", file=sys.stderr)
        return
    context = {"label": topic, "type": "syntaxbuff_invoke", "raw": topic}
    sys.path.insert(0, str(boardroom.parent))
    from boardroom import run_boardroom as rb
    result = rb(context)
    print(json.dumps(result.get("synthesis", {}), indent=2))

# ─────────────────────────────────────────────────────────────────────────────
# GRIMOIRE CHAIN SHORTCUT
# ─────────────────────────────────────────────────────────────────────────────
def cast_chain(name):
    result = subprocess.run(
        ["bash", str(HOME / "bin" / "grimoire"), "cast", name],
        capture_output=False
    )
    return result.returncode

# ─────────────────────────────────────────────────────────────────────────────
# ANTI-FABRICATION WARD (auto-applied to all logged sessions)
# ─────────────────────────────────────────────────────────────────────────────
WARD_HEADER = "ANTI-FABRICATION WARD ACTIVE. All results require raw source. Truth Sleuth watches."

# ─────────────────────────────────────────────────────────────────────────────
# CLI ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="SyntaxBuff — Puter-powered CLI agent"
    )
    parser.add_argument("prompt", nargs="?", help="Your prompt")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                        choices=list(MODELS.keys()),
                        help="Model to use")
    parser.add_argument("--task", "-t", default=None,
                        choices=list(TASK_ROUTER.keys()),
                        help="Task type — auto-routes to best model")
    parser.add_argument("--persona", "-p", action="store_true",
                        help="Inject Mikey persona seed")
    parser.add_argument("--recall", action="store_true",
                        help="Show Anchor memory summary")
    parser.add_argument("--scry", action="store_true",
                        help="Show latest grimoire bus entries")
    parser.add_argument("--models", action="store_true",
                        help="List available models")
    parser.add_argument("--boardroom", action="store_true",
                        help="Fire boardroom at prompt")
    parser.add_argument("--chain", default=None,
                        help="Cast a grimoire chain by name")
    parser.add_argument("--system", "-s", default=None,
                        help="System prompt override")
    parser.add_argument("--boot", action="store_true",
                        help="You asked for it")

    args = parser.parse_args()

    # ── Easter egg ────────────────────────────────────────────────────────────
    if args.boot:
        print(DICKBUTT)
        print("  Built because porting was someone else's ceiling.")
        print(f"  Models: {', '.join(MODELS.keys())}")
        print(f"  Anchor: {'PRESENT' if ANCHOR_DB.exists() else 'ABSENT — copy from A9'}")
        print(f"  Grimoire bus: {len(list(GRIMOIRE_BUS.glob('*.json')) if GRIMOIRE_BUS.exists() else [])} entries")
        return

    # ── Utility modes ─────────────────────────────────────────────────────────
    if args.recall:
        print(anchor_recall())
        return

    if args.scry:
        print(scry_bus())
        return

    if args.models:
        for k, v in MODELS.items():
            print(f"  {k:12} {v['provider']:12} {v['role']}")
        return

    if args.chain:
        cast_chain(args.chain)
        return

    if not args.prompt:
        parser.print_help()
        return

    # ── Task routing ──────────────────────────────────────────────────────────
    model_key = args.model
    if args.task and args.task in TASK_ROUTER:
        model_key = TASK_ROUTER[args.task]
        print(f"[syntaxbuff] task={args.task} → routed to {model_key}", file=sys.stderr)

    # ── Boardroom mode ────────────────────────────────────────────────────────
    if args.boardroom:
        run_boardroom(args.prompt)
        return

    # ── Standard inference ────────────────────────────────────────────────────
    system = args.system or WARD_HEADER
    response = dispatch(
        args.prompt,
        model_key=model_key,
        system=system,
        inject_persona=args.persona
    )

    print(response)
    log_session(args.prompt, model_key, response)
    write_bus(
        insight=f"Ran {model_key} on: {args.prompt[:60]}",
        next_suggestion="Check session log for drift patterns"
    )

if __name__ == "__main__":
    main()
