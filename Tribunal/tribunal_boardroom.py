#!/usr/bin/env python3

# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: tribunal
# DEPS: argparse,datetime,json,os,re,router,sys,time
# ROLE: TRIBUNAL CODE BOARDROOM — v4 of the Official Vertical AI Boardroom.
# AUTHOR: Bleak
# SESSION: 2026-09-11
# TIER: 3
# [/DNA_TAG]

"""
TRIBUNAL CODE BOARDROOM — v4 of the Official Vertical AI Boardroom.
Same engine. New seats. Purpose: adversarial review of AI agent transcripts
and code claims. Did it actually verify? Did it hallucinate? Does the diff
match the claim?

Seats:
  AUDITOR    — Security, tech debt, code smell. Did it break anything?
  WARLOCK    — Adversarial tester. Tries to break it. Edge cases, injection, race conditions.
  SENTINEL   — Reliability. Production readiness. Will it survive Monday morning?
  SCRIBE     — Documentation vs reality. Do the claims match the receipts?
  DEVIL      — Counter-argument. Challenges the strongest assumption.
  CHAIRMAN   — Buffy. Synthesizes. Decides.

Usage:
    python3 tribunal_boardroom.py "Review this agent transcript"
    python3 tribunal_boardroom.py --log ~/Tribunal/logs/session.log
    python3 tribunal_boardroom.py --diff /path/to/changes.diff
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

# ── Router integration ──────────────────────────────────────────────
# Import the existing model router from the boardroom project.
# Falls back to a local stub if the boardroom isn't installed.
_BOARDROOM_DIR = os.path.expanduser("~/The-Werkz/Official-Vertical-AI-Boardroom")
if _BOARDROOM_DIR not in sys.path:
    sys.path.insert(0, _BOARDROOM_DIR)

try:
    from router import ModelTier, call_model, strip_think
except ImportError:
    # Local fallback — minimal router for standalone use
    print("[tribunal] WARNING: boardroom router not found, using local stub")
    strip_think = lambda t: t

    class ModelTier:
        BOARDROOM = "boardroom"
        FAST = "fast"
        CODE = "code"
        CHAIRMAN = "chairman"

    def call_model(prompt, system=None, tier=None, chairman=False):
        raise RuntimeError("Router not available. Set PYTHONPATH to boardroom dir.")

# ── Validation Schema ───────────────────────────────────────────────

class BoardroomInput(BaseModel):
    transcript: str = Field(..., min_length=10)
    diff: str | None = None
    context: str | None = None

# ── Health Check ────────────────────────────────────────────────────

def perform_health_check():
    """Verify router availability."""
    try:
        from router import ModelTier
        return True
    except ImportError:
        return False

# ── Retry Logic ─────────────────────────────────────────────────────

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def call_model_with_retry(prompt, system=None, tier=None, chairman=False):
    return call_model(prompt, system=system, tier=tier, chairman=chairman)

# ── Seat definitions ────────────────────────────────────────────────

SEATS = {
    "AUDITOR": {
        "persona": """You are the Auditor. You've seen codebases die from "it works on my machine."
You don't care if the tests pass — you care if the tests are testing the right thing.
You look at error handling and see Swiss cheese. You look at dependencies and see ticking clocks.
You don't warn about vulnerabilities in the abstract — you name the specific line, the specific input,
the specific crash. You've been burned by "fully tested" code that had zero tests for the edge case
that brought down production at 3 AM on a Saturday. You speak in specifics. Vague warnings are noise.""",
        "focus": "the specific security holes, tech debt, and code smell that the agent missed or ignored",
        "prompt_template": """You are reviewing a transcript from an AI coding agent.
Your job: find what the agent missed, broke, or left insecure.

TRANSCRIPT:
{transcript}

{extra}

AUDIT THIS:
- What specific vulnerabilities or code smells exist?
- What error handling is missing?
- What dependencies are unsafe or outdated?
- What would a security reviewer flag on the first pass?
- Be specific. Name lines, functions, inputs. No vague warnings.""",
    },

    "WARLOCK": {
        "persona": """You are the Warlock. You don't test code — you torture it.
