"""Integration tests: MOLT proposal compilation crosses into Whorl execution."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_WHORL_TMP = tempfile.TemporaryDirectory(prefix="molt-whorl-int-")
os.environ.setdefault("WHORL_HOME", os.path.join(_WHORL_TMP.name, ".whorl"))

_WHORL_DIR = Path(__file__).resolve().parents[1] / "Whorl"
if str(_WHORL_DIR) not in sys.path:
    sys.path.insert(0, str(_WHORL_DIR))


class TestMOLTToWhorlIntegration(unittest.TestCase):
    """End-to-end: MOLT compiles a proposal, Whorl executes it, audit trail verified."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)

        from whorl.runtime import (
            HostProfile,
            AgentIntent,
            ProposalCompiler,
            ExecutionAdapter,
            ApprovalLease,
            Effect,
            Decision,
        )
        self.HostProfile = HostProfile
        self.AgentIntent = AgentIntent
        self.ProposalCompiler = ProposalCompiler
        self.ExecutionAdapter = ExecutionAdapter
        self.ApprovalLease = ApprovalLease
        self.Effect = Effect
        self.Decision = Decision

        self.host = HostProfile(
            host_id="integration-test",
            platform="linux",
            workspace_root=str(self.root),
            capabilities=frozenset({"read", "write", "exec", "network"}),
            allowed_network_hosts=frozenset({"example.test"}),
        )

        self.intent = AgentIntent(
            objective="integration test",
            allowed_roots=("src",),
            allowed_capabilities=frozenset({"read", "write", "exec", "network"}),
            require_human_approval=True,
        )

        self.compiler = ProposalCompiler()

    def test_molt_observation_produces_valid_proposal(self):
        """MOLT IterationObservationEngine compiles a real proposal."""
        from whorl.runtime import IterationObservationEngine

        engine = IterationObservationEngine(self.compiler)
        observation = engine.observe(
            {
                "proposal_id": "p1",
                "agent_id": "molt-agent",
                "host_id": self.host.host_id,
                "steps": [{"step_id": "s1", "effect": "read", "target": "src/app.py"}],
            },
            self.host,
            self.intent,
        )

        self.assertEqual(observation["status"], "proposal_only")
        self.assertFalse(observation["actionable"])
        self.assertIn("proposal", observation)
        proposal = observation["proposal"]
        self.assertEqual(proposal["decision"], "allow")
        self.assertFalse(proposal["approval_required"])

    def test_proposal_survives_round_trip(self):
        """CompiledProposal.from_dict() round-trips with digest intact."""
        from whorl.runtime import CompiledProposal

        original = self.compiler.compile(
            {
                "proposal_id": "p2",
                "agent_id": "molt-agent",
                "host_id": self.host.host_id,
                "steps": [{"step_id": "s1", "effect": "read", "target": "src/app.py"}],
            },
            self.host,
            self.intent,
        )

        data = original.to_dict()
        recovered = CompiledProposal.from_dict(data)

        self.assertEqual(recovered.proposal_id, original.proposal_id)
        self.assertEqual(recovered.digest, original.digest)
        self.assertEqual(len(recovered.steps), len(original.steps))
        self.assertEqual(recovered.decision, original.decision)

    def test_whorl_executes_molt_proposal(self):
        """Full crossing: MOLT compile -> serialize -> Whorl deserialize -> execute."""
        from whorl.runtime import (
            CompiledProposal,
            IterationObservationEngine,
            ExecutionAdapter,
        )

        engine = IterationObservationEngine(self.compiler)
        observation = engine.observe(
            {
                "proposal_id": "p3",
                "agent_id": "molt-agent",
                "host_id": self.host.host_id,
                "steps": [{"step_id": "s1", "effect": "read", "target": "src/app.py"}],
            },
            self.host,
            self.intent,
        )

        proposal = CompiledProposal.from_dict(observation["proposal"])

        receipts = self.root / "receipts.jsonl"
        adapter = ExecutionAdapter(
            runner=lambda step: f"read {step.target}",
            receipt_path=receipts,
        )
        receipt = adapter.submit(proposal, host=self.host, intent=self.intent)

        self.assertEqual(receipt.status, "completed")
        self.assertEqual(receipt.executed_step_ids, ("s1",))
        self.assertIn("read src/app.py", receipt.output)

    def test_f2_contract_at_whorl_boundary(self):
        """F2: forged digest is rejected at Whorl ExecutionAdapter boundary."""
        from whorl.runtime import (
            CompiledProposal,
            ExecutionAdapter,
        )

        proposal = self.compiler.compile(
            {
                "proposal_id": "p4",
                "agent_id": "molt-agent",
                "host_id": self.host.host_id,
                "steps": [
                    {
                        "step_id": "s1",
                        "effect": "exec",
                        "target": "etc",
                        "command": ["id"],
                    }
                ],
            },
            self.host,
            self.intent,
        )

        forged = CompiledProposal(
            proposal_id=proposal.proposal_id,
            agent_id=proposal.agent_id,
            host_id=proposal.host_id,
            intent=proposal.intent,
            steps=proposal.steps,
            decision=self.Decision.ALLOW,
            approval_required=False,
            findings=(),
            digest="0" * 64,
            source=proposal.source,
        )

        receipts = self.root / "receipts.jsonl"
        adapter = ExecutionAdapter(
            runner=lambda step: "never",
            receipt_path=receipts,
        )
        receipt = adapter.submit(forged, host=self.host, intent=self.intent)

        self.assertEqual(receipt.status, "rejected")
        self.assertIn("digest mismatch", receipt.finding)


if __name__ == "__main__":
    unittest.main()
