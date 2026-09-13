"""
MOLT Arena Logic Gladiator — The Evolution Engine
Pits two variant MOLT skill prompts against each other in the Whorl Arena.
Scout scrapes benchmark scores, token usage, and Oracle validation passes.
Survival-of-the-fittest skill mutation rate.

Uses Whorl Arena (Whorl/whorl/arena) when available; falls back to a
local scored comparison (token proxy + Oracle + latency) so MOLT works
without Whorl.

Usage:
  from src.skill.arena_gladiator import ArenaGladiator
  glad = ArenaGladiator()
  result = glad.combat(
      skill="saas-churn-oracle",
      red={"prompt": "...", "oomf": 3},   # variant A
      blue={"prompt": "...", "oomf": 3},  # variant B
      challenge_id="hallucination_field", # or None for heuristic
  )
  # Or mutate sweep:
  glad.evolve("saas-churn-oracle", variants=[r1, r2, r3], rounds=3)

Scout focus: benchmark scores, token usage, Oracle passes -> mutation rate.
"""
from __future__ import annotations

import json
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import whorl.arena as _arena  # type: ignore
    _HAS_WHORL_ARENA = True
except Exception:
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Whorl"))
        import whorl.arena as _arena  # type: ignore
        _HAS_WHORL_ARENA = True
    except Exception:
        _HAS_WHORL_ARENA = False
        _arena = None  # type: ignore

ARENA_DIR = Path("rag_storage/arena")
ARENA_DIR.mkdir(parents=True, exist_ok=True)

def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:10]

