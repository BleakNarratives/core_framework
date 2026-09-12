#!/usr/bin/env python3
"""
drift_reconcile.py — Reconcile Chromebook canonical vs prior A9 intake.

Compares:
  - Prior intake INTAKE_MANIFEST.json (2026-08-21, 447 files, MTP-only)
  - Live Chromebook RootBase manifest (fresh scan)
  - Any new RESCUE_A9_* dirs (if present)

Emits: ~/RESCUE_DRIFT_REPORT.md  + JSON sidecar
"""
import json
import pathlib
import sys
from datetime import datetime, timezone

HOME = pathlib.Path.home()
PRIOR = HOME / "NAT-Recovery-Kernel/intake/2026-08-21-samsung-a9-001/INTAKE_MANIFEST.json"
ROOTBASE = HOME / "RootBase"
OUT_MD = HOME / "RESCUE_DRIFT_REPORT.md"
OUT_JSON = HOME / "RESCUE_DRIFT_REPORT.json"

sys.path.insert(0, str(ROOTBASE))
from fleet_telemetry.scanner import scan_directory  # noqa: E402

print("[drift] Loading prior intake...")
prior = json.load(open(PRIOR))
prior_paths = {f["relative_path"]: f for f in prior["files"]}
print(f"[drift] Prior: {len(prior_paths)} files, {prior['total_bytes']/1e6:.1f} MB, excluded={prior['excluded']}")

print("[drift] Scanning live Chromebook RootBase (depth=4)...")
live = scan_directory(str(ROOTBASE), device_id="chromebook", max_depth=4)
live_paths = live["files"]
print(f"[drift] Live: {live['stats']}")

rescues = sorted(HOME.glob("RESCUE_A9_*"))
rescue = rescues[-1] if rescues else None
rescue_manifest = None
if rescue and (rescue / "INTAKE_MANIFEST.json").exists():
    rescue_manifest = json.load(open(rescue / "INTAKE_MANIFEST.json"))
    print(f"[drift] Rescue: {rescue} -> {rescue_manifest['file_count']} files")
elif rescue:
    print(f"[drift] Rescue dir exists but no manifest yet: {rescue}")
else:
    print("[drift] No RESCUE_A9_* dir yet — report will show gap only")

prior_set = set(prior_paths)


def suffix(p, n=2):
    parts = pathlib.PurePosixPath(p).parts
    return "/".join(parts[-n:]) if len(parts) >= n else p


prior_suffixes = {suffix(k, 2): k for k in prior_set}
live_suffixes = {suffix(k, 2): k for k in live_paths}

overlap = set(prior_suffixes) & set(live_suffixes)
live_only = set(live_suffixes) - set(prior_suffixes)
prior_only = set(prior_suffixes) - set(live_suffixes)

zones = {
    "termux_home": sum(1 for p in prior_paths if "termux" in p.lower() or "com.termux" in p.lower()),
    "r26": sum(1 for p in prior_paths if "/r26" in p.lower() or p.lower().endswith("/r26")),
    "root_2026": sum(1 for p in prior_paths if "root_2026" in p.lower()),
    "internal_RootBase": sum(1 for p in prior_paths if "Internal storage/RootBase" in p),
}

prior_only_big = len(prior_only) > 100
excluded_git = ".git directories" in str(prior.get("excluded", []))
gaps_critical = (zones["r26"] == 0) or (zones["termux_home"] < 10) or excluded_git or prior_only_big

verdict = "PRIOR INTAKE WAS PARTIAL — rescue required (P0)" if gaps_critical else "ok"

report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "prior": {"path": str(PRIOR), "files": len(prior_paths), "bytes": prior["total_bytes"], "excluded": prior["excluded"]},
    "live": {"path": str(ROOTBASE), "stats": live["stats"], "files": len(live_paths)},
    "rescue": {"path": str(rescue) if rescue else None, "files": rescue_manifest["file_count"] if rescue_manifest else None},
    "overlap_suffix": len(overlap),
    "live_only_suffix": len(live_only),
    "prior_only_suffix": len(prior_only),
    "gaps_prior_intake": zones,
    "verdict": verdict,
}

