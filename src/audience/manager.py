import json
import os

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
