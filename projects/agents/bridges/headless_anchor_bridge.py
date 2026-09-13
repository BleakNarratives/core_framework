# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: agents
# FKA: ~/headless_anchor_bridge.py
# ROLE: headless_anchor_bridge.py — see canonical at ~/projects/agents/bridges/headless_anchor_bridge.py
# SESSION: 2026-09-08
# TIER: 3
# [/DNA_TAG]

import sys
from pathlib import Path
# Add Anchor dir to path to allow importing the main logic
sys.path.append(str(Path(__file__).parent.parent / "Anchor" / "puter_ai_anchor"))

from main import initialize_ai_pipeline, get_anchor_response
import json

class HeadlessAnchor:
    def __init__(self):
        self.generator = initialize_ai_pipeline()

    def process_request(self, user_input: str) -> str:
        return get_anchor_response(self.generator, user_input)

if __name__ == "__main__":
    # Test headless invocation
    anchor = HeadlessAnchor()
    response = anchor.process_request("What is the state of the swarm?")
    print(json.dumps({"response": response}))
