import json
import os

# MOLT: optional gambit toggle per user (human ↔ doc tandem)
try:
    from src.audience.context import AudienceContext  # optional
    HAS_AUDIENCE_CONTEXT = True
except ImportError:
    HAS_AUDIENCE_CONTEXT = False

class AudienceManager:
    def __init__(self, data_path="data/audience.json"):
        self.data_path = data_path
        self.audience_data = self._load_data()

    def _load_data(self):
        if os.path.exists(self.data_path):
            with open(self.data_path, 'r') as f:
                return json.load(f)
        return {
            "niche": None,
            "audience": {
                "problems_frustrations": [],
                "interests": [],
                "fears_concerns": [],
                "desires_goals": [],
                "blockers_obstacles": [],
                "motivations": []
            }
        }

    def _save_data(self):
        with open(self.data_path, 'w') as f:
            json.dump(self.audience_data, f, indent=4)

    def set_niche(self, niche):
        self.audience_data["niche"] = niche
        self._save_data()

    def add_insight(self, category, insight):
        if category in self.audience_data["audience"]:
            self.audience_data["audience"][category].append(insight)
            self._save_data()
        else:
            raise ValueError(f"Invalid category: {category}")

    def get_insights(self):
        return self.audience_data["audience"]

    # ── MOLT: context-scoped toggles (gambit / oomf / CLI flags on the fly) ──
    def set_context(self, ctx):
        """Attach a per-session AudienceContext (gambit_id, oomf, flags). No-op if not available."""
        if HAS_AUDIENCE_CONTEXT:
            from src.audience.context import AudienceContext
            if isinstance(ctx, AudienceContext):
                self._audience_context = ctx
            elif isinstance(ctx, dict):
                self._audience_context = AudienceContext.from_dict(ctx)
        else:
            self._audience_context = ctx

    def get_context(self):
        return getattr(self, "_audience_context", None)

    def apply_gambit_flag(self, skill_name, level: int):
        """Set per-skill OOMF override via Gambit (no file write, session only)."""
        try:
            from src.skill.gambit import InstarEngine
            # lightweight: store on instance, SkillManager reads via context on hydrate
            self._gambit_overrides = getattr(self, "_gambit_overrides", {})
            self._gambit_overrides[skill_name] = max(1, min(5, int(level)))
            return dict(self._gambit_overrides)
        except Exception:
            return {}

    def clear_gambit_flags(self):
        self._gambit_overrides = {}
        self._audience_context = None
