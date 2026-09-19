#!/usr/bin/env python3
"""
One-off post-reorganization hardening probe for the MOLT runtime.

This is not a general utility: it takes no arguments and the skill name and probe
query in `main()` are hardcoded to the boardroom post-reorg check it was written
for. It was paraphrased from a task file under `/tmp`, which it does **not** read —
the inputs are in the source. Read the final PASS/FAIL line.

It performs:
1. A dry-run one-shot inference using the "git-state-snapshotter" skill,
   printing the chosen skill and a 300-character preview of the hydrated
   prompt (JSON messages). `dry_run=True` returns before any provider dispatch,
   so this makes no network call and needs no API key.
2. Takes a snapshot of a test skill via StateSnapshotter, printing the snapshot
   version/label and the most recent log entries. This writes runtime state under
   `rag_storage/molt_state/`, which is ignored by Git.
3. Reports PASS/FAIL based on whether any step raised an exception.

Usage:
    python3 -m src.skill.run_retry_task
"""

import sys
import json
import traceback

from src.skill.inference_bridge import molt_one_shot
from src.skill.state_snapshotter import StateSnapshotter


def main() -> int:
    skill_name = "git-state-snapshotter"
    user_query = "stress test the reorganized boardroom at The-Werkz/Official-Vertical-AI-Boardroom"

    # Step 1: dry‑run inference bridge (positional: molt_one_shot(skill_name, query, dry_run=True))
    try:
        hydrated_json = molt_one_shot(skill_name, user_query, dry_run=True)
        # molt_one_shot with dry_run returns a JSON‑formatted string
        hydrated = json.loads(hydrated_json)
        preview = json.dumps(hydrated, ensure_ascii=False, indent=2)[:300]

        print(f"Skill chosen: {skill_name}")
        print("Hydrated preview (first 300 chars):")
        print(preview)
    except Exception as e:
        print("Error during dry‑run inference:", e, file=sys.stderr)
        traceback.print_exc()
        print("FAIL")
        return 1

    # Step 2: snapshot a test skill
    try:
        snapper = StateSnapshotter()
        snapshot_state = {
            "probe": "boardroom_post_reorg_aider",
            "root": "The-Werkz/Official-Vertical-AI-Boardroom",
        }
        sv = snapper.snapshot("aider-skill-test-post-reorg", snapshot_state)
        version = sv.get("version")
        label = sv.get("label")
        print(f"\nSNAPSHOT version:{version} label:{label}")

        log_entries = snapper.log("aider-skill-test-post-reorg", limit=3)
        print("Recent log entries:")
        print(json.dumps(log_entries, ensure_ascii=False, indent=2))
    except Exception as e:
        print("Error during snapshotting:", e, file=sys.stderr)
        traceback.print_exc()
        print("FAIL")
        return 1

    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
