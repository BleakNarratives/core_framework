#!/usr/bin/env python3

# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: thoth
# DEPS: agent_bus,datetime,importlib,os,signal,subprocess,sys,threading,time
# ROLE: swarm_cli.py — Unified swarm orchestrator CLI.
# AUTHOR: Bleak
# SESSION: 2026-09-11
# TIER: 3
# [/DNA_TAG]

"""
swarm_cli.py — Unified swarm orchestrator CLI.

One entry point for the entire agent ecosystem. Launches and monitors
multiple agents as parallel processes. Self-healing, bus-observable,
with dead-letter replay and graceful shutdown.

Force multipliers:
  1. Self-healing       — auto-restart on crash, exponential backoff on loops
  2. Heartbeat watch    — each agent emits heartbeats; supervisor detects hangs
  3. Shared intelligence — MotherBrain decisions propagate to ALL agents via bus
  4. Dead-letter replay  — re-inject failed deliveries for another attempt
  5. Self-observing      — emits swarm.runner events so the system monitors itself
  6. Graceful shutdown   — SIGTERM propagates to children; agents flush state

Agent registry supports two types:
  - Python agents: launched via self-invocation (python3 swarm_cli.py --agent <name>)
  - External CLI agents: launched via subprocess with a "cmd" key
    (for future JS/CLI tools to be absorbed into the unified interface)

Usage:
    python3 swarm_cli.py                   # run the full swarm
    python3 swarm_cli.py --agent <name>     # run a single agent loop (internal)
    python3 swarm_cli.py --status           # print bus status + exit
    python3 swarm_cli.py --replay-dlq        # replay dead-lettered events
    python3 swarm_cli.py --list              # list registered agents
"""

import os
import sys
import time
import signal
import subprocess
import threading
import importlib
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.abspath(__file__)
sys.path.insert(0, SCRIPT_DIR)
import agent_bus  # noqa: E402

# ============================================================
#  Agent registry
# ============================================================
#
# Python agents use "module" + "target" (Class.method or instance.method).
# The supervisor launches them via: python3 swarm_cli.py --agent <name>
#
# External CLI/JS agents use "cmd" instead. Example:
#   "some_js_tool": {
#       "cmd": ["node", "/path/to/index.js"],
#       "interval": 10,   # only used for heartbeat grace, not tick rate
#   },
# External agents don't emit heartbeats (they don't know about the bus),
# so crash detection (poll()) still works but heartbeat monitoring is skipped.

AGENTS = {
    "motherbrain": {
        "module": "motherbrain",
        "target": "MotherBrain.tick",
        "interval": 5,
    },
    "thoth": {
        "module": "thoth_core",
        "target": "ThothCore.act_on_decisions",
        "interval": 3,
    },
    "courier": {
        "module": "agent_bus",
        "target": "courier.process",
        "interval": 2,
    },
}

# --- Force multiplier settings ---
HEARTBEAT_GRACE = 60      # seconds after start before heartbeat checks kick in
HEARTBEAT_TIMEOUT = 45    # seconds without heartbeat = agent is hung
BACKOFF_CAP = 30          # max backoff between restarts
MONITOR_INTERVAL = 10     # seconds between supervisor checks


# ============================================================
#  Agent tick loop (runs when invoked with --agent <name>)
# ============================================================

def run_agent_loop(name):
    """Run a single agent's tick loop. Emits heartbeats. Handles SIGTERM."""
    spec = AGENTS[name]
    module_name = spec["module"]
    target = spec["target"]
    interval = spec["interval"]

    stop = threading.Event()

    def _shutdown(signum, frame):
        stop.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # --- resolve the tick callable ---
    try:
        mod = importlib.import_module(module_name)
        if "." in target:
            obj_name, method_name = target.split(".", 1)
            obj = getattr(mod, obj_name)
            if isinstance(obj, type):
                obj = obj()  # instantiate if it's a class
            tick = getattr(obj, method_name)
        else:
            tick = getattr(mod, target)
    except Exception as e:
        agent_bus.emit_event(
            "agent.heartbeat",
            {"agent": name, "status": "fatal", "error": repr(e)},
            source=name,
            tags=["heartbeat", "fatal"],
        )
        print(f"[{name}] FATAL: import failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[{name}] loop started (interval={interval}s)")

    while not stop.is_set():
        try:
            tick()
            agent_bus.emit_event(
                "agent.heartbeat",
                {"agent": name, "status": "ok"},
                source=name,
                tags=["heartbeat"],
            )
        except Exception as e:
            agent_bus.emit_event(
                "agent.heartbeat",
                {"agent": name, "status": "error", "error": repr(e)},
                source=name,
                tags=["heartbeat", "error"],
            )
            print(f"[{name}] tick error: {e}", file=sys.stderr)
        stop.wait(timeout=interval)

    print(f"[{name}] loop stopped.")


