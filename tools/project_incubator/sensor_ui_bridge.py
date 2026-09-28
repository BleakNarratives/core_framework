#!/usr/bin/env python3
"""
Sensor-UI Bridge (sensor_ui_bridge.py)
Hardened version: production-grade event mapping.
"""

import sys
import json
import logging
import argparse
from pathlib import Path

# Setup Logging
LOG_FILE = Path.home() / "logs" / "sensor_ui_bridge.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stderr)]
)

# Event Mapping
EVENT_MAP = {
    "amplitude_spike": "TRIGGER_UI_ACTION_NORMAL",
    "high_freq_spike": "TRIGGER_UI_SONIC_EVENT",
}

def process_event(line: str):
    """Parses and maps a single event."""
    try:
        event_data = json.loads(line)
        event_type = event_data.get("event")
        
        if event_type in EVENT_MAP:
            trigger = EVENT_MAP[event_type]
            logging.info(f"Mapping {event_type} -> {trigger}")
            # Emit triggered state change to stdout
            print(json.dumps({"trigger": trigger, "event": event_type}))
            sys.stdout.flush()
        else:
            logging.warning(f"Unknown event type: {event_type}")
            
    except json.JSONDecodeError as e:
        logging.error(f"Malformed JSON: {e} | Line: {line.strip()}")

def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    
    logging.info("Sensor-UI Bridge active. Streaming...")
    
    for line in sys.stdin:
        if line.strip():
            process_event(line)

if __name__ == "__main__":
    main()
