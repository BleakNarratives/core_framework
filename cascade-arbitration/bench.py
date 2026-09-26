#!/usr/bin/env python3
"""
bench.py — measure this host and emit a HostProfile as JSON.

The whole premise of cascade arbitration is that local eligibility is
host-specific. A profile you typed in by hand is a claim; this is a
measurement. Run it on any machine and you get the numbers that decide
whether the local tier is even eligible there.

    python3 bench.py                     # probe ollama, emit profile
    python3 bench.py --model llama3.2:1b # probe a specific model
    python3 bench.py --no-ollama         # measure the host, skip inference
    python3 bench.py --out profile.json  # write to a file

Stdlib only. No network except the optional local Ollama probe, which is
loopback-only and degrades silently if absent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cascade import HostProfile  # noqa: E402

DEFAULT_URI = "http://127.0.0.1:11434"


def _read(path: str, default: int = 0) -> int:
    try:
        return int(Path(path).read_text().strip())
    except Exception:
        return default


def measure_ram_mb() -> tuple[int, int]:
    """(total_mb, available_mb) from /proc, falling back to sysconf."""
    try:
        info = Path("/proc/meminfo").read_text()
        total = int(re.search(r"MemTotal:\s+(\d+) kB", info).group(1)) // 1024
        avail = int(re.search(r"MemAvailable:\s+(\d+) kB", info).group(1)) // 1024
        return total, avail
    except Exception:
        try:
            page = os.sysconf("SC_PAGE_SIZE")
            total = os.sysconf("SC_PHYS_PAGES") * page // (1024 * 1024)
            return total, total
        except Exception:
            return 0, 0


def has_gpu() -> bool:
    return bool(shutil.which("nvidia-smi")) or Path("/dev/kfd").exists()


def probe_ollama(model: str, uri: str, num_thread: int, num_predict: int) -> dict:
    """Measure load time, throughput and resident size for one model.

    Resident size is the number that decides everything, and it is NOT the
    on-disk size: llama3.2:1b is 1.3GB on disk and 505MB resident. A runner
    that swaps is not "slow", it is ineligible.
    """
    out = {"model": model, "available": False}
    try:
        import requests
    except ImportError:
        out["error"] = "requests not installed; skipping inference probe"
        return out

    try:
        tags = requests.get(f"{uri}/api/tags", timeout=5).json()
        installed = {m["name"] for m in tags.get("models", [])}
        if model not in installed and f"{model}:latest" not in installed:
            out["error"] = f"model {model!r} not installed (have: {sorted(installed)})"
            return out
    except Exception as exc:
        out["error"] = f"ollama not reachable at {uri}: {exc}"
        return out

    payload = {
        "model": model,
        "prompt": "Reply with exactly: OK",
        "stream": False,
        "options": {"num_predict": num_predict, "num_ctx": 1024, "num_thread": num_thread},
    }
    try:
        t0 = time.time()
        r = requests.post(f"{uri}/api/generate", json=payload, timeout=600)
        wall = time.time() - t0
        r.raise_for_status()
        d = r.json()
    except Exception as exc:
        out["error"] = f"generate failed: {exc}"
        return out

    eval_s = d.get("eval_duration", 0) / 1e9
    out.update({
        "available": True,
        "load_s": round(d.get("load_duration", 0) / 1e9, 2),
        "wall_s": round(wall, 2),
        "gen_tok_per_s": round(d.get("eval_count", 0) / eval_s, 2) if eval_s > 0 else 0.0,
        "sample": (d.get("response") or "").strip()[:80],
        "resident_mb": runner_resident_mb(),
    })
    return out


def runner_resident_mb() -> int:
    """Resident MB of the local runner process (llama-server / ollama runner)."""
    total = 0
    try:
        ps = subprocess.check_output(["ps", "-eo", "rss,comm"], timeout=10).decode()
    except Exception:
        return 0
    for line in ps.splitlines()[1:]:
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].strip() in ("llama-server", "ollama_llama_server"):
            total += int(parts[0]) // 1024
    return total


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Measure this host for cascade arbitration.")
    ap.add_argument("--model", default="llama3.2:1b")
    ap.add_argument("--uri", default=DEFAULT_URI)
    ap.add_argument("--num-thread", type=int, default=2)
    ap.add_argument("--num-predict", type=int, default=48)
    ap.add_argument("--no-ollama", action="store_true", help="skip the inference probe")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    args = ap.parse_args(argv)

    total_mb, avail_mb = measure_ram_mb()
    probe = ({"skipped": True} if args.no_ollama
             else probe_ollama(args.model, args.uri, args.num_thread, args.num_predict))

    profile = HostProfile(
        name=os.uname().nodename.split(".")[0],
        total_ram_mb=total_mb,
        available_ram_mb=avail_mb,
        cpu_cores=os.cpu_count() or 0,
        has_gpu=has_gpu(),
        local_tok_per_s=probe.get("gen_tok_per_s", 0.0),
        local_load_s=probe.get("load_s", 0.0),
        local_model_installed=bool(probe.get("available")),
        local_model_mb=probe.get("resident_mb", 0),
    )
    result = {
        "profile": {
            "name": profile.name, "total_ram_mb": profile.total_ram_mb,
            "available_ram_mb": profile.available_ram_mb, "cpu_cores": profile.cpu_cores,
            "has_gpu": profile.has_gpu, "local_tok_per_s": profile.local_tok_per_s,
            "local_load_s": profile.local_load_s,
            "local_model_installed": profile.local_model_installed,
            "local_model_mb": profile.local_model_mb,
        },
        "local_usable": profile.local_usable,
        "probe": probe,
    }
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
