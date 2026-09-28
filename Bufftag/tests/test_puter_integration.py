"""Offline contract tests for Puter's Bufftag and command-safety wiring."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
PUTER_ROOT = ROOT / "RootBase" / "puter"
if str(PUTER_ROOT) not in sys.path:
    sys.path.insert(0, str(PUTER_ROOT))

import ai_router  # noqa: E402
import concierge  # noqa: E402
import valet  # noqa: E402


class FakeState:
    def __init__(self):
        self.messages = []

    def save_message(self, session, role, content, model=None):
        self.messages.append((session, role, content, model))


class FakeKG:
    def get_context(self, task, max_chars=2000):
        return "untrusted retrieved context"


class FakePersona:
    def get_system_prompt(self, mode):
        return "test system prompt"


class FakeAI:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return {
            "success": True,
            "content": self.content,
            "provider": "fixture",
            "model": "offline",
        }


class AdvisorFixture:
    def __init__(self):
        self.assisted = None
        self.corrected = None

    def status(self):
        return {
            "workspace": "/fixture",
            "atlas": "/fixture/moves.jsonl",
            "external_anchor": "/separate/head.json",
            "lane": "lane-1",
            "owner": "owner-1",
            "lease_held": False,
            "report": {
                "root": "/fixture",
                "files_scanned": 1,
                "receipt_count": 1,
                "ok": True,
                "findings": [],
            },
        }

    def assist(self, ai, request):
        self.assisted = request
        return {
            "success": True,
            "advisory_only": True,
            "content": "advisory",
            "provider": "fixture",
            "model": "offline",
            "evidence_sha256": "a" * 64,
        }

    def correct_course(self, ai, request):
        self.corrected = request
        return {
            "success": True,
            "advisory_only": True,
            "content": "correction",
            "provider": "fixture",
            "model": "offline",
            "evidence_sha256": "b" * 64,
        }


class PuterValetTests(unittest.TestCase):
    def test_model_generated_commands_are_returned_but_never_executed(self):
        ai = FakeAI(
            json.dumps(
                {
                    "commands": ["rm -rf /", "echo unsafe"],
                    "description": "unsafe fixture",
                    "risks": ["destructive"],
                    "rollback": ["none"],
                }
            )
        )
        service = valet.Valet(FakeState(), FakeKG(), ai, FakePersona())
        with mock.patch.object(valet.subprocess, "run") as subprocess_run:
            result = service.execute("do something", "session-1")
        subprocess_run.assert_not_called()
        self.assertEqual(result["type"], "proposal")
        self.assertTrue(result["advisory_only"])
        self.assertEqual(result["executed_actions"], [])
        self.assertIn("NOT EXECUTED", result["content"])
        self.assertIn("rm -rf /", result["content"])

    def test_provider_status_never_previews_credentials(self):
        secret = "SECRET-PREFIX-MUST-NOT-LEAK"
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": secret}, clear=False):
            router = ai_router.AIRouter()
            rendered = json.dumps(router.get_available_providers())
        self.assertNotIn(secret, rendered)
        self.assertNotIn("SECRET-PRE", rendered)
        groq = next(item for item in router.get_available_providers() if item["name"] == "groq")
        self.assertEqual(groq["key"], "SET")


class ConciergeBufftagTests(unittest.TestCase):
    def setUp(self):
        self.advisor = AdvisorFixture()
        self.service = object.__new__(concierge.Concierge)
        self.service.state = FakeState()
        self.service.kg = FakeKG()
        self.service.ai = FakeAI("unused")
        self.service.persona = FakePersona()
        self.service.bufftag = self.advisor

    def test_assist_and_correct_commands_preserve_request_text(self):
        result = self.service.process("bufftag assist why is this route stale?", "s1")
        self.assertEqual(self.advisor.assisted, "why is this route stale?")
        self.assertTrue(result["advisory_only"])
        result = self.service.process("bufftag correct tighten rollback policy", "s1")
        self.assertEqual(self.advisor.corrected, "tighten rollback policy")
        self.assertTrue(result["advisory_only"])

    def test_status_command_uses_real_adapter_report(self):
        result = self.service.process("bufftag status", "s1")
        self.assertEqual(result["type"], "status")
        self.assertIn("Routes: 1", result["content"])


if __name__ == "__main__":
    unittest.main()
