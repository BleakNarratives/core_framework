"""
MOLT Inference Bridge — one-shot API wrapper that nixes tool-call loops.
Hydrates Living SKILL.md via SkillManager and tosses the hydrated prompt
at any inference API in a single call — no MCP, no tool schema, no bloat.

Supports: Puter bridge, OpenRouter, Groq, Gemini, generic OpenAI-compatible.

Usage (Python):
    from src.skill.inference_bridge import molt_one_shot
    text = molt_one_shot("med-triage-copilot", "triage this intake: ...", oomf_level=3)

Usage (CLI):
    python -m src.skill.inference_bridge --skill med-triage-copilot --oomf 3 "triage: ..."
    vibe "build disaster triage unit --oomf 5 --elevate network,write"
    # The vibe wrapper can call hydrate_for_api internally if patched (see below).

Zero-bloat: if no skill name is passed, bridge is a plain passthrough.
"""
import os
import sys
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, List, Dict, Any

from .skill_manager import SkillManager

# Reuse SyntaxBuff model routing if available
try:
    from tools.inference.syntaxbuff import dispatch as buff_dispatch  # type: ignore
    HAS_BUFF = True
except Exception:
    HAS_BUFF = False

# ── Core one-shot ────────────────────────────────────────────────
def molt_hydrate(skill_name: str, user_query: str,
                 oomf_level: Optional[int] = None,
                 system_prefix: str = "",
                 max_chars: int = 6000,
                 gambit=None,
                 user_id: Optional[str] = None) -> List[Dict[str, str]]:
    """Build messages array via SkillManager — no network. Gambit-gated if passed."""
    mgr = SkillManager()
    return mgr.hydrate_for_api(skill_name, user_query,
                               oomf_level=oomf_level,
                               system_prefix=system_prefix,
                               gambit=gambit, user_id=user_id)


def molt_one_shot(skill_name: str, user_query: str,
                  oomf_level: Optional[int] = None,
                  model: str = "anchor",
                  provider: Optional[str] = None,
                  system_prefix: str = "",
                  timeout: int = 90,
                  dry_run: bool = False,
                  gambit=None,
                  user_id: Optional[str] = None) -> str:
    """
    Hydrate skill + call inference in one shot. No tool loop.
    - skill_name: Living SKILL.md name (e.g. "med-triage-copilot")
    - oomf_level: 1-5 overrides frontmatter depth (still capped by gambit if active)
    - model/provider: dispatch hint (uses SyntaxBuff routing if available)
    - dry_run: return hydrated prompt without calling API (for tests/docs)
    - gambit/user_id: if passed, hydrate is instar-gated + auto-OOMF
    """
    messages = molt_hydrate(skill_name, user_query, oomf_level=oomf_level,
                            system_prefix=system_prefix,
                            gambit=gambit, user_id=user_id)
    if dry_run:
        # Return hydrated system + user concat for inspection
        return json.dumps(messages, indent=2, ensure_ascii=False)

    # Extract system + user for legacy dispatchers
    system = messages[0]["content"] if messages else ""
    prompt = messages[1]["content"] if len(messages) > 1 else user_query

    # Prefer SyntaxBuff dispatch (Puter/Groq/OpenRouter routing)
    if HAS_BUFF:
        try:
            # buff_dispatch expects (prompt, model_key, system)
            # model param maps to buff model keys
            return buff_dispatch(prompt, model_key=model, system=system)
        except Exception as e:
            print(f"[molt] buff dispatch failed: {e} — trying generic", file=sys.stderr)

    # Fallback: direct OpenRouter if key present
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GROQ_API_KEY")
    if key:
        return _call_openrouter_generic(messages, key, timeout=timeout)

    # Last resort: return dry_run hint
    raise RuntimeError(
        "No inference backend available. Set OPENROUTER_API_KEY/GROQ_API_KEY or ensure "
        "SyntaxBuff Puter bridge is configured. Use dry_run=True to inspect hydrated prompt."
    )


