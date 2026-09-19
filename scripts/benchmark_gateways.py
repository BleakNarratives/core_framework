#!/usr/bin/env python3
"""benchmark_gateways.py — lightweight health/benchmark runner for AI gateway endpoints.

Probes each configured provider with a 1-token chat completion, records timing,
status code, rate-limit headers, and writes a structured JSONL log.

Usage:
    python scripts/benchmark_gateways.py
    python scripts/benchmark_gateways.py --output benchmarks/run.jsonl
    python scripts/benchmark_gateways.py --providers groq openrouter gemini

Environment:
    GROQ_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY, DEEPINFRA_API_KEY,
    CEREBRAS_API_KEY, MISTRAL_API_KEY, OPENAI_API_KEY, SWARMS_API_KEY

No secrets are written to the log. Keys are redacted if present in error bodies.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Gateway catalogue — matches docs/PROVIDER_ENDPOINTS.md
# ---------------------------------------------------------------------------

PROVIDERS: List[Dict[str, Any]] = [
    {
        "name": "groq",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "env_key": "GROQ_API_KEY",
        "model": "openai/gpt-oss-120b",
        "max_tokens": 1,
        "headers": {
            "HTTP-Referer": "https://github.com/molt-living-markdown",
            "X-Title": "MOLT-Benchmark",
        },
    },
    {
        "name": "openrouter",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "env_key": "OPENROUTER_API_KEY",
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "max_tokens": 1,
        "headers": {
            "HTTP-Referer": "https://github.com/molt-living-markdown",
            "X-Title": "MOLT-Benchmark",
        },
    },
    {
        "name": "gemini",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "env_key": "GEMINI_API_KEY",
        "model": "gemini-flash-latest",
        "max_tokens": 1,
        "headers": {},
    },
    {
        "name": "deepinfra",
        "endpoint": "https://api.deepinfra.com/v1/openai/chat/completions",
        "env_key": "DEEPINFRA_API_KEY",
        "model": "meta-llama/Meta-Llama-3.3-70B-Instruct",
        "max_tokens": 1,
        "headers": {},
    },
    {
        "name": "cerebras",
        "endpoint": "https://api.cerebras.ai/v1/chat/completions",
        "env_key": "CEREBRAS_API_KEY",
        "model": "gpt-oss-120b",
        "max_tokens": 1,
        "headers": {
            "HTTP-Referer": "https://github.com/molt-living-markdown",
            "X-Title": "MOLT-Benchmark",
        },
    },
    {
        "name": "mistral",
        "endpoint": "https://api.mistral.ai/v1/chat/completions",
        "env_key": "MISTRAL_API_KEY",
        "model": "mistral-small-latest",
        "max_tokens": 1,
        "headers": {},
    },
    {
        "name": "openai",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "env_key": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
        "max_tokens": 1,
        "headers": {},
    },
    {
        "name": "swarms",
        "endpoint": "https://api.swarms.world/v1/chat/completions",
        "env_key": "SWARMS_API_KEY",
        "model": "gpt-4o-mini",
        "max_tokens": 1,
        "headers": {
            "HTTP-Referer": "https://github.com/molt-living-markdown",
            "X-Title": "MOLT-Benchmark",
        },
    },
    {
        "name": "ollama",
        "endpoint": "http://localhost:11434/v1/chat/completions",
        "env_key": None,
        "model": "llama3",
        "max_tokens": 1,
        "headers": {},
        "local": True,
    },
]

# Cloudflare-protected providers need a real UA or they 403 before auth.
CF_PROVIDERS = {"groq", "cerebras"}

FIXED_PROMPT = "ping"
TIMEOUT_S = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(text: str) -> str:
    """Best-effort redaction of API keys and tokens in error bodies."""
    import re
    patterns = [
        r"sk-or-v1-[A-Fa-f0-9]{32,}",
        r"gsk_[A-Za-z0-9]{20,}",
        r"AIza[0-9A-Za-z\-_]{35}",
        r"Bearer\s+[A-Za-z0-9_\-\.]+",
    ]
    out = text
    for pat in patterns:
        out = re.sub(pat, "[REDACTED]", out, flags=re.IGNORECASE)
    return out


def _extract_rate_limit_headers(headers: Dict[str, str]) -> Dict[str, Any]:
    """Pull standard rate-limit headers into a compact dict."""
    result: Dict[str, Any] = {}
    for key in (
        "x-ratelimit-limit-requests",
        "x-ratelimit-remaining-requests",
        "x-ratelimit-reset-requests",
        "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-reset-tokens",
        "retry-after",
    ):
        if key in headers:
            result[key] = headers[key]
    return result


def _post_chat(
    endpoint: str,
    api_key: Optional[str],
    model: str,
    prompt: str,
    max_tokens: int,
    extra_headers: Dict[str, str],
    local: bool = False,
) -> Dict[str, Any]:
    """Send a minimal chat completion. Returns structured result."""
    headers = {
        "Content-Type": "application/json",
    }
    if api_key and not local:
        headers["Authorization"] = f"Bearer {api_key}"
    headers.update(extra_headers)

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers=headers,
        method="POST",
    )

    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
            return {
                "ok": True,
                "status_code": resp.status,
                "elapsed_ms": elapsed_ms,
                "rate_limit": _extract_rate_limit_headers(dict(resp.headers)),
                "response_preview": _redact(
                    json.dumps(body, ensure_ascii=False)[:300]
                ),
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        raw_body = ""
        try:
            raw_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {
            "ok": False,
            "status_code": exc.code,
            "elapsed_ms": elapsed_ms,
            "rate_limit": _extract_rate_limit_headers(
                {k: v for k, v in exc.headers.items()}
                if exc.headers
                else {}
            ),
            "response_preview": _redact(raw_body[:500]),
            "error": f"HTTP {exc.code}: {exc.reason}",
        }
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "ok": False,
            "status_code": None,
            "elapsed_ms": elapsed_ms,
            "rate_limit": {},
            "response_preview": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def run_benchmark(
    providers: List[Dict[str, Any]],
    prompt: str,
) -> List[Dict[str, Any]]:
    """Run benchmark across providers, returning structured records."""
    results: List[Dict[str, Any]] = []
    ts = _utcnow_iso()

    for p in providers:
        name = p["name"]
        endpoint = p["endpoint"]
        env_key = p.get("env_key")
        api_key = os.environ.get(env_key, "") if env_key else None
        model = p["model"]
        max_tokens = p.get("max_tokens", 1)
        extra_headers = p.get("headers", {})
        local = p.get("local", False)

        if not local and not api_key:
            record = {
                "timestamp": ts,
                "provider": name,
                "endpoint": endpoint,
                "model": model,
                "status_code": None,
                "elapsed_ms": None,
                "rate_limit": {},
                "response_preview": "",
                "error": f"missing env var {env_key}",
                "ok": False,
            }
            results.append(record)
            continue

        # Cloudflare-protected providers need a real UA
        if name in CF_PROVIDERS:
            extra_headers = dict(extra_headers)
            extra_headers.setdefault(
                "User-Agent",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120 Safari/537.36",
            )

        record = {
            "timestamp": ts,
            "provider": name,
            "endpoint": endpoint,
            "model": model,
        }
        result = _post_chat(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            extra_headers=extra_headers,
            local=local,
        )
        record.update(result)
        results.append(record)

    return results


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def write_jsonl(records: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def print_summary(records: List[Dict[str, Any]]) -> None:
    """Print a compact table to stdout."""
    fmt = "{:<12} {:>6} {:>10}  {}"
    print(fmt.format("PROVIDER", "STATUS", "MS", "NOTE"))
    print("-" * 60)
    for rec in records:
        status = str(rec.get("status_code") or "----")
        ms = f"{rec['elapsed_ms']:.1f}" if rec.get("elapsed_ms") is not None else "  ---"
        if rec.get("ok"):
            note = "ok"
        else:
            err = rec.get("error") or "unknown"
            note = err[:40]
        print(fmt.format(rec["provider"], status, ms, note))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Benchmark AI gateway endpoints and write a JSONL log.",
    )
    p.add_argument(
        "--output", "-o",
        default="benchmark_gateways.jsonl",
        help="Path for JSONL log (default: benchmark_gateways.jsonl)",
    )
    p.add_argument(
        "--prompt", "-p",
        default=FIXED_PROMPT,
        help=f"Test prompt (default: {FIXED_PROMPT!r})",
    )
    p.add_argument(
        "--providers",
        nargs="*",
        default=None,
        help="Subset of provider names to test (default: all)",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    pool = PROVIDERS
    if args.providers:
        wanted = {n.lower() for n in args.providers}
        pool = [p for p in PROVIDERS if p["name"].lower() in wanted]
        if not pool:
            print(f"No matching providers for: {', '.join(args.providers)}", file=sys.stderr)
            return 2

    print(f"Benchmarking {len(pool)} gateway(s) …")
    records = run_benchmark(pool, prompt=args.prompt)
    write_jsonl(records, args.output)
    print_summary(records)
    print(f"\nLog written to: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
