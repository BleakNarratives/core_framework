# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: thoth
# ROLE: Undocumented module
# TIER: Scout (6)
# AUTHOR: BleakNarratives
# SESSION: 2026-08-22 ShipWreckD OS Builder — auto-tagged by DNA Sweeper
# [/DNA_TAG]

import requests
import json
import os

class CoachBleakAdapter:
    """Wraps the Coach Bleak Accountability Engine for aggressive recovery."""
    BASE_URL = "http://localhost:5000"

    def analyze_scenario(self, scenario, mode="analysis", additional_prompt=None):
        """
        Sends a scenario to Coach Bleak for analysis.
        Modes: 'analysis', 'audit', 'psychoWarfare', 'perpWalk'
        """
        payload = {
            "scenarioInput": scenario,
            "currentMode": mode,
            "additionalPrompt": additional_prompt
        }
        try:
            # Since app.py uses async routes, we call it via standard POST
            response = requests.post(f"{self.BASE_URL}/analyze_scenario", json=payload, timeout=30)
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    def generate_pressure_notice(self, client_name, amount_due, days_overdue):
        """
        Custom macro to generate a high-pressure recovery notice.
        """
        scenario = f"Client {client_name} owes {amount_due} sats and is {days_overdue} days overdue. They are ignoring Mrs. Higgins."
        return self.analyze_scenario(scenario, mode="psychoWarfare")

# Singleton
coach_bleak = CoachBleakAdapter()
