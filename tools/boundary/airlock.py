#!/usr/bin/env python3
"""airlock — nothing leaves unsanitized.

WHY THIS EXISTS
---------------
This tree contains live credentials inside files named like conversation logs.
GitHub push protection blocked three pushes over exactly this: live Neo4j
credentials and GCP service-account keys sitting inside AI chat transcripts
(vai_output_vai_*.json). Every cloud call made from this machine risks
uploading a secret, because the material being sent *is* the codebase.

So the boundary is the product. Everything outbound passes through one gate,
and what cannot be sanitized does not leave.

THE DECISION (one place, one rule)
----------------------------------
                    ┌─ secret found, strict mode ──▶ LOCAL ONLY
    text ──▶ scan ───┼─ secret found, redact mode ──▶ redact ──▶ CLOUD
                    └─ clean ─────────────────────▶ CLOUD
                              cloud unavailable ───▶ LOCAL (degraded)

The local model is not a fallback for *capability* — a 0.5B model cannot reason
about a codebase. It is a fallback for two narrow things: availability when
cloud keys are exhausted (402/429), and the specific calls the gate refuses to
release. Degraded but safe beats clever but leaky.

USAGE
-----
  airlock rules                 what it detects, by tier
  airlock check <file|->        exit 1 if anything sensitive is present
  airlock redact <file|->       print sanitized text
  airlock route <file|->        print the routing decision and why
  airlock scan --index          which of YOUR files must never leave
  airlock probe                 is cloud reachable? is a local model up?

Exit codes: 0 clean, 1 findings, 2 error. Never prints a full secret.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

VERSION = "1.0.0"
HOME = Path.home()
ARIADNE_DB = HOME / ".local/share/ariadne/index.db"
VAULT = HOME / ".concierge/vault.json"
LOCAL_ENDPOINT = os.environ.get("AIRLOCK_LOCAL_ENDPOINT", "http://localhost:11434")
CLOUD_KEY_FILES = (VAULT,)
CLOUD_ENV_KEYS = ("GROQ_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "CEREBRAS_API_KEY")

TIERS = ("critical", "high", "medium", "personal")
TIER_RANK = {t: i for i, t in enumerate(TIERS)}


# --- detection rules --------------------------------------------------------
# Order matters only for reporting; all rules are applied.
RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    # --- credentials that grant access to something -------------------------
    ("private-key", "critical", re.compile(r"-----BEGIN [A-Z ]{0,32}PRIVATE KEY-----")),
    ("gcp-service-account", "critical", re.compile(r'"type"\s*:\s*"service_account"')),
    ("gcp-private-key-id", "critical", re.compile(r'"private_key_id"\s*:')),
    ("aws-access-key", "critical", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("openai-key", "critical", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("openrouter-key", "critical", re.compile(r"\bsk-or-v1-[A-Fa-f0-9]{32,}")),
    ("groq-key", "critical", re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("google-api-key", "critical", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("anthropic-key", "critical", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("cerebras-key", "critical", re.compile(r"\bcsk-[A-Za-z0-9]{20,}")),
    ("huggingface-token", "critical", re.compile(r"\bhf_[A-Za-z0-9]{20,}")),
    ("github-token", "critical", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}")),
    ("slack-token", "critical", re.compile(r"\bxox[abpsr]-[A-Za-z0-9\-]{10,}")),
    ("stripe-key", "critical", re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("db-uri-with-creds", "critical",
     re.compile(r"\b(?:neo4j|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|bolt)"
                r"://[^:@\s/]+:[^@\s]{3,}@", re.I)),
    # --- tokens that may be expired but are still identity ------------------
    ("jwt", "high", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}")),
    ("oauth-token", "high", re.compile(r"\bya29\.[A-Za-z0-9_\-]{20,}")),
    ("assigned-secret", "high",
     re.compile(r"(?i)\b(?:password|passwd|pwd|secret|api_?key|access_token|auth_token"
                r"|client_secret|private_key|web_secret_key)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
    ("basic-auth-url", "high", re.compile(r"://[^:@\s/]{2,}:[^@\s]{6,}@", re.I)),
    # --- money and identity -------------------------------------------------
    ("lightning-address", "personal",
     re.compile(r"\b[A-Za-z0-9._%+\-]+@(?:strike\.me|coinos\.io|getalby\.com|zbd\.gg"
                r"|walletofsatoshi\.com|blink\.sv)\b", re.I)),
    ("monero-address", "personal", re.compile(r"\b4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b")),
    ("bitcoin-address", "personal", re.compile(r"\bbc1[a-z0-9]{25,62}\b")),
    ("eth-address", "personal", re.compile(r"\b0x[a-fA-F0-9]{40}\b")),
    ("email-address", "personal",
     re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("us-phone", "personal", re.compile(r"\b\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")),
    # --- noisy but revealing ------------------------------------------------
    ("bearer-token", "medium", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.]{20,}")),
    ("long-hex-blob", "medium", re.compile(r"\b[A-Fa-f0-9]{64,}\b")),
)


# Cheap literal prescreens. ``str in text`` runs at C speed, so most rules never
# reach a regex. Without this, scanning tens of thousands of files takes minutes;
# with it, the work collapses to the handful of files that could possibly match.
# A rule absent from this map is always evaluated.
_PRESCREEN: dict[str, tuple[str, ...]] = {
    "private-key": ("PRIVATE KEY",),
    "gcp-service-account": ("service_account",),
    "gcp-private-key-id": ("private_key_id",),
    "aws-access-key": ("AKIA", "ASIA"),
    "openai-key": ("sk-",),
    "openrouter-key": ("sk-or-",),
    "groq-key": ("gsk_",),
    "google-api-key": ("AIza",),
    "anthropic-key": ("sk-ant-",),
    "cerebras-key": ("csk-",),
    "huggingface-token": ("hf_",),
    "github-token": ("ghp_", "gho_", "ghu_", "ghs_", "ghr_"),
    "slack-token": ("xox",),
    "stripe-key": ("sk_live", "sk_test", "rk_live", "rk_test"),
    "db-uri-with-creds": ("://",),
    "jwt": ("eyJ",),
    "oauth-token": ("ya29.",),
    "assigned-secret": ("password", "passwd", "pwd", "secret", "api_key", "apikey",
                        "access_token", "auth_token", "private_key", "web_secret_key"),
    "basic-auth-url": ("://",),
    "lightning-address": ("@strike.me", "@coinos.io", "@getalby.com", "@zbd.gg",
                          "@walletofsatoshi.com", "@blink.sv"),
    "monero-address": ("4", "8"),
    "bitcoin-address": ("bc1",),
    "eth-address": ("0x",),
    "email-address": ("@",),
    "us-phone": ("-", ")", " "),
    "bearer-token": ("earer",),
    "long-hex-blob": ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"),
}


@dataclass
class Finding:
    rule: str
    tier: str
    start: int
    end: int
    preview: str          # masked, never the full secret
    fingerprint: str      # stable hash so the same secret correlates across files


def _mask(value: str) -> str:
    """Never reveal a secret. Show enough to recognize, not enough to use."""
    v = value.strip()
    if len(v) <= 8:
        return "*" * len(v)
    return f"{v[:3]}{'*' * min(len(v) - 5, 24)}{v[-2:]} ({len(v)} chars)"


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:10]


def scan(text: str, min_tier: str = "personal") -> list[Finding]:
    floor = TIER_RANK[min_tier]
    out: list[Finding] = []
    for rule, tier, rx in RULES:
        if TIER_RANK[tier] > floor:
            continue
        pre = _PRESCREEN.get(rule)
        if pre is not None and not any(s in text for s in pre):
            continue
        for m in rx.finditer(text):
            out.append(Finding(rule, tier, m.start(), m.end(),
                               _mask(m.group(0)), _fingerprint(m.group(0))))
    out.sort(key=lambda f: (f.start, f.end))
    return out


def highest_tier(findings: list[Finding]) -> str | None:
    if not findings:
        return None
    return min((f.tier for f in findings), key=lambda t: TIER_RANK[t])


def redact(text: str, findings: list[Finding]) -> str:
    """Replace spans with a fingerprinted marker.

    The fingerprint is the point: you can tell that the same secret appears in
    two files without either file revealing it.
    """
    out = []
    cursor = 0
    for f in findings:
        if f.start < cursor:
            continue
        out.append(text[cursor:f.start])
        out.append(f"[REDACTED:{f.rule}:{f.fingerprint}]")
        cursor = f.end
    out.append(text[cursor:])
    return "".join(out)


# --- routing ----------------------------------------------------------------
def cloud_keys_present() -> dict[str, str]:
    """Which cloud providers actually have a usable key, and where it came from.

    The vault's real schema is {"keys": {"<provider>": {"key": ..., "env_var": ...}}}
    -- NOT flat GROQ_API_KEY names. Reading it the flat way silently reported zero
    credentials, which would have made every routing decision wrong.
    """
    present: dict[str, str] = {}
    for k in CLOUD_ENV_KEYS:
        if os.environ.get(k):
            present[k] = "environment"

    for path in CLOUD_KEY_FILES:
        try:
            blob = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(blob, dict):
            continue

        # nested schema: keys -> provider -> {key, env_var, status}
        keys = blob.get("keys")
        if isinstance(keys, dict):
            for provider, entry in keys.items():
                if not isinstance(entry, dict):
                    continue
                if entry.get("status") and str(entry["status"]).lower() in {"dead", "revoked", "invalid"}:
                    continue
                if entry.get("key"):
                    name = entry.get("env_var") or f"{provider.upper()}_API_KEY"
                    present[name] = f"vault:{provider}"

        # tolerate a flat schema too
        for k in CLOUD_ENV_KEYS:
            if isinstance(blob.get(k), str) and blob[k]:
                present.setdefault(k, "vault:flat")
    return present


def local_model_up(timeout: float = 1.5) -> bool:
    """Is a local inference server actually listening?

    llama.cpp and Ollama expose DIFFERENT endpoints: llama-server serves
    ``/health``, Ollama serves ``/api/tags``. Checking only the Ollama path made
    the local fallback invisible when running llama.cpp, which silently turned
    both local routing branches into dead ends.
    """
    import urllib.error
    import urllib.request
    for path in ("/health", "/api/tags"):
        try:
            with urllib.request.urlopen(f"{LOCAL_ENDPOINT}{path}", timeout=timeout) as resp:
                if 200 <= getattr(resp, "status", 200) < 300:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return False


def route(text: str, mode: str, min_tier: str = "personal") -> dict:
    findings = scan(text, min_tier)
    tier = highest_tier(findings)
    blocking = [f for f in findings if TIER_RANK[f.tier] <= TIER_RANK["high"]]

    if mode == "off":
        return {"target": "cloud", "reason": "gate disabled (--mode off)", "findings": findings}

    if blocking and mode == "strict":
        return {"target": "local",
                "reason": f"{len(blocking)} credential-shaped match(es); strict mode refuses cloud",
                "findings": findings}

    if blocking and mode == "redact":
        if not cloud_keys_present():
            return {"target": "local",
                    "reason": "no cloud credentials configured; degraded local answer",
                    "findings": findings}
        return {"target": "cloud",
                "reason": f"redacted {len(blocking)} credential-shaped match(es) before send",
                "findings": findings}

    if not cloud_keys_present():
        return {"target": "local", "reason": "no cloud credentials configured", "findings": findings}
    return {"target": "cloud", "reason": f"clean at tier >= {min_tier}", "findings": findings}


# --- commands ---------------------------------------------------------------
def _read(target: str) -> str:
    if target in ("-", "/dev/stdin"):
        return sys.stdin.read()
    return Path(target).expanduser().read_text(encoding="utf-8", errors="replace")


def cmd_rules(args) -> int:
    print(f"{'rule':<24}{'tier':<10}pattern")
    print("-" * 78)
    for rule, tier, rx in RULES:
        pat = rx.pattern if len(rx.pattern) < 44 else rx.pattern[:41] + "..."
        print(f"{rule:<24}{tier:<10}{pat}")
    counts = {t: sum(1 for _, x, _ in RULES if x == t) for t in TIERS}
    print("-" * 78)
    print("  ".join(f"{t}={counts[t]}" for t in TIERS))
    return 0


def cmd_check(args) -> int:
    text = _read(args.target)
    findings = scan(text, args.min_tier)
    if not findings:
        print(f"airlock: CLEAN ({len(text):,} chars, tier >= {args.min_tier})")
        return 0
    by_rule: dict[str, list[Finding]] = {}
    for f in findings:
        by_rule.setdefault(f.rule, []).append(f)
    print(f"airlock: {len(findings)} finding(s) at tier >= {args.min_tier} "
          f"— highest: {highest_tier(findings)}")
    for rule, group in sorted(by_rule.items(), key=lambda kv: TIER_RANK[kv[1][0].tier]):
        for f in group[:4]:
            print(f"  [{f.tier:<8}] {rule:<22} {f.preview}  fp={f.fingerprint}")
        if len(group) > 4:
            print(f"             ... +{len(group)-4} more {rule}")
    return 1


def cmd_redact(args) -> int:
    text = _read(args.target)
    findings = scan(text, args.min_tier)
    result = redact(text, findings)
    if args.stats:
        print(f"airlock: redacted {len(findings)} match(es)", file=sys.stderr)
    sys.stdout.write(result)
    if not result.endswith("\n"):
        sys.stdout.write("\n")
    return 1 if findings else 0


def cmd_route(args) -> int:
    text = _read(args.target)
    decision = route(text, args.mode, args.min_tier)
    print(f"target : {decision['target'].upper()}")
    print(f"reason : {decision['reason']}")
    print(f"findings: {len(decision['findings'])}")
    for f in decision["findings"][:8]:
        print(f"  [{f.tier:<8}] {f.rule:<22} {f.preview}")
    if decision["target"] == "cloud" and decision["findings"]:
        print("\npayload after redaction:")
        print("  " + redact(text, decision["findings"])[:400].replace("\n", "\n  "))
    return 0


def cmd_probe(args) -> int:
    keys = cloud_keys_present()
    print(f"cloud providers with a usable key: {len(keys)}")
    for name, source in sorted(keys.items()):
        print(f"  YES  {name:<26} ({source})")
    if not keys:
        print("  no cloud credentials found in env or vault")
    up = local_model_up()
    print(f"\nlocal model endpoint {LOCAL_ENDPOINT}: {'UP' if up else 'DOWN'}")
    print(f"  (start one with: llama-server -m <model.gguf> --port 11434)")
    if not any(keys.values()) and not up:
        print("\nairlock: WARNING — no cloud keys and no local model. Inference is unavailable.")
        return 2
    return 0


def cmd_scan(args) -> int:
    """Which of YOUR files must never leave. Uses the ariadne index if present."""
    candidates: list[str] = []
    if args.index:
        if not ARIADNE_DB.exists():
            print("airlock: no ariadne index. Run: ariadne index", file=sys.stderr)
            return 2
        con = sqlite3.connect(f"file:{ARIADNE_DB}?mode=ro", uri=True)
        q = ("SELECT path,size FROM files WHERE zone='canon' AND size < 2000000 "
             "AND ext IN ('.py','.md','.json','.txt','.sh','.env','.yaml','.yml','.toml','.ini','.cfg','.jsonl')")
        for path, _size in con.execute(q):
            candidates.append(path)
        con.close()
        candidates.sort()
    else:
        candidates = args.paths
    if args.limit:
        candidates = candidates[:args.limit]

    hits: list[tuple[str, int, str, list[str]]] = []
    scanned = 0
    for rel in candidates:
        full = Path(rel) if os.path.isabs(rel) else HOME / rel
        try:
            if full.stat().st_size > 2_000_000:
                continue
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        if scanned % 2000 == 0:
            print(f"  ... {scanned:,}/{len(candidates):,} scanned, {len(hits)} hit(s)",
                  file=sys.stderr, flush=True)
        findings = scan(text, args.min_tier)
        if not findings:
            continue
        tier = highest_tier(findings)
        rules = sorted({f.rule for f in findings})
        hits.append((rel, len(findings), tier, rules))
        if args.verbose:
            print(f"  HIT [{tier}] {rel} ({', '.join(rules[:3])})", file=sys.stderr, flush=True)

    hits.sort(key=lambda h: (TIER_RANK[h[2]], -h[1]))
    print(f"scanned {scanned:,} candidate file(s); "
          f"{len(hits):,} contain sensitive material\n")
    print(f"{'tier':<10}{'hits':>6}  file  →  rules")
    print("-" * 100)
    for rel, count, tier, rules in hits[:args.limit_hits]:
        rule_str = ", ".join(rules[:4]) + (f" +{len(rules)-4}" if len(rules) > 4 else "")
        print(f"{tier:<10}{count:>6}  {rel}")
        print(f"{'':<18}→ {rule_str}")
    if len(hits) > args.limit_hits:
        print(f"\n... +{len(hits)-args.limit_hits} more files")
    print(f"\nThese are the files that must never leave this machine unredacted.")
    return 1 if hits else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="airlock",
        description="Redaction boundary: nothing leaves unsanitized. Read-only.")
    p.add_argument("--version", action="version", version=f"airlock {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("rules", help="list detection rules by tier")
    r.set_defaults(func=cmd_rules)

    c = sub.add_parser("check", help="exit 1 if sensitive material is present")
    c.add_argument("target", help="file path or - for stdin")
    c.add_argument("--min-tier", choices=TIERS, default="personal")
    c.set_defaults(func=cmd_check)

    rd = sub.add_parser("redact", help="print sanitized text")
    rd.add_argument("target", help="file path or - for stdin")
    rd.add_argument("--min-tier", choices=TIERS, default="personal")
    rd.add_argument("--stats", action="store_true", help="report count on stderr")
    rd.set_defaults(func=cmd_redact)

    ro = sub.add_parser("route", help="print the cloud/local routing decision")
    ro.add_argument("target", help="file path or - for stdin")
    ro.add_argument("--mode", choices=["strict", "redact", "off"], default="redact")
    ro.add_argument("--min-tier", choices=TIERS, default="personal")
    ro.set_defaults(func=cmd_route)

    pr = sub.add_parser("probe", help="is cloud reachable? is a local model up?")
    pr.set_defaults(func=cmd_probe)

    sc = sub.add_parser("scan", help="which of YOUR files must never leave")
    sc.add_argument("paths", nargs="*", help="files to scan when not using --index")
    sc.add_argument("--index", action="store_true", help="use the ariadne index for candidates")
    sc.add_argument("--min-tier", choices=TIERS, default="high")
    sc.add_argument("--limit", type=int, help="cap candidate files")
    sc.add_argument("--limit-hits", type=int, default=40)
    sc.add_argument("--verbose", action="store_true", help="print hits as they are found")
    sc.set_defaults(func=cmd_scan)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