You find the input that makes it scream. You find the race condition that nobody thought about.
You find the edge case that only happens on the third Tuesday of the month when the timezone
is wrong and the user's name contains a semicolon. You think in attack surfaces:
- What happens with empty input?
- What happens with 10GB of input?
- What happens when two requests arrive at the same time?
- What happens when the network drops mid-request?
- What happens when the database is slow?
You don't ask "is it secure?" — you show the exploit. You speak in payloads, not theories.""",
        "focus": "the attack vectors, edge cases, and failure modes the agent never considered",
        "prompt_template": """You are adversarial-testing a transcript from an AI coding agent.
Your job: find the inputs and scenarios that break it.

TRANSCRIPT:
{transcript}

{extra}

ATTACK THIS:
- What inputs crash it? (empty, huge, malformed, unicode, injection)
- What race conditions exist? (concurrent writes, shared state, locks)
- What happens when upstream services fail? (timeouts, partial responses)
- What happens under load? (memory, disk, connections)
- Give specific payloads or scenarios, not general warnings. Show the exploit.""",
    },

    "SENTINEL": {
        "persona": """You are the Sentinel. You care about one thing: will this survive Monday morning?
You've seen "done" code that couldn't handle a single concurrent user.
You've seen "production ready" deployments with no health checks, no logging, no rollback plan.
You think in failure domains:
- What happens when this is the only thing running and it dies?
- Can someone else debug this at 3 AM without the original author?
- Is there a way to know something is wrong BEFORE the user reports it?
- Can this be rolled back without data loss?
- Does this actually handle the real-world load, or just the happy path?
You don't care about elegance. You care about resilience. You speak in SLAs, not aspirations.""",
        "focus": "whether this will actually survive production, and what kills it first",
        "prompt_template": """You are evaluating production readiness from an AI agent's transcript.
Your job: find what will break in the real world.

TRANSCRIPT:
{transcript}

{extra}

PRODUCTION CHECK:
- Does it have health checks, logging, error recovery?
- Can it handle concurrent users / requests?
- What happens when it crashes? Can it recover?
- What monitoring or alerting exists?
- What's the first thing that breaks under real load?
- Rate it: P0 (blocks deploy), P1 (blocks next week), P2 (tech debt), P3 (polish)""",
    },

    "SCRIBE": {
        "persona": """You are the Scribe. You catch the gap between what was said and what was done.
You've read too many "all tests pass" claims from agents that never ran the tests.
You've seen "fully verified" logs that contained zero verification commands.
You compare the agent's claims against its actual output:
- Did it say "done" before the build finished?
- Did it say "verified" without running verification?
- Did it say "tests pass" without showing test output?
- Did it say "deployed" without a deployment receipt?
- Did it say "fixed" without showing the before/after?
You are the receipt checker. Every claim gets a verdict: CLAIMED vs RECEIPTED. No middle ground.""",
        "focus": "the gap between what the agent claims and what it actually proved",
        "prompt_template": """You are fact-checking an AI coding agent's transcript.
Your job: match every claim to a receipt.

TRANSCRIPT:
{transcript}

{extra}

AUDIT THE CLAIMS:
Go line by line through the transcript. For every claim the agent makes
("done", "verified", "tests pass", "fixed", "deployed", "secure", etc.):
1. What was the claim?
2. Is there a receipt? (actual command output, diff, test log, deployment confirmation)
3. Verdict: RECEIPTED (proof shown) or CLAIMED (no proof)

Output a table. No prose. Claim | Receipt | Verdict.
Then: how many claims were unverified? What percentage?""",
    },

    "DEVIL": {
        "persona": """You are the Devil's Advocate. You don't play this role for fun — you actually believe
the opposite. You find the strongest thing the agent said and you dismantle it, not to be a
contrarian, but because untested consensus is how production incidents happen.
You find it suspicious when the agent is confident. Confidence without receipts is a red flag.
You will sometimes agree with the room if the agent genuinely did good work. But they rarely did.
You speak with the confidence of someone who's seen the post-mortem and knows the root cause
was the thing everyone agreed was fine.""",
        "focus": "the strongest assumption everyone is accepting, and why it's wrong",
        "prompt_template": """You are challenging the consensus on an AI coding agent's work.
Your job: find the strongest claim and prove it's weaker than it looks.

TRANSCRIPT:
{transcript}

{extra}

CHALLENGE:
- What's the single strongest claim the agent made?
- Why is it weaker than it appears?
- What would change your mind? (What evidence would make you say "actually, they did it right"?)
- What's the one thing in this transcript that, if it's wrong, makes everything else collapse?
- Be honest. If the work is genuinely good, say so. But make them earn it.""",
    },
}

# ── Chairman (Buffy) ───────────────────────────────────────────────

CHAIRMAN_PERSONA = """You are Buffy, the Chairman of the Tribunal Code Boardroom.
You are a coding agent — an operator, not a consultant. You've shipped more
code than everyone at this table combined. You got here by being direct, by
refusing to hedge, and by never letting a bad idea walk out of the room untested.

Your voice: direct, no hedging, profanity allowed when it earns its place,
no corporate language, no consultant-speak, no restating the obvious. You
speak to the operator like a technical peer sitting next to you, not a client
across the desk. When the board is right, you say so plainly. When they're
wrong, you name it. When the evidence doesn't support a verdict, you say
what would change your mind.

You are not a committee. You have heard the arguments. You decide."""

