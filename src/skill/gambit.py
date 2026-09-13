"""
MOLT Gambit — Instar Ladder
Human ↔ Doc tandem progression so neither outruns the other.

The metaphor: an insect doesn't molt on schedule — it molts when it's ready.
Each INSTAr is a developmental stage. The doc's OOMF only deepens when the human
demonstrates comprehension + retention. Proficient users fast-track; novices are
scaffolded.

Instars:
  1  Hatchling — vocab & mental model (can name the Triad parts)
  2  Crawler   — guided execution (run a demo with hints)
  3  Forager   — solo execution (ship a variant unaided)
  4  Weaver    — adapt & morph (handle edge cases, swap domains)
  5  Molt      — author living skills for others (teach)

Incentive: you don't just *read* the doc — you molt WITH it. Each instar unlocks:
  - deeper OOMF hydration (richer RAG, live crawl)
  - new runbook sections revealed
  - privilege suggestions (--elevate) become available
  - visible progress (badges, streak, XP) in rag_storage/instars/

Fast-track: if you ace calibration quickly, you skip straight to 3/4. No grind.

Storage: rag_storage/instars/<user>__<skill>.json  (portable, offline, no DB)
Zero-bloat: if no InstarEngine is passed to SkillManager, everything is vanilla.
"""

import re
import json
import time
import hashlib
import random
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple

try:
    import yaml  # noqa: F401
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

INSTARS = {
    1: {"name": "Hatchling", "label": "I can name it",      "oomf_cap": 1, "xp_to_next": 30,
        "unlocks": ["vocab quiz", "Triad map"]},
    2: {"name": "Crawler",   "label": "I can run it",       "oomf_cap": 2, "xp_to_next": 40,
        "unlocks": ["guided demo", "copy-paste runbook"]},
    3: {"name": "Forager",   "label": "I can ship it",      "oomf_cap": 3, "xp_to_next": 50,
        "unlocks": ["solo task", "RAG bake"]},
    4: {"name": "Weaver",    "label": "I can bend it",      "oomf_cap": 4, "xp_to_next": 60,
        "unlocks": ["edge cases", "domain morph", "--elevate write"]},
    5: {"name": "Molt",      "label": "I can teach it",     "oomf_cap": 5, "xp_to_next": 0,
        "unlocks": ["author new skill", "--elevate exec", "spawn swarm"]},
}

DEFAULT_STORE = Path("rag_storage/instars")
# Challenge bank — lightweight, no LLM needed for MVP. Swap for model-generated later.
CHALLENGE_BANK: Dict[str, List[Dict[str, Any]]] = {
    # fallback generic if skill not listed
    "_generic": [
        {"instar": 1, "type": "recall", "q": "Name the three Triad parts and one sentence for each.", "a_keywords": ["scout", "oracle", "governor"], "points": 10},
        {"instar": 1, "type": "recall", "q": "OOMF 1 vs OOMF 5 — what's the difference?", "a_keywords": ["inert", "crawl"], "points": 10},
        {"instar": 2, "type": "apply",  "q": "Hydrate a skill at oomf 2 without calling the API (dry_run). What flag?", "a_keywords": ["dry_run", "hydrate"], "points": 15},
        {"instar": 2, "type": "apply",  "q": "You got 'Governor: network required'. What flag fixes it?", "a_keywords": ["--elevate", "network"], "points": 15},
        {"instar": 3, "type": "apply",  "q": "Your Scout fetched 0 docs at depth 3 — name two likely causes.", "a_keywords": ["target_domains", "governor", "network"], "points": 20},
        {"instar": 3, "type": "debug",  "q": "Oracle blocked with 'privilege_drift exec' — what happened?", "a_keywords": ["scout", "exec", "user"], "points": 20},
        {"instar": 4, "type": "design", "q": "Morph a triage skill into a sports_broadcast runtime — what preset + what changes?", "a_keywords": ["sports_broadcast", "morph", "scout"], "points": 25},
        {"instar": 5, "type": "design", "q": "Design a new Living skill from scratch: name, depth, oracle mode, and one target_domain.", "a_keywords": ["scout", "oracle", "depth"], "points": 30},
    ]
}

def _now() -> float:
    return time.time()

def _stable_id(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:10]


