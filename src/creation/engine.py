"""
CreationEngine — MOLT Living Markdown extension
Injects default Scout/Oracle/privilege YAML headers into new skill generation.
Hooks local RAG sidecars for hydrated prompts.
"""
import json
from pathlib import Path

try:
    from src.skill.skill_manager import SkillManager, DEFAULT_FRONTMATTER
    HAS_MOLT = True
except ImportError:
    SkillManager = None
    DEFAULT_FRONTMATTER = {"name": "unnamed", "version": "1.0.0", "scout": {"depth": 3, "interval": "6h", "target_domains": []}, "oracle": {"mode": "strict", "verify_compliance": []}, "privileges": {"elevated": False}}
    HAS_MOLT = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    yaml = None
    HAS_YAML = False

TEMPLATE_PATH = Path("templates/SKILL.template.md")


class CreationEngine:
    """
    Generates structured content based on topic and context.
    MOLT: injects default Scout/Oracle YAML headers into new skills.
    """
    def generate_content_plan(self, topic, format_type):
        # This is a functional placeholder. It generates a structure, not the actual text.
        # This allows for modular expansion of the content itself later.

        plan = {
            "topic": topic,
            "format": format_type,
            "structure": [
                {"component": "hook", "objective": "Earn attention via curiosity or problem statement"},
                {"component": "body", "objective": "Deliver value neutrally"},
                {"component": "conclusion", "objective": "Summarize takeaways"}
            ]
        }
        # MOLT: attach hydrated RAG context if a skill topic maps to a living skill
        if HAS_MOLT and topic:
            try:
                mgr = SkillManager()
                # heuristic: topic slug
                slug = topic.lower().replace(" ", "-").replace("_", "-")[:40]
                if slug in mgr.list_skills():
                    plan["molt"] = {
                        "hydrated_skill": slug,
                        "frontmatter": mgr.parse_frontmatter(slug),
                        "rag_chars": len(mgr.hydrate(slug)),
                    }
            except Exception:
                pass
        return plan

    # ── MOLT: Living skill generation ────────────────────────────
    def create_living_skill(self, name: str, description: str = "",
                            scout_depth: int = 3,
                            target_domains=None,
                            oracle_mode: str = "strict",
                            verify_compliance=None,
                            output_path: str = None) -> dict:
        """
        Create a new Living SKILL.md from the MOLT template with injected frontmatter.
        Returns {path, frontmatter, body_preview}.
        """
        target_domains = target_domains or []
        verify_compliance = verify_compliance or []
        # Clamp depth
        scout_depth = max(1, min(5, int(scout_depth)))
        if oracle_mode not in ("strict", "permissive", "user_only"):
            oracle_mode = "strict"

        frontmatter = {
            "name": name,
            "version": "1.0.0",
            "scout": {"depth": scout_depth, "interval": "6h", "target_domains": target_domains},
            "oracle": {"mode": oracle_mode, "verify_compliance": verify_compliance},
            "privileges": {"elevated": False},
        }

        # Load template
        if TEMPLATE_PATH.exists():
            template = TEMPLATE_PATH.read_text(encoding="utf-8")
            # Replace placeholders
            body = template
            # If template has frontmatter, strip it and use our injected one
            if body.startswith("---"):
                # find closing ---
                end = body.find("\n---", 3)
                if end != -1:
                    body = body[end + 4:].lstrip()
            body = body.replace("{{SKILL_NAME}}", name).replace("my-living-skill", name)
            if description:
                body = body.replace("Describe the core job here.", description)
        else:
            body = f"# {name}\n\n{description or 'Living skill — MOLT hydrated.'}\n"

        # Serialize frontmatter
        if HAS_YAML:
            fm_text = yaml.safe_dump(frontmatter, sort_keys=False)
        else:
            # minimal
            lines = [f"name: {name}", "version: 1.0.0", "scout:", f"  depth: {scout_depth}", '  interval: "6h"']
            if target_domains:
                lines.append(f"  target_domains: [{', '.join(target_domains)}]")
            else:
                lines.append("  target_domains: []")
            lines += ["oracle:", f"  mode: {oracle_mode}"]
            if verify_compliance:
                lines.append(f"  verify_compliance: [{', '.join(verify_compliance)}]")
            else:
                lines.append("  verify_compliance: []")
            lines += ["privileges:", "  elevated: false"]
            fm_text = "\n".join(lines) + "\n"

        full = f"---\n{fm_text}---\n{body}\n"

        # Determine output path
        if output_path:
            dest = Path(output_path)
        else:
            dest = Path(f".agents/skills/{name}/SKILL.md")
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Also ensure scout sidecar dir
        (dest.parent / "scout").mkdir(exist_ok=True)
        # Write traces.jsonl + config.yaml for consistency with ScoutEmpire
        sc_cfg = dest.parent / "scout" / "config.yaml"
        if not sc_cfg.exists():
            sc_cfg.write_text(f"name: {name}-scout\nversion: 1.0.0\ndesired_settings:\n  optimize_for: {name}\nscout:\n  depth: {scout_depth}\n", encoding="utf-8")
        (dest.parent / "scout" / "traces.jsonl").touch(exist_ok=True)
        dest.write_text(full, encoding="utf-8")
        return {"path": str(dest), "frontmatter": frontmatter, "body_preview": body[:800]}

    def hydrate_skill(self, skill_name: str, oomf_level=None) -> str:
        """MOLT: hydrate a skill's RAG sidecars into a prompt chunk."""
        if not HAS_MOLT:
            return ""
        try:
            mgr = SkillManager()
            return mgr.hydrate(skill_name, oomf_level=oomf_level)
        except Exception:
            return ""
