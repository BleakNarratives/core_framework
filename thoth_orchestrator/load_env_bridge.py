# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: thoth
# ROLE: Undocumented module
# TIER: Scout (6)
# AUTHOR: BleakNarratives
# SESSION: 2026-08-22 ShipWreckD OS Builder — auto-tagged by DNA Sweeper
# [/DNA_TAG]

import os
from pathlib import Path

def bootstrap_environment():
    """
    Surgically injects the safe RootBase .env parameters directly 
    into the running Python process memory space.
    """
    env_path = Path("/home/bleaknarratives/RootBase/income_engine/.env")
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                clean_line = line.strip()
                if clean_line and not clean_line.startswith('#') and '=' in clean_line:
                    key, value = clean_line.split('=', 1)
                    # Strip any lingering quotes from the bash migration
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")
        print("[BRIDGE] Secure environment parameters bootstrapped to memory.")
    else:
        print("[WARN] Persistent .env configuration matrix not found.")
