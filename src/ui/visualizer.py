import json
import sys
from pathlib import Path

def render_boardroom_status():
    history_file = Path(".boardroom_history.jsonl")
    if not history_file.exists():
        return "[Boardroom: Waiting...]"

    with open(history_file, "r") as f:
        lines = f.readlines()
        # Drop blank lines so a trailing newline (or a whitespace-only file) is not
        # mistaken for a damaged entry.
        lines = [line for line in lines if line.strip()]
        if not lines:
            return "[Boardroom: Empty]"
        
        # A status line is cosmetic: a truncated or hand-edited entry has to report
        # itself, not raise into whatever asked for the status.
        try:
            last_entry = json.loads(lines[-1])
        except json.JSONDecodeError:
            return "[Boardroom: Unreadable]"
        if not isinstance(last_entry, dict):
            return "[Boardroom: Unreadable]"

        payload = last_entry.get("sanitized_payload")
        if not isinstance(payload, dict):
            payload = {}
        
        persona = payload.get("persona", "Unknown")
        status = payload.get("status", "UNKNOWN")
        
        return f"[{persona}: {status}]"

if __name__ == "__main__":
    print(render_boardroom_status())
