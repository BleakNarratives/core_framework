#!/usr/bin/env python3
"""
demo.py — show what the arbiter decides, and why.

Runs a realistic task mix through the arbiter against a supplied HostProfile
and prints the decision, the tier, and the reasoning. No network, no model
required, so it runs anywhere in under a second.

    python3 demo.py                       # the documented 2.6GiB N200 host
    python3 demo.py --host-gpu            # a 32GB GPU box
    python3 demo.py --profile p.json      # a profile from bench.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cascade import CascadeRequest, HostProfile, TaskShape, Tier, arbitrate, measured_n200_profile  # noqa: E402

# (label, request) — the kind of work a real agent stack actually dispatches.
WORKLOAD = [
    ("tag this document's language",   CascadeRequest(TaskShape.CLASSIFY, input_tokens=800)),
    ("pick the next tool to call",      CascadeRequest(TaskShape.ROUTE, input_tokens=400)),
    ("pull name/email/org from a lead", CascadeRequest(TaskShape.EXTRACT, input_tokens=600)),
    ("are these two issues duplicates?", CascadeRequest(TaskShape.DEDUP, input_tokens=1200)),
    ("3-sentence summary",              CascadeRequest(TaskShape.SUMMARIZE_SHORT,
                                                       input_tokens=1500, expected_output_tokens=60)),
    ("write a 900-word article",        CascadeRequest(TaskShape.GENERATE,
                                                       input_tokens=2000, expected_output_tokens=1200)),
    ("debug this stack trace",          CascadeRequest(TaskShape.REASON,
                                                       input_tokens=1800, expected_output_tokens=800)),
    ("refactor this function",          CascadeRequest(TaskShape.CODE_WRITE,
                                                       input_tokens=3000, expected_output_tokens=900)),
    ("summarise a 100k-token corpus",   CascadeRequest(TaskShape.SUMMARIZE_SHORT, input_tokens=100_000)),
]

GPU_HOST = HostProfile(
    name="gpu-box", total_ram_mb=65536, available_ram_mb=48000, cpu_cores=32,
    has_gpu=True, local_tok_per_s=95.0, local_load_s=6.0,
    local_model_installed=True, local_model_mb=16000,
)


def render(host: HostProfile) -> None:
    print(f"\n  host: {host.name}  {host.available_ram_mb}MiB free of {host.total_ram_mb}MiB  "
          f"{host.cpu_cores} cores  {'GPU' if host.has_gpu else 'CPU-only'}")
    if host.local_tok_per_s:
        print(f"  measured local: {host.local_tok_per_s} tok/s, "
              f"{host.local_load_s}s cold load, {host.local_model_mb}MB resident")
    verdict = "ELIGIBLE" if host.local_usable else "NOT ELIGIBLE (insufficient resident memory)"
    print(f"  local tier: {verdict}")
    if not host.local_usable and not host.has_gpu:
        print(f"  → {host.available_ram_mb}MiB available < {host.local_model_mb}MB needed to stay resident")
        print("    a model that cannot stay resident is not 'slow', it is ineligible.")

    print(f"\n  {'task':<38} {'tier':<7} {'why'}")
    print("  " + "-" * 96)
    for label, req in WORKLOAD:
        d = arbitrate(req, host)
        mark = "local " if d.eligible else "CLOUD"
        why = d.reasons[0] if d.reasons else ""
        if len(why) > 46:
            why = why[:43] + "..."
        print(f"  {label:<38} {mark:<7} {why}")
    loc = sum(1 for _, r in WORKLOAD if arbitrate(r, host).eligible)
    print(f"\n  {loc}/{len(WORKLOAD)} tasks eligible locally on this host.\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Demo cascade arbitration decisions.")
    ap.add_argument("--profile", help="JSON profile from bench.py")
    ap.add_argument("--host-gpu", action="store_true", help="use a hypothetical GPU host")
    args = ap.parse_args(argv)

    if args.profile:
        data = json.loads(Path(args.profile).read_text())
        p = data.get("profile", data)
        host = HostProfile(
            name=p.get("name", "profile"), total_ram_mb=p.get("total_ram_mb", 0),
            available_ram_mb=p.get("available_ram_mb", 0), cpu_cores=p.get("cpu_cores", 0),
            has_gpu=p.get("has_gpu", False), local_tok_per_s=p.get("local_tok_per_s", 0.0),
            local_load_s=p.get("local_load_s", 0.0),
            local_model_installed=p.get("local_model_installed", False),
            local_model_mb=p.get("local_model_mb", 0),
        )
    elif args.host_gpu:
        host = GPU_HOST
    else:
        host = measured_n200_profile()

    print("\n" + "=" * 98)
    print("  CASCADE ARBITRATION — which requests may run locally")
    print("=" * 98)
    render(host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