# ============================================================
#  Swarm supervisor
# ============================================================

class SwarmSupervisor:
    """Launches, monitors, and restarts agent processes."""

    def __init__(self):
        self.procs = {}        # name -> Popen
        self.start_times = {}  # name -> time.time()
        self.backoff = {}      # name -> current backoff seconds
        self.running = True

    # ---- launch commands ----

    def _cmd_for(self, name):
        """Build the command to launch an agent as a subprocess."""
        spec = AGENTS[name]
        if "cmd" in spec:
            # External CLI agent (JS, shell, etc.)
            return spec["cmd"]
        # Python agent — self-invoke
        return [sys.executable, SCRIPT_PATH, "--agent", name]

    def start_agent(self, name):
        cmd = self._cmd_for(name)
        proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
        self.procs[name] = proc
        self.start_times[name] = time.time()
        self.backoff[name] = 1
        agent_bus.emit_event(
            "swarm.runner",
            {"action": "start", "agent": name, "pid": proc.pid},
            source="swarm_cli",
            tags=["supervisor"],
        )
        print(f"[supervisor] started {name} (pid={proc.pid})")

    def stop_agent(self, name, reason="shutdown"):
        proc = self.procs.get(name)
        if not proc or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print(f"[supervisor] {name} didn't exit, killing...")
            proc.kill()
            proc.wait()
        agent_bus.emit_event(
            "swarm.runner",
            {"action": "stop", "agent": name, "reason": reason},
            source="swarm_cli",
            tags=["supervisor"],
        )

    def restart_agent(self, name, reason="crash"):
        wait = self.backoff.get(name, 1)
        print(f"[supervisor] {name} restart in {wait}s (reason: {reason})")
        agent_bus.emit_event(
            "swarm.runner",
            {"action": "restart", "agent": name, "reason": reason, "backoff_s": wait},
            source="swarm_cli",
            tags=["supervisor", "restart"],
        )
        time.sleep(wait)
        if not self.running:
            return  # shutting down, don't restart
        self.backoff[name] = min(wait * 2, BACKOFF_CAP)
        self.start_agent(name)

    # ---- heartbeat monitoring ----

    def _is_external(self, name):
        return "cmd" in AGENTS[name]

    def _heartbeat_stale(self, name):
        """True if agent has been running past grace period with no recent heartbeat."""
        if self._is_external(name):
            return False  # external agents don't emit heartbeats
        age = time.time() - self.start_times.get(name, time.time())
        if age < HEARTBEAT_GRACE:
            return False  # still in grace period
        head = agent_bus.current_line_count()
        events, _ = agent_bus.read_events(offset=max(0, head - 100), limit=100)
        now = datetime.now(timezone.utc)
        for event in reversed(events):
            if (event.get("event_type") == "agent.heartbeat"
                    and event.get("source") == name):
                try:
                    ts = datetime.fromisoformat(
                        event.get("created_at", "").replace("Z", "+00:00")
                    )
                    return (now - ts).total_seconds() > HEARTBEAT_TIMEOUT
                except (ValueError, TypeError):
                    return False
        return False  # no heartbeat found — don't kill (could be brand new)

    # ---- dashboard ----

    def _print_dashboard(self):
        status = {}
        for name, proc in self.procs.items():
            if proc.poll() is None:
                status[name] = "running"
            else:
                status[name] = f"stopped(rc={proc.returncode})"
        print(f"[supervisor] {status}")

    # ---- main monitor loop ----

    def monitor(self):
        while self.running:
            for name, proc in list(self.procs.items()):
                if proc.poll() is not None:
                    # Crashed
                    rc = proc.returncode
                    print(f"[supervisor] {name} exited (rc={rc})")
                    self.restart_agent(name, reason=f"exit_{rc}")
                elif self._heartbeat_stale(name):
                    # Hung — still running but not heartbeating
                    print(f"[supervisor] {name} heartbeat stale, restarting...")
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    self.restart_agent(name, reason="heartbeat_timeout")
            self._print_dashboard()
            time.sleep(MONITOR_INTERVAL)

    # ---- lifecycle ----

    def start(self):
        print("[supervisor] launching swarm...")
        for name in AGENTS:
            self.start_agent(name)
        agent_bus.emit_event(
            "swarm.runner",
            {"action": "swarm_start", "agents": list(AGENTS.keys())},
            source="swarm_cli",
            tags=["supervisor"],
        )
        try:
            self.monitor()
        finally:
            self.shutdown()

    def shutdown(self):
        self.running = False
        print("[supervisor] shutting down all agents...")
        for name in list(self.procs):
            self.stop_agent(name, reason="graceful_shutdown")
        agent_bus.emit_event(
            "swarm.runner",
            {"action": "swarm_stop"},
            source="swarm_cli",
            tags=["supervisor"],
        )
        print("[supervisor] all agents stopped.")

    # ---- utility commands ----

    def replay_dead_letters(self, limit=50):
        """Force multiplier: re-inject dead-lettered events onto the bus."""
        entries, _ = agent_bus.read_dead_letters(limit=limit)
        replayed = 0
        for entry in entries:
            event = entry.get("event")
            if not event:
                continue
            agent_bus.emit_event(
                event.get("event_type", "replay"),
                event.get("payload", {}),
                source="dlq_replay",
                origin=event.get("source", ""),
                channel=event.get("channel", "local"),
                tags=["replay"] + event.get("tags", []),
            )
            replayed += 1
        print(f"[supervisor] replayed {replayed} dead-lettered events.")
        agent_bus.emit_event(
            "swarm.runner",
            {"action": "replay_dlq", "replayed": replayed},
            source="swarm_cli",
            tags=["supervisor", "replay"],
        )
        return replayed

    def status(self):
        """Print bus status and recent events."""
        head = agent_bus.current_line_count()
        events, _ = agent_bus.read_events(offset=max(0, head - 20), limit=20)
        print(f"=== Swarm Bus Status ({head} total events) ===")
        by_type = {}
        for e in events:
            t = e.get("event_type", "?")
            by_type[t] = by_type.get(t, 0) + 1
        for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"  {t}: {c}")
        dlq, _ = agent_bus.read_dead_letters(limit=10)
        print(f"  dead_letters: {len(dlq)}")
        print(f"  registered agents: {list(AGENTS.keys())}")

    @staticmethod
    def list_agents():
        print("Registered agents:")
        for name, spec in AGENTS.items():
            if "cmd" in spec:
                print(f"  {name}: cmd={spec['cmd']} (external)")
            else:
                print(f"  {name}: {spec['module']}.{spec['target']} (every {spec['interval']}s)")


# ============================================================
#  Entry point
# ============================================================

if __name__ == "__main__":
    if "--agent" in sys.argv:
        # Internal: run a single agent loop (launched by the supervisor)
        idx = sys.argv.index("--agent")
        name = sys.argv[idx + 1]
        run_agent_loop(name)
    elif "--status" in sys.argv:
        SwarmSupervisor().status()
    elif "--replay-dlq" in sys.argv:
        SwarmSupervisor().replay_dead_letters()
    elif "--list" in sys.argv:
        SwarmSupervisor.list_agents()
    else:
        # Run the full swarm
        runner = SwarmSupervisor()

        def _sig(signum, frame):
            print(f"\n[supervisor] signal {signum} received.")
            runner.running = False

        signal.signal(signal.SIGTERM, _sig)
        signal.signal(signal.SIGINT, _sig)
        runner.start()