def _call_openrouter_generic(messages: List[Dict[str, str]], api_key: str,
                             model: str = "openai/gpt-oss-120b",
                             base_url: str = "https://openrouter.ai/api/v1/chat/completions",
                             timeout: int = 90) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/molt-living-markdown",
        "X-Title": "MOLT",
    }
    payload = json.dumps({"model": model, "messages": messages}).encode()
    req = urllib.request.Request(base_url, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]


# ── Vibe/Codebuff shim ───────────────────────────────────────────
def patch_vibe_argv(argv: List[str]) -> tuple:
    """
    Parse MOLT flags out of a freeform vibe prompt without breaking vibe.
    e.g. 'build triage unit --oomf 5 --elevate network,write'
    Returns (cleaned_prompt, oomf, elevate_scopes).
    This can be called from bin/vibe or tools/inference/syntaxbuff.py.
    """
    from .governor import Governor
    flags = Governor.parse_cli_flags(argv)
    # Strip MOLT flags from argv for passthrough
    cleaned = []
    skip_next = False
    for i, tok in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if tok == "--oomf" and i + 1 < len(argv):
            skip_next = True
            continue
        if tok.startswith("--oomf="):
            continue
        if tok == "--elevate":
            # consume following scope tokens until next flag
            j = i + 1
            while j < len(argv) and not argv[j].startswith("--"):
                j += 1
            # skip elevate + scopes
            cleaned.extend(argv[j:])
            break
        if tok.startswith("--elevate"):
            continue
        if tok == "--elevate-ttl":
            skip_next = True
            continue
        cleaned.append(tok)
    prompt = " ".join(cleaned).strip()
    return prompt, flags["oomf_level"], flags["elevate_scopes"]


# ── CLI ──────────────────────────────────────────────────────────
def _cli():
    import argparse
    p = argparse.ArgumentParser(description="MOLT one-shot inference bridge (no MCP, no tool loop)")
    p.add_argument("prompt", nargs="?", help="User prompt (or bare query if --skill omitted)")
    p.add_argument("--skill", "-s", default=None, help="Living SKILL.md name to hydrate")
    p.add_argument("--oomf", type=int, default=None, choices=range(1, 6), help="OOMF depth 1-5")
    p.add_argument("--model", "-m", default="anchor", help="Model key (anchor/deepseek/glm/...)")
    p.add_argument("--dry-run", action="store_true", help="Print hydrated prompt, don't call API")
    p.add_argument("--system", default="", help="Extra system prefix")
    p.add_argument("--list-skills", action="store_true", help="List available Living skills")
    args = p.parse_args()

    if args.list_skills:
        mgr = SkillManager()
        for name in mgr.list_skills():
            front = mgr.parse_frontmatter(name)
            print(f"{name:<32} depth:{front.get('scout',{}).get('depth',3)}  oracle:{front.get('oracle',{}).get('mode','strict')}")
        return 0

    if not args.prompt:
        p.print_help()
        return 0

    skill = args.skill
    # also support inline --oomf in prompt
    if not args.oomf and args.prompt and "--oomf" in args.prompt:
        cleaned, oomf, _ = patch_vibe_argv(args.prompt.split())
        if oomf:
            args.oomf = oomf
            args.prompt = cleaned
            print(f"[molt] inline --oomf {oomf} detected", file=sys.stderr)

    if not skill:
        # passthrough without hydration
        print("[molt] no --skill, passthrough", file=sys.stderr)
        if args.dry_run:
            print(args.prompt)
            return 0
        if HAS_BUFF:
            print(buff_dispatch(args.prompt, model_key=args.model, system=args.system))
            return 0
        print("Set --skill or OPENROUTER_API_KEY", file=sys.stderr)
        return 1

    out = molt_one_shot(skill, args.prompt, oomf_level=args.oomf,
                        model=args.model, system_prefix=args.system,
                        dry_run=args.dry_run)
    # Hive: optional Whorl bus deposit of hydrate so headless/Termux/Chromebook nodes see it
    if skill and not args.dry_run:
        try:
            from .whorl_bus import WhorlBusDispatcher
            WhorlBusDispatcher(agent_name="molt-inference", auto_register=False).send_molt_hydrate(
                skill, out[:6000], oomf_level=args.oomf or 3, recipients=["broadcast"])
        except Exception:
            pass
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
