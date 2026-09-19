import json
import sys
from pathlib import Path

def render_boardroom_status():
    history_file = Path(".boardroom_history.jsonl")
    if not history_file.exists():
        return "[Boardroom: Waiting...]"

    with open(history_file, "r") as f:
        lines = f.readlines()
        if not lines:
            return "[Boardroom: Empty]"
        
        last_entry = json.loads(lines[-1])
        payload = last_entry.get("sanitized_payload", {})
        
        persona = payload.get("persona", "Unknown")
        status = payload.get("status", "UNKNOWN")
        
        return f"[{persona}: {status}]"

if __name__ == "__main__":
    print(render_boardroom_status())
