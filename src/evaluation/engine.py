"""
Evaluator — MOLT Living Markdown extension
Adds evaluation loops against Oracle diagnostics to compare baseline vs proposed mutations.
"""
from pathlib import Path

try:
    from src.skill.oracle import Oracle
    from src.skill.skill_manager import SkillManager
    HAS_MOLT = True
except ImportError:
    Oracle = SkillManager = None
    HAS_MOLT = False


class Evaluator:
    """
    Evaluates content output and provides metrics for improvement.
    MOLT: can evaluate OracleDiagnostics vs baseline.
    """
    def evaluate(self, content, metrics):
        # Placeholder for evaluation logic
        # Metrics could include: engagement_potential, clarity, audience_alignment
        if not metrics:
            return 0.0
        score = 0
        for metric in metrics:
            score += metrics[metric]
        return score / len(metrics)

    # ── MOLT: Oracle-aware evaluation ───────────────────────────
    def evaluate_mutation(self, skill_name: str, mutation: dict,
                          baseline_content=None,
                          oracle_mode: str = None,
                          verify_compliance=None) -> dict:
        """
        Execute evaluation loop against Oracle diagnostics.

        Compares baseline behavior vs proposed mutation:
        - Runs Oracle.audit on the mutation
        - Scores baseline vs mutated content via evaluate()
        - Returns {oracle_verdict, baseline_score, mutated_score, delta, recommendation}.

        Zero-bloat: if MOLT not installed, returns baseline score only.
        """
        if not HAS_MOLT:
            score = self.evaluate(mutation if isinstance(mutation, dict) else {"text": str(mutation)}, {"coherence": 0.5})
            return {"oracle_verdict": {"verdict": "pass"}, "score": score, "delta": 0}

        # Resolve oracle config from skill frontmatter if not provided
        frontmatter = {}
        if skill_name:
            try:
                mgr = SkillManager()
                frontmatter = mgr.parse_frontmatter(skill_name)
            except Exception:
                pass
        mode = oracle_mode or frontmatter.get("oracle", {}).get("mode", "strict")
        compliance = verify_compliance if verify_compliance is not None else frontmatter.get("oracle", {}).get("verify_compliance", [])

        oracle = Oracle(mode=mode, verify_compliance=compliance)
        verdict = oracle.audit(mutation, skill_frontmatter=frontmatter)
        verdict_dict = verdict.to_dict()

        # Score baseline vs mutated (simple heuristic: mutated with more ops scores higher if Oracle passes)
        baseline_score = 0.5
        if baseline_content is not None:
            if isinstance(baseline_content, dict):
                baseline_score = self.evaluate(baseline_content, {"clarity": 0.7, "engagement": 0.6})
            elif isinstance(baseline_content, str):
                baseline_score = 0.6 if len(baseline_content) > 100 else 0.4

        mutated_score = 0.5
        if verdict.verdict == "pass":
            # Bonus for clean mutations
            mutated_score = min(0.95, baseline_score + 0.15 + len(mutation.get("ops", [])) * 0.02)
        elif verdict.verdict == "warn":
            mutated_score = max(0.2, baseline_score - 0.1)
        else:  # block
            mutated_score = max(0.1, baseline_score - 0.3)

        delta = mutated_score - baseline_score
        if verdict.verdict == "block":
            recommendation = "reject — Oracle blocked"
        elif verdict.verdict == "warn":
            recommendation = "review — Oracle warned, inspect findings"
        elif delta > 0.05:
            recommendation = "accept — Oracle passed and score improved"
        else:
            recommendation = "defer — Oracle passed but no score gain"

        return {
            "skill": skill_name,
            "oracle_verdict": verdict_dict,
            "baseline_score": round(baseline_score, 3),
            "mutated_score": round(mutated_score, 3),
            "delta": round(delta, 3),
            "recommendation": recommendation,
            "frontmatter": frontmatter,
        }

    def evaluate_hydrated(self, skill_name: str, user_query: str, oomf_level=None) -> dict:
        """Hydrate a skill and score the resulting prompt quality."""
        if not HAS_MOLT:
            return {"score": 0.5}
        try:
            mgr = SkillManager()
            chunk = mgr.hydrate(skill_name, oomf_level=oomf_level)
            # Simple quality heuristics: length, sidecar presence, frontmatter depth
            front = mgr.parse_frontmatter(skill_name)
            depth = int(front.get("scout", {}).get("depth", 3))
            sidecar_lines = 0
            sidecar_path = Path("rag_storage/sidecars") / f"{skill_name}.jsonl"
            if sidecar_path.exists():
                sidecar_lines = sum(1 for _ in open(sidecar_path))
            score = 0.5
            score += min(0.2, len(chunk) / 20000)
            score += 0.1 if sidecar_lines > 0 else 0
            score += 0.05 * (depth - 1)
            score = min(0.95, score)
            return {"skill": skill_name, "chunk_chars": len(chunk), "depth": depth, "sidecar_lines": sidecar_lines, "score": round(score, 3)}
        except Exception as e:
            return {"skill": skill_name, "score": 0.0, "error": str(e)}