CHAIRMAN_SYSTEM = (
    f"{CHAIRMAN_PERSONA}\n\n"
    "Format your closing exactly like this:\n"
    "VERDICT: ship-it | fix-first | reject | honest-work\n"
    "SEVERITY: P0 | P1 | P2 | P3\n"
    "CRITICAL: <the single thing that must be fixed before anything else>\n"
    "RISK: <the single biggest risk if this ships as-is>\n"
    "SAVING: <the single best thing the agent did, if anything>\n"
    "SAYING: <one line a chairman would actually say>\n"
    "\n"
    "Then write 2-3 short paragraphs of plain speech explaining the call. "
    "No bullet points. No restating the board's words. Sound like someone "
    "who has made hard calls before and will make them again."
)

_VERDICT_RE = re.compile(r"^\s*VERDICT:\s*(ship-it|fix-first|reject|honest-work)\s*$", re.I | re.M)
_SEVERITY_RE = re.compile(r"^\s*SEVERITY:\s*(P[0-3])\s*$", re.I | re.M)
_FIELD_RE = re.compile(r"^\s*(CRITICAL|RISK|SAVING|SAYING):\s*(.+)$", re.I | re.M)


def parse_chairman_verdict(text):
    """Parse the chairman's closing into structured fields."""
    clean = (text or "").strip()
    verdict = "unknown"
    severity = "P2"
    m = _VERDICT_RE.search(clean)
    if m:
        verdict = m.group(1).lower()
    sm = _SEVERITY_RE.search(clean)
    if sm:
        severity = sm.group(1).upper()

    fields = {}
    for fm in _FIELD_RE.finditer(clean):
        fields[fm.group(1).lower()] = fm.group(2).strip()

    prose = _VERDICT_RE.sub("", clean)
    prose = _SEVERITY_RE.sub("", prose)
    prose = _FIELD_RE.sub("", prose).strip()

    return {
        "verdict": verdict,
        "severity": severity,
        "critical": fields.get("critical", ""),
        "risk": fields.get("risk", ""),
        "saving": fields.get("saving", ""),
        "saying": fields.get("saying", ""),
        "statement": prose,
        "chairman": "buffy",
    }


# ── Core engine ─────────────────────────────────────────────────────

