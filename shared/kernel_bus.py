#!/usr/bin/env python3
"""
core_framework/shared/kernel_bus.py

GossipBus kernel lock-in — the one-bus contract.

Declares GossipBus as THE canonical kernel bus and demotes every other bus in
the workspace to an adapter. This is the code-side lock-in of the decision the
design docs kept deferring (see DESIGN_INTENT_ASSESSMENT.md §4/§6: "multiple
peer buses" was scored the single highest-risk divergence from the intended
one-kernel architecture).

Pointer-layer rules, same as every launcher in this repo:
  * The canonical kernel file (`RootBase/gossip_bus.py`) is NEVER copied here.
  * Resolution order: $CORE_FRAMEWORK_KERNEL_BUS override > sibling scan
    (`<repo-parent>/RootBase/gossip_bus.py`) > None (graceful).
  * Removing this module has zero effect on any canonical tree.

The other buses are catalogued as demoted adapters with their canonical paths
so the registry can report — honestly — which surfaces still exist as peers.
Nothing is moved, renamed, or deleted: consolidation is a *declaration* plus
an auditable health report, and the physical demotion happens on the machine
that owns those trees.
"""

from __future__ import annotations

import os
from pathlib import Path

# The kernel decision, stated once, in code.
CANONICAL_KERNEL = "gossip_bus"
KERNEL_ENV_VAR = "CORE_FRAMEWORK_KERNEL_BUS"

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = FRAMEWORK_ROOT.parent

# Every known peer bus, demoted to adapter. Paths are canonical-tree pointers,
# not copies. (SyntaxIntelligence's event_bus and OutClaw's outclaw_bus were
# the two named peers in EVENT_BUS.md; Whorl's adapter already calls itself an
# adapter, which is exactly the right shape for everything below the kernel.)
ADAPTER_CATALOG: tuple[dict, ...] = (
    {
        "name": "integration_bus",
        "path": "RootBase/integration_bus.py",
        "note": "RootBase transport — becomes the kernel's local transport adapter",
    },
    {
        "name": "event_bus",
        "path": "SyntaxIntelligence/event_bus.py",
        "note": "SyntaxIntelligence pub/sub — bridge to the kernel, not a peer",
    },
    {
        "name": "outclaw_bus",
        "path": "OutClaw",
        "note": "OutClaw PII-redacting adapter — bridges via the kernel only",
    },
    {
        "name": "whorl_bus_adapter",
        "path": "Whorl/whorl/bus_adapter.py",
        "note": "already an adapter by name — keep it below the kernel",
    },
)


def resolve_kernel_path(
    framework_root: Path | None = None, override: str | Path | None = None
) -> Path | None:
    """Locate the canonical GossipBus file, or return None (graceful).

    Order: explicit override > $CORE_FRAMEWORK_KERNEL_BUS > sibling scan of
    ``<repo-parent>/RootBase/gossip_bus.py``. Returning None is NOT an error —
    this checkout may simply not carry the home workspace.
    """
    candidate = override or os.environ.get(KERNEL_ENV_VAR)
    if candidate:
        path = Path(candidate)
        return path if path.exists() else None

    root = Path(framework_root) if framework_root else FRAMEWORK_ROOT
    kernel = root.parent / "RootBase" / "gossip_bus.py"
    return kernel if kernel.exists() else None


def bus_registry(framework_root: Path | None = None) -> list[dict]:
    """Full bus registry: one kernel, everything else a demoted adapter.

    Each entry reports ``present`` truthfully so the report never lies about
    which trees are actually on this machine.
    """
    root = Path(framework_root) if framework_root else FRAMEWORK_ROOT
    kernel_path = resolve_kernel_path(framework_root=root)

    registry = [
        {
            "name": CANONICAL_KERNEL,
            "role": "kernel",
            "path": str(kernel_path) if kernel_path else "RootBase/gossip_bus.py",
            "present": kernel_path is not None,
            "note": "THE canonical kernel bus — all traffic routes through it",
        }
    ]
    for adapter in ADAPTER_CATALOG:
        adapter_path = root.parent / adapter["path"]
        registry.append(
            {
                "name": adapter["name"],
                "role": "adapter",
                "path": str(adapter_path),
                "present": adapter_path.exists(),
                "note": adapter["note"],
            }
        )
    return registry


def kernel_health(framework_root: Path | None = None) -> dict:
    """Summary verdict for preflight/status surfaces."""
    registry = bus_registry(framework_root)
    kernel = next(e for e in registry if e["role"] == "kernel")
    adapters = [e for e in registry if e["role"] == "adapter"]
    return {
        "kernel": CANONICAL_KERNEL,
        "kernel_present": kernel["present"],
        "kernel_path": kernel["path"],
        "adapters_declared": len(adapters),
        "adapters_present": sum(1 for a in adapters if a["present"]),
        "lock_in_declared": True,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(kernel_health(), indent=2))
