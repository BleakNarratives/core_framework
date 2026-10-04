#!/usr/bin/env python3
"""
core_framework/tests/test_kernel_bus.py

Tests for the GossipBus kernel lock-in registry. All filesystem effects are
redirected into tmp_path (via framework_root / override parameters), so the
real workspace is never touched and the tests are hermetic.
"""

from __future__ import annotations

import json
from pathlib import Path

from core_framework.shared import kernel_bus as kb

from core_framework.shared.kernel_bus import (
    CANONICAL_KERNEL,
    bus_registry,
    kernel_health,
    resolve_kernel_path,
)


def _fake_workspace(tmp_path: Path, *, with_kernel: bool = False) -> Path:
    """Build a standalone fake workspace: <root>/core_framework + siblings."""
    fw = tmp_path / "core_framework"
    fw.mkdir(exist_ok=True)  # the honest-presence test reuses the same root
    if with_kernel:
        kernel_dir = tmp_path / "RootBase"
        kernel_dir.mkdir()
        (kernel_dir / "gossip_bus.py").write_text("# canonical kernel stub\n")
    return fw


def test_registry_declares_exactly_one_kernel(tmp_path):
    fw = _fake_workspace(tmp_path)
    registry = bus_registry(framework_root=fw)

    kernels = [e for e in registry if e["role"] == "kernel"]
    adapters = [e for e in registry if e["role"] == "adapter"]
    assert len(kernels) == 1
    assert kernels[0]["name"] == CANONICAL_KERNEL
    assert len(adapters) == 4  # integration_bus, event_bus, outclaw_bus, whorl
    assert all(a["role"] == "adapter" for a in adapters)
    # Every adapter carries its canonical path + demotion note.
    assert all(a["note"] for a in adapters)


def test_registry_reports_presence_honestly(tmp_path):
    # Nothing on disk -> nothing claimed present (no lies, even for the kernel).
    fw = _fake_workspace(tmp_path, with_kernel=False)
    registry = bus_registry(framework_root=fw)
    assert not any(e["present"] for e in registry)

    # Kernel tree present -> kernel flips to present, adapters stay honest.
    fw = _fake_workspace(tmp_path, with_kernel=True)
    registry = bus_registry(framework_root=fw)
    kernel = next(e for e in registry if e["role"] == "kernel")
    assert kernel["present"] is True
    assert kernel["path"].endswith("RootBase/gossip_bus.py")


def test_resolve_kernel_scans_sibling_rootbase(tmp_path):
    fw = _fake_workspace(tmp_path, with_kernel=True)
    resolved = resolve_kernel_path(framework_root=fw)
    assert resolved == tmp_path / "RootBase" / "gossip_bus.py"


def test_resolve_kernel_env_override_wins(tmp_path):
    fw = _fake_workspace(tmp_path, with_kernel=True)
    custom = tmp_path / "elsewhere" / "gossip_bus.py"
    custom.parent.mkdir()
    custom.write_text("# overridden kernel location\n")

    resolved = resolve_kernel_path(framework_root=fw, override=custom)
    assert resolved == custom

    # An override that does not exist degrades to None, never to a guess.
    assert resolve_kernel_path(framework_root=fw, override=tmp_path / "nope.py") is None


def test_resolve_kernel_is_graceful_when_absent(tmp_path):
    fw = _fake_workspace(tmp_path, with_kernel=False)
    assert resolve_kernel_path(framework_root=fw) is None
    health = kernel_health(framework_root=fw)
    assert health["kernel_present"] is False
    assert health["lock_in_declared"] is True  # the decision stands regardless


def test_kernel_health_summary_shape(tmp_path):
    fw = _fake_workspace(tmp_path, with_kernel=True)
    health = kernel_health(framework_root=fw)
    assert health["kernel"] == CANONICAL_KERNEL
    assert health["kernel_present"] is True
    assert health["adapters_declared"] == 4
    assert health["adapters_present"] == 0