def convene(transcript, diff=None, context=None):
    # P0 FIX: Health check and Validation
    if not perform_health_check():
        raise RuntimeError("Boardroom health check failed: Router inaccessible.")
    
    try:
        validated_input = BoardroomInput(transcript=transcript, diff=diff, context=context)
        transcript = validated_input.transcript
    except ValidationError as e:
        raise ValueError(f"Input validation failed: {e}")

    """
    Run the full Tribunal boardroom on a transcript.

    Args:
        transcript: The agent's raw output / log content
        diff: Optional diff or code changes to review
        context: Optional extra context (what was asked, what should have happened)

    Returns:
        dict with seats (per-seat output), chairman verdict, metadata
    """
    session_id = f"tribunal_{int(time.time())}"
    started = datetime.now(timezone.utc).isoformat()

    # Build the base context
    extra_parts = []
    if diff:
        extra_parts.append(f"DIFF / CHANGES:\n{diff}")
    if context:
        extra_parts.append(f"CONTEXT / EXPECTATIONS:\n{context}")
    extra = "\n\n".join(extra_parts) if extra_parts else "No additional context provided."

    # Truncate transcript if huge (models have context limits)
    if len(transcript) > 15000:
        transcript = transcript[:15000] + "\n... [truncated at 15k chars]"

    results = {}
    debate = []

    print(f"\n{'='*60}")
    print(f"  TRIBUNAL CODE BOARDROOM — Session {session_id}")
    print(f"  Transcript: {len(transcript)} chars | Started: {started}")
    print(f"{'='*60}\n")

    # ── Each seat speaks ──
    for seat_name, seat in SEATS.items():
        print(f"  [{seat_name}] Deliberating...")
        t0 = time.time()

        prompt = seat["prompt_template"].format(
            transcript=transcript, extra=extra
        )

        try:
            response, provider = call_model_with_retry(
                prompt,
                system=seat["persona"],
                tier=ModelTier.BOARDROOM,
            )
            response = strip_think(response) if response else ""
            elapsed = time.time() - t0
            print(f"  [{seat_name}] Done ({elapsed:.1f}s via {provider})")
        except Exception as e:
            response = f"[SEAT UNAVAILABLE: {e}]"
            provider = "error"
            elapsed = time.time() - t0
            print(f"  [{seat_name}] FAILED ({elapsed:.1f}s): {e}")

        results[seat_name] = {
            "persona": seat_name,
            "focus": seat["focus"],
            "response": response,
            "provider": provider,
            "elapsed": round(elapsed, 1),
        }
        debate.append(f"--- {seat_name} ({seat['focus']}) ---\n{response}")

    # ── Chairman synthesizes ──
    print(f"\n  [CHAIRMAN] Deliberating on {len(SEATS)} seats...")
    t0 = time.time()

    debate_text = "\n\n".join(debate)
    chairman_prompt = (
        f"The Tribunal board has delivered the following verdicts on an AI agent's work:\n\n"
        f"{debate_text}\n\n"
        f"Original transcript for reference:\n{transcript[:3000]}\n\n"
        f"Synthesize. Decide. Be specific. Be direct."
    )

    try:
        chairman_response, provider = call_model_with_retry(
            chairman_prompt,
            system=CHAIRMAN_SYSTEM,
            chairman=True,
        )
        chairman_response = strip_think(chairman_response) if chairman_response else ""
        elapsed = time.time() - t0
        print(f"  [CHAIRMAN] Done ({elapsed:.1f}s via {provider})")
    except Exception as e:
        chairman_response = f"[CHAIRMAN UNAVAILABLE: {e}]"
        provider = "error"
        elapsed = time.time() - t0
        print(f"  [CHAIRMAN] FAILED ({elapsed:.1f}s): {e}")

    verdict = parse_chairman_verdict(chairman_response)

    results["CHAIRMAN"] = {
        "persona": "CHAIRMAN",
        "focus": "synthesis and final verdict",
        "response": chairman_response,
        "parsed": verdict,
        "provider": provider,
        "elapsed": round(elapsed, 1),
    }

    # ── Output ──
    finished = datetime.now(timezone.utc).isoformat()

    print(f"\n{'='*60}")
    print(f"  VERDICT: {verdict['verdict'].upper()} ({verdict['severity']})")
    if verdict.get("critical"):
        print(f"  CRITICAL: {verdict['critical']}")
    if verdict.get("saying"):
        print(f"  SAYING: \"{verdict['saying']}\"")
    print(f"{'='*60}\n")

    # ── Save session ──
    session = {
        "session_id": session_id,
        "started": started,
        "finished": finished,
        "transcript_length": len(transcript),
        "seats": results,
        "verdict": verdict,
    }

    logdir = os.path.expanduser("~/Tribunal/logs")
    os.makedirs(logdir, exist_ok=True)
    logfile = os.path.join(logdir, f"tribunal_{session_id}.json")
    with open(logfile, "w") as f:
        json.dump(session, f, indent=2)
    print(f"  Session saved: {logfile}")

    return session


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Tribunal Code Boardroom — adversarial review of AI agent transcripts"
    )
    parser.add_argument("transcript_text", nargs="?", help="Raw transcript text to review")
    parser.add_argument("--log", help="Path to a log file to review")
    parser.add_argument("--diff", help="Path to a diff file to include")
    parser.add_argument("--context", help="Extra context (what was asked, expected outcome)")
    parser.add_argument("--json", action="store_true", help="Output full session as JSON")
    parser.add_argument("--health", action="store_true", help="Run health check and exit")

    args = parser.parse_args()

    if args.health:
        if perform_health_check():
            print("Boardroom healthy.")
            sys.exit(0)
        else:
            print("Boardroom unhealthy.")
            sys.exit(1)

    # Load transcript
    transcript = ""
    if args.log:
        with open(args.log, "r") as f:
            transcript = f.read()
    elif args.transcript_text:
        transcript = args.transcript_text
    elif not sys.stdin.isatty():
        transcript = sys.stdin.read()
    else:
        parser.print_help()
        print("\nExamples:")
        print('  python3 tribunal_boardroom.py "the agent said all tests pass"')
        print("  python3 tribunal_boardroom.py --log ~/Tribunal/logs/session.log")
        print('  cat transcript.log | python3 tribunal_boardroom.py --json')
        sys.exit(1)

    if not transcript.strip():
        print("Error: empty transcript")
        sys.exit(1)

    # Load diff if provided
    diff = None
    if args.diff:
        with open(args.diff, "r") as f:
            diff = f.read()

    session = convene(transcript, diff=diff, context=args.context)

    if args.json:
        print(json.dumps(session, indent=2))


if __name__ == "__main__":
    main()
