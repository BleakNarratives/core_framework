# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: agents
# FKA: ~/orchestrator.py
# ROLE: orchestrator.py — see canonical at ~/projects/agents/orchestrators/orchestrator.py
# SESSION: 2026-09-08
# TIER: 3
# [/DNA_TAG]

import os
import importlib.util
import sys

# Whitelist of allowed agent files (prevents arbitrary execution)
WHITELIST_FILE = "allowed_agents.txt"

class Orchestrator:
    def __init__(self):
        self.allowed_agents = self._load_whitelist()

    def _load_whitelist(self):
        if not os.path.exists(WHITELIST_FILE):
            return set()
        with open(WHITELIST_FILE, 'r') as f:
            return set(line.strip() for line in f if line.strip())

    def list_agents(self):
        print("[*] Approved Agents:")
        for agent in self.allowed_agents:
            print(f" - {agent}")

    def run(self, agent_name):
        if agent_name not in self.allowed_agents:
            print(f"[-] Security error: Agent '{agent_name}' not in {WHITELIST_FILE}.")
            return
        
        # Simple search for the file path based on name
        found_path = None
        for root, _, files in os.walk(os.getcwd()):
            if f"{agent_name}.py" in files:
                found_path = os.path.join(root, f"{agent_name}.py")
                break
        
        if not found_path:
            print(f"[-] Agent '{agent_name}' file not found.")
            return

        print(f"[*] Executing {agent_name} safely...")
        try:
            spec = importlib.util.spec_from_file_location(agent_name, found_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, 'main'):
                module.main()
        except Exception as e:
            print(f"[-] Execution error: {e}")

def main():
    orch = Orchestrator()
    print("--- Secure Minimal Orchestrator ---")
    print(f"Only agents in {WHITELIST_FILE} are executable.")
    
    while True:
        cmd = input("swarm> ").strip().split()
        if not cmd: continue
        
        if cmd[0] == 'list':
            orch.list_agents()
        elif cmd[0] == 'run':
            if len(cmd) > 1:
                orch.run(cmd[1])
            else:
                print("[-] Specify agent name.")
        elif cmd[0] == 'exit':
            break
        else:
            print("[-] Unknown command.")

if __name__ == "__main__":
    main()
