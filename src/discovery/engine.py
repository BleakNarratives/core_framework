"""
DiscoveryEngine — MOLT Living Markdown extension
Adds runtime scanning for active SKILL.md trees, local RAG sidecars, and terminal-exposed "oomf" toggles.
"""

try:
    from src.skill.skill_manager import SkillManager
    HAS_MOLT = True
except ImportError:
    SkillManager = None
    HAS_MOLT = False


class DiscoveryEngine:
    """
    Identifies content opportunities based on audience insights.
    MOLT: also scans Living SKILL.md trees + RAG sidecars.
    """
    def __init__(self, audience_manager):
        self.audience_manager = audience_manager
        # MOLT: optional skill manager for hybrid discovery
        self._skill_manager = None
        if HAS_MOLT:
            try:
                self._skill_manager = SkillManager()
            except Exception:
                self._skill_manager = None

    def discover_topics(self):
        insights = self.audience_manager.get_insights()
        topics = []

        # Rule: Problems/Frustrations -> Solution-focused content
        for problem in insights.get("problems_frustrations", []):
            topics.append({"topic": f"How to solve {problem}", "type": "Solution"})

        # Rule: Interests -> Deep-dive/Insights content
        for interest in insights.get("interests", []):
            topics.append({"topic": f"Deep dive into {interest}", "type": "Insight"})

        # MOLT: enrich with skill-derived topics if living skills exist
        if self._skill_manager:
            try:
                for skill in self._skill_manager.list_skills()[:5]:
                    front = self._skill_manager.parse_frontmatter(skill)
                    # Only surface skills with meaningful depth
                    if int(front.get("scout", {}).get("depth", 1)) >= 3:
                        topics.append({"topic": f"Living skill: {skill}", "type": "MOLT", "skill": skill, "frontmatter": front})
            except Exception:
                pass

        return topics

    # ── MOLT: Living skill discovery ───────────────────────────
    def scan_active_skills(self):
        """
        Runtime scanning for active SKILL.md trees, local RAG sidecars,
        and terminal-exposed "oomf" toggles.
        Returns list of {name, frontmatter, has_sidecar, sidecar_lines, oomf, oracle_mode}.
        Pass-through to SkillManager.scan_active if available; otherwise [].
        """
        if not self._skill_manager:
            return []
        try:
            return self._skill_manager.scan_active()
        except Exception:
            return []

    def scan_rag_sidecars(self):
        """List RAG sidecar files (rag_storage/sidecars/*.jsonl)."""
        if not self._skill_manager:
            return []
        try:
            import pathlib
            sidecars = pathlib.Path("rag_storage/sidecars")
            if not sidecars.exists():
                return []
            return [{"skill": p.stem.replace(".scout", "").replace(".jsonl", ""), "path": str(p), "lines": sum(1 for _ in open(p))}
                    for p in sidecars.glob("*.jsonl")]
        except Exception:
            return []

    def oomf_toggle(self, skill_name, level: int):
        """
        Terminal-exposed "oomf" toggle: update a skill's scout.depth frontmatter.
        Returns new frontmatter or {}.
        """
        if not self._skill_manager:
            return {}
        try:
            from pathlib import Path
            path = self._skill_manager.skill_path(skill_name)
            if not path:
                return {}
            level = max(1, min(5, int(level)))
            return self._skill_manager.inject_frontmatter(path, overrides={"scout": {"depth": level}})
        except Exception:
            return {}