json.dump(report, open(OUT_JSON, "w"), indent=2)

# Build MD report with string concatenation (avoids f-string triple-quote hell)
md = "# A9 Drift Reconciliation — " + report["generated_at"] + "\n\n"
md += "**Prior intake (2026-08-21):** `" + str(PRIOR) + "` — " + str(len(prior_paths)) + " files / " + f"{prior['total_bytes']/1e6:.1f}" + " MB\n"
md += "Excluded: " + ", ".join(prior["excluded"]) + "\n"
md += "Modes: " + prior["connection_mode"] + "\n\n"
md += "**Live Chromebook RootBase:** `" + str(ROOTBASE) + "` — " + str(live["stats"]["total_files"]) + " files / " + str(live["stats"]["total_mb"]) + " MB\n\n"
md += "**Rescue dir (newest):** `" + str(rescue or "(none yet — run a9_rescue.sh)") + "`\n"
if rescue_manifest:
    md += "  — " + str(rescue_manifest["file_count"]) + " files / " + f"{rescue_manifest['total_bytes']/1e6:.1f}" + " MB\n"
md += "\n## Verdict\n\n**" + report["verdict"] + "**\n\n"
md += "Prior intake gaps (why rescue is P0):\n"
md += "- termux_home (com.termux/data/data): " + str(zones["termux_home"]) + " files in prior (expected 0 — MTP blind)\n"
md += "- /r26 on SD: " + str(zones["r26"]) + " files (expected 0)\n"
md += "- /root_2026 on SD: " + str(zones["root_2026"]) + " files (partial — only ModMind/nat_vcs subset)\n"
md += "- Internal RootBase: prioritized but 198MB live vs 16MB prior suggests growth since 2026-08-21\n"
md += "- Excluded .git/.env/.vault: " + str(excluded_git) + " — quarterly work holds real config\n"
md += "- Prior-only suffixes (A9-unique, Chromebook-missing): " + str(len(prior_only)) + " — huge drift\n\n"
md += "## Overlap (by suffix, last 2 path components)\n\n"
md += "- Overlap: " + str(len(overlap)) + " suffixes share names\n"
md += "- Live-only (Chromebook has, prior A9 lacked): " + str(len(live_only)) + "\n"
md += "- Prior-only (A9 had, Chromebook lacks): " + str(len(prior_only)) + "\n\n"
md += "## Live-only sample (first 30 — Chromebook drift since intake)\n\n```\n"
for s in sorted(live_only)[:30]:
    md += live_suffixes[s] + "\n"
md += "```\n\n## Prior-only sample (first 30 — A9-unique)\n\n```\n"
for s in sorted(prior_only)[:30]:
    md += prior_suffixes[s] + "\n"
md += "```\n\n"
md += "## What the rescue WILL close\n\n"
md += "- `termux_home/` — ADB or on-device tar (`tar -czf /sdcard/termux_home_*.tar.gz -C /data/data/com.termux/files home`)\n"
md += "- `sdcard_root_2026/` + `sdcard_r26/` — ADB+MTP with SD volume scan (/storage/<ID>/)\n"
md += "- `internal_RootBase/` — full copy with .git/.env/.vault intact (prior excluded them)\n\n"
md += "## Next\n\n```bash\n./tools/rescue/a9_rescue.sh --check          # preflight\n./tools/rescue/a9_rescue.sh --dry-run        # plan\n./tools/rescue/a9_rescue.sh                  # capture (plug A9, share to Linux)\ncat ~/RESCUE_DRIFT_REPORT.md\n```\n\n---\nGenerated by `tools/rescue/drift_reconcile.py`\n"

open(OUT_MD, "w").write(md)
print(md)
print(f"\n[drift] Wrote {OUT_MD}")
print(f"[drift] Wrote {OUT_JSON}")
