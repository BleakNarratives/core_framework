# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: thoth
# ROLE: Undocumented module
# TIER: Scout (6)
# AUTHOR: BleakNarratives
# SESSION: 2026-08-22 ShipWreckD OS Builder — auto-tagged by DNA Sweeper
# [/DNA_TAG]

import subprocess
import json
import requests
import os
import shutil
import sys
from dotenv import load_dotenv
from agent_bus import emit_event, read_events, current_line_count, ensure_bus

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

# Add RootBase paths to sys.path to allow importing from other projects
sys.path.append('/home/bleaknarratives/RootBase/project_bundle_20260513_120226/datacampus')

try:
    from datacampus import runtime as dc_runtime
except ImportError:
    dc_runtime = None

class PaymentBridge:
    """
    The ModMind Payment Gateway.
    Interfaces with Lightning nodes (Voltage/LNbits) to verify real-time payment state.
    """
    def __init__(self):
        self.api_url = os.getenv("LIGHTNING_API_URL", "http://localhost:8080")
        self.api_key = os.getenv("LIGHTNING_API_KEY", "default_key")

    def check_invoice_status(self, payment_id):
        """
        Polls the Lightning node for the status of a specific invoice.
        Returns: 'PAID', 'PENDING', or 'EXPIRED'
        """
        try:
            response = requests.get(f"{self.api_url}/invoices/{payment_id}", 
                                    headers={"X-Api-Key": self.api_key}, 
                                    timeout=5)
            if response.status_code == 200:
                status = response.json().get("status")
                return status.upper() if status else "ERROR"
            return "ERROR"
        except Exception as e:
            return f"ERROR: {str(e)}"

    def verify_webhook(self, payload):
        payment_id = payload.get("payment_id")
        amount = payload.get("amount")
        return True if payment_id and amount else False

class ZeroClawAdapter:
    """Wraps the ZeroClaw Lab Broker CLI for quick task management."""
    CLI_PATH = "/home/bleaknarratives/RootBase/project_bundle_20260513_120226/project_incubator/zeroclaw_lab_broker"

    @staticmethod
    def _run_cli(args):
        cmd = ["python", "-m", "zeroclaw_lab_broker.cli"] + args
        result = subprocess.run(cmd, cwd=ZeroClawAdapter.CLI_PATH, capture_output=True, text=True)
        if result.returncode != 0:
            return {"error": result.stderr}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout

    def verify_payment(self, payment_id, customer_id, amount_sats):
        return self._run_cli(["verify-payment", "--payment-id", payment_id, "--customer-id", customer_id, "--amount", str(amount_sats)])

    def create_task(self, assignment_id, lab_id, capabilities, risk="low", payment_id=None):
        cap_args = []
        for c in capabilities:
            cap_args.extend(["--capability", c])
        args = ["create-task", "--assignment-id", assignment_id, "--lab-id", lab_id] + cap_args + ["--risk-level", risk]
        if payment_id:
            args.extend(["--payment-id", payment_id])
        return self._run_cli(args)

    def get_status(self):
        return self._run_cli(["status"])

    def list_open_tasks(self):
        return self._run_cli(["open-tasks"])

class OpenClawAdapter:
    """Wraps the OpenClaw (npm) CLI. Mirrors ZeroClawAdapter's contract so
    Thoth routes OpenClaw traffic through the same path as ZeroClaw.

    NOTE: the `openclaw` binary is NOT installed on this device (checked
    2026-09-07). Activate with `npm install -g openclaw`. CLI arg flags mirror
    ZeroClaw's surface and may need aligning to openclaw's real flags once
    the binary is present.
    """
    CLI = os.getenv("OPENCLAW_CLI", "openclaw")

    @staticmethod
    def _run_cli(args):
        if not shutil.which(OpenClawAdapter.CLI):
            return {"error": "openclaw CLI not installed (run `npm install -g openclaw`)"}
        cmd = [OpenClawAdapter.CLI] + args
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {"error": result.stderr}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout

    def verify_payment(self, payment_id, customer_id, amount_sats):
        return self._run_cli(["verify-payment", "--payment-id", payment_id, "--customer-id", customer_id, "--amount", str(amount_sats)])

    def create_task(self, assignment_id, lab_id, capabilities, risk="low", payment_id=None):
        cap_args = []
        for c in capabilities:
            cap_args.extend(["--capability", c])
        args = ["create-task", "--assignment-id", assignment_id, "--lab-id", lab_id] + cap_args + ["--risk-level", risk]
        if payment_id:
            args.extend(["--payment-id", payment_id])
        return self._run_cli(args)

    def get_status(self):
        return self._run_cli(["status"])

    def list_open_tasks(self):
        return self._run_cli(["open-tasks"])

class LoughAdapter:
    """Interfaces with the Lough field_server for event emitting and polling."""
    def __init__(self):
        self.base_url = os.getenv("LOUGH_BASE_URL", "http://localhost:7070")

    def emit(self, event_type, payload, source="thoth", location="orchestrator"):
        data = {"event_type": event_type, "payload": payload, "source": source, "location": location}
        emit_event(event_type, payload, source=source, origin=location)
        try:
            response = requests.post(f"{self.base_url}/emit", json=data, timeout=5)
            return response.json()
        except Exception as e:
            return {"error": str(e), "transport": "local_event_bus"}

    def poll(self, limit=10):
        try:
            response = requests.get(f"{self.base_url}/poll", params={"limit": limit}, timeout=5)
            return response.json()
        except Exception as e:
            events, _ = read_events(max(0, current_line_count() - limit), limit=limit)
            return {"error": str(e), "transport": "local_event_bus", "events": events}

class DataCampusAdapter:
    """Wraps DataCampus runtime for curriculum and student management."""
    def __init__(self):
        if dc_runtime is None:
            print("[WARN] DataCampus runtime not found.")

    def create_assignment(self, cohort_id, lab_id, source="Artificial-Criminal"):
        if not dc_runtime: return {"error": "DataCampus runtime unavailable"}
        return dc_runtime.create_assignment(cohort_id, lab_id, source_project=source)

    def create_student(self, name, metadata=None):
        if not dc_runtime: return {"error": "DataCampus runtime unavailable"}
        return dc_runtime.create_student(name, metadata)

    def import_lab(self, manifest):
        if not dc_runtime: return {"error": "DataCampus runtime unavailable"}
        return dc_runtime.import_lab_manifest(manifest)

payment_bridge = PaymentBridge()
zeroclaw = ZeroClawAdapter()
openclaw = OpenClawAdapter()
lough = LoughAdapter()
datacampus = DataCampusAdapter()
