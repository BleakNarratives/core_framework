# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: agents
# FKA: ~/simulator.py
# ROLE: simulator.py — see canonical at ~/projects/agents/sim/simulator.py
# SESSION: 2026-09-08
# TIER: 3
# [/DNA_TAG]

#!/usr/bin/env python3
import datetime
import random

class Simulator:
    def __init__(self):
        self.scenario = None

    def log(self, sender, message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {sender:10} | {message}")

    def run_scenario(self, scenario_name, context):
        self.log("SYSTEM", f"INITIALIZING SIMULATION: {scenario_name}")
        self.log("THOUGHT", "Analyzing context...")
        
        if scenario_name == "father_news":
            self.log("AGENT_SON", "I need to tell him. It’s heavy.")
            self.log("THOUGHT", "Constructing empathetic approach.")
            self.log("AGENT_SON", "Dad, I have some news. It’s… it’s life-changing.")
            self.log("AGENT_FATHER", "You're scaring me. What is it?")
            self.log("AGENT_SON", "It's about... about a young lady. She's pregnant.")
        
        elif scenario_name == "loss_notification":
            self.log("AGENT_A", "How do I tell them? They don't know they passed.")
            self.log("THOUGHT", "Prioritizing emotional safety.")
            self.log("AGENT_A", "I think we need to talk about what happened.")
            self.log("AGENT_B", "Why? Is everything okay?")
        
        self.log("SYSTEM", "SIMULATION COMPLETE")

if __name__ == "__main__":
    sim = Simulator()
    # Let's run one as a demo
    sim.run_scenario("father_news", "Context: Telling father about unexpected pregnancy.")
