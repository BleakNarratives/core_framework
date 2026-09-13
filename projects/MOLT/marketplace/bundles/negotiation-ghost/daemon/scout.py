#!/usr/bin/env python3
"""
negotiation-ghost — Scout daemon shim.
Pre-fetches feeds on schedule and writes sidecar.json so IDE hydration needs 0 tool calls.
No MCP server — just a cron/systemd job.
"""
import json, time
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]
SIDECAR = BUNDLE / "sidecar.json"
CONFIG = Path(__file__).with_name("config.yaml")

def main():
    print(f"[{BUNDLE.name}] Scout daemon shim — interval from config.yaml")
    print(f"  sidecar: {SIDECAR}")
    print(f"  config:  {CONFIG}")
    # Hook: integrate with src/skill/scout.py here.
    # e.g. from src.skill.scout import Scout; Scout().run("negotiation-ghost", depth=3)
    data = json.loads(SIDECAR.read_text()) if SIDECAR.exists() else {}
    data["_daemon_check"] = time.time()
    SIDECAR.write_text(json.dumps(data, indent=2))
    print("  wrote daemon heartbeat to sidecar.json")

if __name__ == "__main__":
    main()