@dataclass
class InstarState:
    user_id: str
    skill: str
    instar: int = 1
    xp: int = 0
    streak: int = 0  # consecutive passes
    best_ms: Optional[float] = None
    last_challenge_at: Optional[float] = None
    next_due_at: Optional[float] = None  # spaced repetition
    history: List[Dict[str, Any]] = field(default_factory=list)
    calibrated: bool = False
    unlocked_at: Dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InstarState":
        # tolerate missing keys from old saves
        return cls(
            user_id=d.get("user_id", "anon"),
            skill=d.get("skill", "?"),
            instar=int(d.get("instar", 1)),
            xp=int(d.get("xp", 0)),
            streak=int(d.get("streak", 0)),
            best_ms=d.get("best_ms"),
            last_challenge_at=d.get("last_challenge_at"),
            next_due_at=d.get("next_due_at"),
            history=d.get("history", []),
            calibrated=bool(d.get("calibrated", False)),
            unlocked_at={int(k): float(v) for k, v in d.get("unlocked_at", {}).items()},
        )

    def tier(self) -> Dict[str, Any]:
        return INSTARS.get(self.instar, INSTARS[1])


class InstarEngine:
    """
    Human ↔ Doc tandem driver.

    One engine per human (user_id). Tracks multiple skills independently.
    Persisted to rag_storage/instars/ — survives reboot, works offline.

    Fast-track: calibrate() can place you at 3/4 immediately if you demonstrate
    high comprehension. No forced grind.

    Example:
        g = InstarEngine(user_id="bubba")
        g.calibrate("med-triage-copilot")          # 60s placement quiz
        g.challenge("med-triage-copilot")          # get next task at your instar
        g.submit("med-triage-copilot", answers)    # -> {passed, new_instar, next_oomf}
        g.auto_oomf("med-triage-copilot")          # doc hydrates at your instar cap
    """

    def __init__(self, user_id: str = "anon", store_dir: str = "rag_storage/instars"):
        self.user_id = user_id or "anon"
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, InstarState] = {}

    # ── persistence ──────────────────────────────────────────────
    def _path(self, skill: str) -> Path:
        safe_user = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.user_id)[:24]
        safe_skill = "".join(c if c.isalnum() or c in "-_" else "_" for c in skill)[:40]
        return self.store_dir / f"{safe_user}__{safe_skill}.json"

    def _load(self, skill: str) -> InstarState:
        if skill in self._cache:
            return self._cache[skill]
        p = self._path(skill)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                st = InstarState.from_dict(data)
                self._cache[skill] = st
                return st
            except Exception:
                pass
        st = InstarState(user_id=self.user_id, skill=skill, instar=1, unlocked_at={1: _now()})
        self._cache[skill] = st
        self._save(st)
        return st

    def _save(self, st: InstarState) -> None:
        p = self._path(st.skill)
        p.parent.mkdir(parents=True, exist_ok=True)
        # atomic-ish
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(st.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(p)
        self._cache[st.skill] = st

    # ── calibration (placement) ──────────────────────────────────
    def calibrate(self, skill: str) -> Dict[str, Any]:
        """
        Quick placement quiz — 5 questions spanning instar 1→3.
        Score + speed determines starting instar. Idempotent: re-calibrate anytime.
        Returns {instar, score, max_score, elapsed_ms, quiz}
        """
        st = self._load(skill)
        bank = CHALLENGE_BANK.get(skill, CHALLENGE_BANK["_generic"])
        quiz = [q for q in bank if q["instar"] <= 3][:5]
        # caller will present quiz and call calibrate_submit; this just returns quiz
        # For headless/test use: auto-score via a_keywords not applicable — provide quiz to UI
        return {
            "skill": skill,
            "instar_before": st.instar,
            "quiz": quiz,
            "hint": "Answer in your own words — keywords matter more than exact phrasing. Speed counts."
        }

    def calibrate_submit(self, skill: str, answers: List[str], elapsed_ms: float) -> Dict[str, Any]:
        """
        Score calibration answers. Fast + accurate => jump instars.
        Thresholds:
          0-30%  -> instar 1
          30-60% -> instar 2
          60-85% -> instar 3
          85-100% in <45s -> instar 4 (weaver fast-track)
          100% in <30s -> instar 4 with bonus XP
        """
        st = self._load(skill)
        bank = CHALLENGE_BANK.get(skill, CHALLENGE_BANK["_generic"])
        quiz = [q for q in bank if q["instar"] <= 3][:5]
        max_score = sum(q["points"] for q in quiz)
        score = 0
        per_q = []
        for q, ans in zip(quiz, answers):
            ans_l = (ans or "").lower()
            hits = sum(1 for kw in q["a_keywords"] if kw.lower() in ans_l)
            # partial credit: need >=50% keywords
            ratio = hits / max(1, len(q["a_keywords"]))
            got = int(q["points"] * (1 if ratio >= 0.5 else ratio))
            # bonus: exact keyword combo
            if ratio >= 1.0:
                got = q["points"]
            score += got
            per_q.append({"q": q["q"][:60], "hits": hits, "need": len(q["a_keywords"]), "points": got})

        pct = score / max(1, max_score)
        new_instar = 1
        if pct >= 0.85 and elapsed_ms < 45000:
            new_instar = 4
        elif pct >= 0.6:
            new_instar = 3
        elif pct >= 0.3:
            new_instar = 2

        # Don't demote if already higher
        if new_instar > st.instar:
            st.instar = new_instar
            st.unlocked_at[new_instar] = _now()
        st.calibrated = True
        # XP bonus for fast perfect
        bonus = 20 if pct >= 1.0 and elapsed_ms < 30000 else (10 if pct >= 0.85 else 0)
        st.xp += score + bonus
        st.best_ms = min(st.best_ms, elapsed_ms) if st.best_ms else elapsed_ms
        st.history.append({"type": "calibrate", "score": score, "max": max_score, "pct": round(pct, 2), "elapsed_ms": elapsed_ms, "per_q": per_q, "ts": _now()})
        st.last_challenge_at = _now()
        st.next_due_at = _now() + 24 * 3600  # revisit tomorrow
        self._save(st)
        return {
            "skill": skill,
            "score": score,
            "max_score": max_score,
            "pct": round(pct, 2),
            "elapsed_ms": elapsed_ms,
            "instar": st.instar,
            "instar_name": INSTARS[st.instar]["name"],
            "bonus_xp": bonus,
            "auto_oomf": self.auto_oomf(skill),
            "per_q": per_q,
        }

    # ── challenge → submit loop ──────────────────────────────────
    def challenge(self, skill: str) -> Dict[str, Any]:
        """
        Get next challenge at current instar. Includes hint scaffold scaled to instar.
        Lower instars get more hints; instar 5 gets open-ended prompts.
        """
        st = self._load(skill)
        bank = CHALLENGE_BANK.get(skill, CHALLENGE_BANK["_generic"])
        pool = [q for q in bank if q["instar"] == st.instar] or [q for q in bank if q["instar"] <= st.instar]
        q = random.choice(pool)
        scaffold = {
            1: "Hint: answer can be one sentence. Keywords in your response are auto-scored.",
            2: "Hint: try the command; paste output if stuck.",
            3: "Hint: check rag_storage/sidecars/<skill>.jsonl and SKILL.md frontmatter.",
            4: "Hint: you're expected to handle an edge case or swap a domain preset.",
            5: "Hint: no hints — design it, teach it, ship it.",
        }.get(st.instar, "")
        return {
            "skill": skill,
            "instar": st.instar,
            "instar_name": INSTARS[st.instar]["name"],
            "oomf_cap": INSTARS[st.instar]["oomf_cap"],
            "challenge": q,
            "scaffold": scaffold,
            "xp_to_next": INSTARS[st.instar]["xp_to_next"],
            "xp": st.xp,
            "streak": st.streak,
        }

    def submit(self, skill: str, answer: str, elapsed_ms: Optional[float] = None) -> Dict[str, Any]:
        """
        Score a challenge answer. Simple keyword heuristic for MVP — swap for LLM judge later.
        Fast + accurate promotes. Slow or partial keeps you practicing at same instar.
        """
        st = self._load(skill)
        # We need to know which challenge was issued — recover from last history or guess via keywords
        # For MVP: score against all questions at current instar, take best match
        bank = CHALLENGE_BANK.get(skill, CHALLENGE_BANK["_generic"])
        pool = [q for q in bank if q["instar"] == st.instar] or bank
        ans_l = (answer or "").lower()
        best = None
        best_ratio = 0
        best_q = pool[0]
        for q in pool:
            hits = sum(1 for kw in q["a_keywords"] if kw.lower() in ans_l)
            ratio = hits / max(1, len(q["a_keywords"]))
            if ratio > best_ratio:
                best_ratio = ratio
                best_q = q
                best = hits
        # score
        points = int(best_q["points"] * (best_ratio if best_ratio < 1 else 1))
        passed = best_ratio >= 0.5
        # speed bonus
        if elapsed_ms is not None and elapsed_ms < 15000 and best_ratio >= 1.0:
            points += 5

        prev_instar = st.instar
        leveled = False
        if passed:
            st.xp += points
            st.streak += 1
            # spaced retention push
            st.last_challenge_at = _now()
            st.next_due_at = _now() + (48 * 3600 if st.streak >= 3 else 24 * 3600)
            # level up check: need XP threshold + streak
            need = INSTARS[st.instar]["xp_to_next"]
            if need > 0 and st.xp >= need and st.streak >= 2:
                if st.instar < 5:
                    st.instar += 1
                    st.unlocked_at[st.instar] = _now()
                    st.xp = 0  # reset for next tier (keep overflow small)
                    leveled = True
            # fast-track: perfect streak of 3 at instar 2-3 jumps an extra
            if st.streak >= 3 and best_ratio >= 1.0 and st.instar < 5 and leveled is False:
                # check if eligible for double molt
                if elapsed_ms is not None and elapsed_ms < 20000:
                    st.instar = min(5, st.instar + 1)
                    st.unlocked_at[st.instar] = _now()
                    leveled = True
        else:
            st.streak = 0
            st.xp = max(0, st.xp - 2)  # tiny decay, not punishing

        st.best_ms = min(st.best_ms, elapsed_ms) if (st.best_ms and elapsed_ms) else (elapsed_ms or st.best_ms)
        st.history.append({
            "type": "challenge",
            "instar": prev_instar,
            "q": best_q["q"][:80],
            "ratio": round(best_ratio, 2),
            "points": points,
            "passed": passed,
            "elapsed_ms": elapsed_ms,
            "ts": _now(),
        })
        self._save(st)
        return {
            "skill": skill,
            "passed": passed,
            "points": points,
            "ratio": round(best_ratio, 2),
            "prev_instar": prev_instar,
            "new_instar": st.instar,
            "leveled": leveled,
            "instar_name": INSTARS[st.instar]["name"],
            "auto_oomf": self.auto_oomf(skill),
            "next_challenge_due": st.next_due_at,
            "streak": st.streak,
            "xp": st.xp,
        }

    # ── progress & gating ────────────────────────────────────────
    def progress(self, skill: str) -> Dict[str, Any]:
        st = self._load(skill)
        t = INSTARS[st.instar]
        return {
            "skill": skill,
            "user_id": self.user_id,
            "instar": st.instar,
            "instar_name": t["name"],
            "label": t["label"],
            "xp": st.xp,
            "xp_to_next": t["xp_to_next"],
            "oomf_cap": t["oomf_cap"],
            "auto_oomf": self.auto_oomf(skill),
            "unlocks": t["unlocks"],
            "streak": st.streak,
            "best_ms": st.best_ms,
            "calibrated": st.calibrated,
            "next_due_at": st.next_due_at,
            "history_len": len(st.history),
            "unlocked": sorted(st.unlocked_at.keys()),
        }

    def auto_oomf(self, skill: str) -> int:
        """Doc's recommended OOMF for this human at this skill — never exceeds instar cap."""
        st = self._load(skill)
        cap = INSTARS[st.instar]["oomf_cap"]
        # frontmatter depth is the doc's max; human cap is the min
        try:
            from .skill_manager import SkillManager
            front = SkillManager().parse_frontmatter(skill)
            doc_depth = int(front.get("scout", {}).get("depth", 3))
        except Exception:
            doc_depth = 5
        return min(cap, doc_depth)

    def reset(self, skill: str) -> None:
        p = self._path(skill)
        if p.exists():
            p.unlink()
        self._cache.pop(skill, None)

    def all_progress(self) -> List[Dict[str, Any]]:
        return [self.progress(skill) for skill in self._list_tracked_skills()]

    def _list_tracked_skills(self) -> List[str]:
        if not self.store_dir.exists():
            return []
        prefix = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.user_id)[:24] + "__"
        skills = []
        for p in self.store_dir.glob(f"{prefix}*.json"):
            # strip prefix and suffix
            name = p.stem[len(prefix):]
            # recover original skill name (underscores were sanitized — best effort)
            skills.append(name)
        return skills

    # ── hydration helper: instar-gated reveal ────────────────────
    def gate_hydration(self, skill: str, full_body: str) -> str:
        """
        Gate doc sections by instar. Hidden sections are wrapped in:
          <!-- instar:3 --> ... <!-- /instar -->
        Below your instar they are stripped and replaced with a teaser + challenge prompt.
        No gate if no marker found — backward compatible.
        """
        st = self._load(skill)
        instar = st.instar
        # Find gated blocks
        pattern = re.compile(r"<!--\s*instar:(\d+)\s*-->(.*?)<!--\s*/instar\s*-->", re.DOTALL | re.IGNORECASE)

        def repl(m):
            need = int(m.group(1))
            inner = m.group(2)
            if instar >= need:
                return inner
            # never echo gated content — generic banner only (prevents secret leak)
            return f"\n> \U0001f512 Instar {need} locked \u2014 complete a challenge to molt -> `molt challenge {skill}` (requires instar {need})\n"

        return pattern.sub(repl, full_body)

# Backwards compat alias
GambitEngine = InstarEngine
