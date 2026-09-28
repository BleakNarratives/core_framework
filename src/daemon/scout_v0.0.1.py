import json
import time
from pathlib import Path

# ScoutDaemon Mock Daemon v0.0.1
# Purpose: Generates initial sidecar.json for hydration

def generate_sidecar():
    sidecar_path = Path("rag_storage/sidecars/scout-plantasm.json")
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "metadata": {
            "version": "0.0.1",
            "timestamp": time.time(),
            "intent": "init_groundwork"
        },
        "state": {
            "status": "hydrated",
            "last_verification": "none"
        }
    }
    
    with open(sidecar_path, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"Generated sidecar at {sidecar_path}")

if __name__ == "__main__":
    generate_sidecar()