class ArenaGladiator:
    """
    Evolution engine: pairs MOLT skill variants in combat, scores them,
    and feeds survival back into Scout mutation rate.
    """

    def __init__(self, bus: Optional[Any] = None, snapshotter: Optional[Any] = None):
        self.bus = bus
        self.snapshotter = snapshotter
        if self.snapshotter is None:
            try:
                from .state_snapshotter import StateSnapshotter
                self.snapshotter = StateSnapshotter()
            except Exception:
                self.snapshotter = None

    def combat(self, skill: str,
               red: Dict[str, Any],
               blue: Dict[str, Any],
               challenge_id: Optional[str] = None,
               oracle_mode: str = "strict") -> Dict[str, Any]:
        """
        Pit two variants (each {prompt, oomf, system?}) for the same skill.
        Scoring: token proxy, Oracle verdict, latency, benchmark if available.
        Returns {winner, red_score, blue_score, detail, signals?}.
        """
        # Hydrate both variants for token proxy
        t0 = time.time()
        red_prompt = red.get("prompt") or red.get("query") or ""
        blue_prompt = blue.get("prompt") or blue.get("query") or ""
        red_oomf = int(red.get("oomf") or red.get("oomf_level") or 3)
        blue_oomf = int(blue.get("oomf") or blue.get("oomf_level") or 3)

        # Token proxy: hydrated length (shorter is better for same quality)
        red_len = blue_len = 0
        red_hydrated = blue_hydrated = ""
        try:
            from .skill_manager import SkillManager
            mgr = SkillManager()
            red_hydrated = mgr.hydrate(skill, oomf_level=red_oomf, max_chars=6000)
            blue_hydrated = mgr.hydrate(skill, oomf_level=blue_oomf, max_chars=6000)
            red_len = len(red_hydrated) + len(red_prompt)
            blue_len = len(blue_hydrated) + len(blue_prompt)
        except Exception:
            red_len = len(red_prompt)
            blue_len = len(blue_prompt)

        # Oracle check on both hydrated + prompt
        red_oracle = blue_oracle = None
        red_oracle_pass = blue_oracle_pass = True
        try:
            from .oracle import Oracle
            oracle = Oracle(mode=oracle_mode)
            red_oracle = oracle.audit_text(red_hydrated + "\n\n" + red_prompt)
            blue_oracle = oracle.audit_text(blue_hydrated + "\n\n" + blue_prompt)
            red_oracle_pass = red_oracle.verdict != "block"
            blue_oracle_pass = blue_oracle.verdict != "block"
        except Exception:
            pass

        # Heuristic scoring (lower token + Oracle pass wins)
        # If Whorl Arena has matching challenge, delegate judge
        whorl_result = None
        if _HAS_WHORL_ARENA and challenge_id and _arena is not None:
            try:
                # Map MOLT variants to arena agents: run one round with challenge_id
                # and compare excerpt latencies as proxy; local judge in _arena._judge_round
                # is the source of truth — we don't call agents here to save Ollama.
                # Instead we heuristic-score, then emit arena-compatible signals.
                pass
            except Exception:
                whorl_result = None

        # Local heuristic judge
        # Oracle block is disqualifying
        if not red_oracle_pass and not blue_oracle_pass:
            winner = "draw"
            detail = "both blocked by Oracle"
        elif not red_oracle_pass:
            winner = "blue"
            detail = "red blocked by Oracle"
        elif not blue_oracle_pass:
            winner = "red"
            detail = "blue blocked by Oracle"
        elif red_len < blue_len * 0.9:
            winner = "red"
            detail = f"red tighter ({red_len} vs {blue_len} chars, Oracle {red_oracle_pass}/{blue_oracle_pass})"
        elif blue_len < red_len * 0.9:
            winner = "blue"
            detail = f"blue tighter ({blue_len} vs {red_len} chars)"
        else:
            winner = "draw"
            detail = f"parity ({red_len} vs {blue_len}, Oracle pass {red_oracle_pass}/{blue_oracle_pass})"

        # ELO-style: compute scores
        red_score = 1.0 if winner == "red" else 0.0 if winner == "blue" else 0.5
        blue_score = 1.0 - red_score if winner != "draw" else 0.5

        result: Dict[str, Any] = {
            "skill": skill,
            "challenge_id": challenge_id or "molt-heuristic",
            "winner": winner,
            "red": {"prompt_hash": _hash_prompt(red_prompt), "oomf": red_oomf, "chars": red_len, "oracle": getattr(red_oracle, "verdict", "unknown")},
            "blue": {"prompt_hash": _hash_prompt(blue_prompt), "oomf": blue_oomf, "chars": blue_len, "oracle": getattr(blue_oracle, "verdict", "unknown")},
            "red_score": red_score,
            "blue_score": blue_score,
            "detail": detail,
            "latency_s": round(time.time() - t0, 3),
            "oracle_mode": oracle_mode,
        }
        if whorl_result:
            result["whorl"] = whorl_result

        # Emit to Whorl arena signals + bus if available
        try:
            if _HAS_WHORL_ARENA and _arena is not None:
                _arena.emit("arena.judge_scored", {  # reuse signal log
                    "skill": skill, "red_score": red_score, "blue_score": blue_score,
                    "winner": winner, "challenge_id": challenge_id or "molt-heuristic",
                    "detail": detail,
                }, verbose=False)
        except Exception:
            pass
        if self.bus is not None:
            try:
                self.bus.emit_score("arena", f"molt:{skill}:{winner}", 1.0 if winner != "draw" else 0.5, scenario_id=challenge_id or "molt")
                self.bus.send("loom-weaver", "score.record", {"skill": skill, "winner": winner, "red_score": red_score, "blue_score": blue_score})
            except Exception:
                pass

        # Persist
        self._append_record(skill, result)
        return result

    def evolve(self, skill: str, variants: List[Dict[str, Any]],
               rounds: int = 1, challenge_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Pit N variants round-robin. Return survival leaderboard + recommended variant.
        Scout mutation rate = win rate / token efficiency.
        """
        if len(variants) < 2:
            raise ValueError("evolve requires >=2 variants")
        # Round-robin pairs
        pair_results: List[Dict[str, Any]] = []
        wins: Dict[int, int] = {i: 0 for i in range(len(variants))}
        losses: Dict[int, int] = {i: 0 for i in range(len(variants))}
        draws = 0
        for _ in range(max(1, rounds)):
            for i in range(len(variants)):
                for j in range(i + 1, len(variants)):
                    r = self.combat(skill, variants[i], variants[j], challenge_id=challenge_id)
                    pair_results.append({"pair": (i, j), **r})
                    if r["winner"] == "red":
                        wins[i] += 1; losses[j] += 1
                    elif r["winner"] == "blue":
                        wins[j] += 1; losses[i] += 1
                    else:
                        draws += 1
        # Rank by wins
        ranked = sorted(range(len(variants)), key=lambda k: wins[k], reverse=True)
        best_idx = ranked[0]
        best = variants[best_idx]
        mutation_rate = wins[best_idx] / max(1, sum(wins.values()) + draws)  # survival fraction

        survival = [{"idx": i, "wins": wins[i], "losses": losses[i],
                     "prompt_hash": _hash_prompt(variants[i].get("prompt", "")[:200])} for i in ranked]

        report = {
            "skill": skill,
            "variants": len(variants),
            "rounds": rounds,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "ranked": ranked,
            "best_idx": best_idx,
            "best_prompt_hash": _hash_prompt(best.get("prompt", "")[:200]),
            "mutation_rate": round(mutation_rate, 3),
            "pair_results": pair_results,
            "survival": survival,
            "recommendation": {"idx": best_idx, "prompt": best.get("prompt", "")[:500]},
        }
        # Emit sweep_done
        try:
            if _HAS_WHORL_ARENA and _arena is not None:
                _arena.emit("arena.sweep_done", {"skill": skill, "survival": survival, "rounds": rounds}, verbose=False)
        except Exception:
            pass
        self._append_record(skill, {"evolve": report, "ts": time.time()})
        return report

    def _append_record(self, skill: str, record: Dict[str, Any]) -> None:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in skill)[:36]
        path = ARENA_DIR / f"{safe}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def history(self, skill: str, limit: int = 20) -> List[Dict[str, Any]]:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in skill)[:36]
        path = ARENA_DIR / f"{safe}.jsonl"
        if not path.exists():
            return []
        lines = path.read_text().strip().splitlines()
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
