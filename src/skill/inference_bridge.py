"""
MOLT Inference Bridge — one-shot API wrapper that nixes tool-call loops.
Hydrates Living SKILL.md via SkillManager and tosses the hydrated prompt
at the local AI gateway in a single call — no MCP, no tool schema, no bloat.

Routes through `http://127.0.0.1:7071/v1/auto`: the gateway is the only
component that holds provider keys, and it walks the live chain
(groq -> swarms -> openrouter) so this bridge inherits fallback for free.

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
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, List, Dict, Any

from .skill_manager import SkillManager

# All inference goes through the local gateway, the only component that holds
# provider keys (see ~/.config/ai/config.toml). This replaces the old SyntaxBuff
# dispatch + raw OPENROUTER_API_KEY/GROQ_API_KEY fallback, which bypassed the
# gateway's live provider chain entirely.
GATEWAY_BASE = os.environ.get("AI_GATEWAY_URL", "http://127.0.0.1:7071/v1/auto")

# ── Bitchwork Guardrail ──────────────────────────────────────────
SYSTEM_BITCHWORK_SUFFIX = """
[EXECUTION CONTRACT]
Perform your full persona-based architectural review.
At the very end of your response, output a final JSON decision block enclosed in ```json ... ```:

{
   "persona": "<PersonaName>",
   "status": "APPROVED | REJECTED | WARNING",
   "code": "NONE | ERR_SCHEMA_VIOLATION | ERR_SCHEMA_FAIL | ERR_SECURITY_SINK | ERR_MARGIN_EXCEEDED",
   "patch": "<git diff string or null>"
}
"""

def sanitize_persona_output(raw_output: str, persona_name: str) -> dict:
    """
    Enforces machine-readable parsing on agent output.
    Separates the persona's internal monologue from the clean JSON contract.
    Returns a dict containing both the full trace for logging and clean payload.
    """
    import json
    import re

    try:
        # 1. Extract explicit ```json ... ``` block
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_output, re.DOTALL)
        
        # 2. Fallback: scan for last valid raw JSON object matching schema
        if not json_match:
            json_match = re.search(r'(\{[\s\S]*?"persona"[\s\S]*?\})', raw_output)

        if not json_match:
            raise ValueError("No valid JSON execution block detected in persona output.")

        payload = json.loads(json_match.group(1))

        # 3. Verify required keys
        required_keys = {"persona", "status", "code", "patch"}
        if not required_keys.issubset(payload.keys()):
            raise ValueError("Missing required schema keys in extracted payload.")

        return {
            "raw_trace": raw_output,
            "sanitized_payload": payload,
            "status": "OK"
        }

    except Exception as e:
        return {
            "raw_trace": raw_output,
            "sanitized_payload": {
                "persona": persona_name,
                "status": "REJECTED",
                "code": "ERR_SCHEMA_VIOLATION",
                "patch": None,
                "error_detail": f"Model breached Bitchwork Protocol: {str(e)}"
            },
            "status": "SCHEMA_ERROR"
        }

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
    
    # Inject Bitchwork Guardrail into the system prompt
    if messages:
        messages[0]["content"] += f"\n\n{SYSTEM_BITCHWORK_SUFFIX}"

    if dry_run:
        # Return hydrated system + user concat for inspection
        return json.dumps(messages, indent=2, ensure_ascii=False)

    # Route through the local gateway: it owns the provider keys and walks the
    # live chain, so this call inherits fallback for free. `model`/`provider` are
    # retained for signature compatibility but the chain now selects the pool.
    return _call_gateway(messages, model="auto", timeout=timeout)

def molt_one_shot_sanitized(skill_name: str, user_query: str, **kwargs) -> Dict[str, Any]:
    """Wrapper that enforces Bitchwork Protocol on the output.

    Persists the sanitized envelope, not just the raw text. The raw-only
    record made src/ui/visualizer.py unreadable: it looks up
    `sanitized_payload` on the last line, which never appeared there.
    """
    raw_output = molt_one_shot(skill_name, user_query, **kwargs)
    result = sanitize_persona_output(raw_output, skill_name)
    Path(".boardroom_history.jsonl").parent.mkdir(parents=True, exist_ok=True)
    with open(".boardroom_history.jsonl", "a", encoding="utf-8") as f:
        # `raw` kept alongside the envelope so earlier readers keep working.
        f.write(json.dumps({"skill": skill_name, "raw": raw_output, **result}) + "\n")
    return result


def _call_gateway(messages: List[Dict[str, str]], model: str = "auto",
                  timeout: int = 90) -> str:
    """One-shot chat completion via the local AI gateway (/v1/auto).

    No provider key is read here — the gateway owns them and walks its live
    chain. Raises if the gateway is unreachable so the caller does not silently
    fall back to a key-holding path.
    """
    payload = json.dumps({"model": model, "messages": messages}).encode()
    req = urllib.request.Request(
        f"{GATEWAY_BASE.rstrip('/')}/chat/completions",
        data=payload, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except Exception as e:
        raise RuntimeError(
            f"AI gateway unreachable at {GATEWAY_BASE} ({e}). "
            "Start it with: systemctl --user start ai-gateway"
        ) from e
    return data["choices"][0]["message"]["content"]


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
        messages = []
        if args.system:
            messages.append({"role": "system", "content": args.system})
        messages.append({"role": "user", "content": args.prompt})
        print(_call_gateway(messages, model="auto"))
        return 0

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
