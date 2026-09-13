"""
src.audience.context — Context-scoped user toggles and CLI flags on the fly.
Used by AudienceManager.set_context / governor flag parsing / SkillManager hydrate path.

No persistence — session only. Serialize to dict for transport between CLI invocations.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, Set


@dataclass
class AudienceContext:
    user_id: str = "anon"
    gambit_enabled: bool = False
    oomf_overrides: Dict[str, int] = field(default_factory=dict)  # skill -> 1..5
    flags: Dict[str, Any] = field(default_factory=dict)  # raw Governor.parse_cli_flags output
    elevate_scopes: Set[str] = field(default_factory=set)

    def override_oomf(self, skill: str, level: int) -> None:
        self.oomf_overrides[skill] = max(1, min(5, int(level)))

    def clear_oomf(self, skill: Optional[str] = None) -> None:
        if skill is None:
            self.oomf_overrides.clear()
        else:
            self.oomf_overrides.pop(skill, None)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["elevate_scopes"] = sorted(self.elevate_scopes)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AudienceContext":
        scopes = set(d.get("elevate_scopes", []))
        return cls(
            user_id=d.get("user_id", "anon"),
            gambit_enabled=bool(d.get("gambit_enabled", False)),
            oomf_overrides=dict(d.get("oomf_overrides", {})),
            flags=dict(d.get("flags", {})),
            elevate_scopes=scopes,
        )

    @classmethod
    def from_cli(cls, argv: Optional[list] = None, user_id: str = "anon") -> "AudienceContext":
        """Parse current CLI flags into a context (zero-bloat, ignores unknowns)."""
        try:
            from src.skill.governor import Governor
            flags = Governor.parse_cli_flags(argv)
        except Exception:
            flags = {"oomf_level": None, "elevate": False, "elevate_scopes": set()}
        ctx = cls(user_id=user_id, flags=flags, elevate_scopes=set(flags.get("elevate_scopes", set())))
        # If a global --oomf was passed without a skill qualifier, keep it as default hint
        # (per-skill overrides still win). Stored under "_global_oomf".
        if flags.get("oomf_level") is not None:
            ctx.oomf_overrides["_global_oomf"] = flags["oomf_level"]
        return ctx
