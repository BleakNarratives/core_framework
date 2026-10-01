"""Focused offline coverage for provider adapters and inference parsing.

All transport and subprocess boundaries are mocked. These tests never use credentials,
network access, or repository state outside the functions under test.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.skill import inference_bridge as bridge
from tools.inference import syntaxbuff


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


class TestSyntaxBuffProviders(unittest.TestCase):
    def test_openrouter_adapter_builds_messages_and_reads_content(self):
        response = {"choices": [{"message": {"content": "router reply"}}]}
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False), \
             patch.object(syntaxbuff.urllib.request, "urlopen",
                          return_value=FakeResponse(json.dumps(response).encode())) as open_url:
            result = syntaxbuff.call_openrouter("hello", "model-x", "system")

        self.assertEqual(result, "router reply")
        request = open_url.call_args.args[0]
        self.assertIn("Bearer test-key", request.headers["Authorization"])
        body = json.loads(request.data)
        self.assertEqual(body["model"], "model-x")
        self.assertEqual(body["messages"][0], {"role": "system", "content": "system"})
        self.assertEqual(body["messages"][1], {"role": "user", "content": "hello"})

    def test_groq_adapter_uses_groq_key_and_supports_no_system(self):
        response = {"choices": [{"message": {"content": "groq reply"}}]}
        with patch.dict(os.environ, {"GROQ_API_KEY": "groq-key"}, clear=False), \
             patch.object(syntaxbuff.urllib.request, "urlopen",
                          return_value=FakeResponse(json.dumps(response).encode())) as open_url:
            result = syntaxbuff.call_groq("hello", "groq-model")

        self.assertEqual(result, "groq reply")
        request = open_url.call_args.args[0]
        self.assertIn("Bearer groq-key", request.headers["Authorization"])
        self.assertEqual(json.loads(request.data)["messages"],
                         [{"role": "user", "content": "hello"}])

    def test_openai_compatible_uses_model_prefix_key(self):
        response = {"choices": [{"message": {"content": "compatible reply"}}]}
        with patch.dict(os.environ, {"COHERE_API_KEY": "cohere-key"}, clear=False), \
             patch.object(syntaxbuff.urllib.request, "urlopen",
                          return_value=FakeResponse(json.dumps(response).encode())) as open_url:
            result = syntaxbuff.call_openai_compatible("hello", "cohere-model", "https://api.example.test/v1")

        self.assertEqual(result, "compatible reply")
        request = open_url.call_args.args[0]
        self.assertIn("Bearer cohere-key", request.headers["Authorization"])

    def test_provider_adapters_fail_before_transport_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(syntaxbuff.urllib.request, "urlopen") as open_url:
            with self.assertRaisesRegex(RuntimeError, "OPENROUTER_API_KEY"):
                syntaxbuff.call_openrouter("hello", "model-x")
            with self.assertRaisesRegex(RuntimeError, "GROQ_API_KEY"):
                syntaxbuff.call_groq("hello", "model-x")
            with self.assertRaisesRegex(RuntimeError, "API key not set"):
                syntaxbuff.call_openai_compatible("hello", "cohere-model", "https://api.example.test/v1")
        open_url.assert_not_called()

    def test_dispatch_routes_through_gateway_with_pinned_provider(self):
        with patch.object(syntaxbuff, "call_gateway", return_value="ok") as call:
            self.assertEqual(syntaxbuff.dispatch("hello", model_key="qwen"), "ok")
        call.assert_called_once_with(
            "hello", model="openrouter::qwen/qwen3-235b-a22b:free", system=None)

    def test_dispatch_sends_auto_for_non_pinnable_models(self):
        with patch.object(syntaxbuff, "call_gateway", return_value="ok") as call:
            syntaxbuff.dispatch("hello", model_key="cohere")
        call.assert_called_once_with("hello", model="auto", system=None)

    def test_call_gateway_uses_local_endpoint_and_parses_response(self):
        response = {"choices": [{"message": {"content": "gw reply"}}]}
        with patch.object(syntaxbuff.urllib.request, "urlopen",
                          return_value=FakeResponse(json.dumps(response).encode())) as open_url:
            result = syntaxbuff.call_gateway("hello", model="auto", system="sys")

        self.assertEqual(result, "gw reply")
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url,
                         syntaxbuff.GATEWAY_BASE.rstrip("/") + "/chat/completions")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "auto")
        self.assertEqual(body["messages"][0], {"role": "system", "content": "sys"})
        self.assertEqual(body["messages"][1], {"role": "user", "content": "hello"})
        self.assertNotIn("Authorization", request.headers)


class TestLeadDirectorySchema(unittest.TestCase):
    def test_outbound_candidates_has_unique_normalized_records(self):
        path = Path("data/leads/outbound_candidates.json")
        self.assertTrue(path.is_file())
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        leads = payload["leads"]
        self.assertTrue(leads)
        self.assertEqual(len({lead["id"] for lead in leads}), len(leads))
        required = {
            "id", "source", "source_section", "author", "title", "url",
            "published", "matched", "employment_type", "contact",
        }
        contact_fields = {
            "emails", "dm_available", "profile_urls", "application_urls",
            "venue_urls",
        }
        for lead in leads:
            self.assertTrue(required <= lead.keys())
            self.assertEqual(set(lead["contact"]), contact_fields)
            self.assertTrue(all("@" in email for email in lead["contact"]["emails"]))


class TestInferenceBridgeParsing(unittest.TestCase):
    def test_sanitize_accepts_fenced_execution_contract(self):
        raw = 'analysis\n```json\n{"persona":"reviewer","status":"APPROVED","code":"NONE","patch":null}\n```'
        result = bridge.sanitize_persona_output(raw, "skill")
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["sanitized_payload"]["persona"], "reviewer")

    def test_sanitize_rejects_missing_contract(self):
        result = bridge.sanitize_persona_output("plain text", "skill")
        self.assertEqual(result["status"], "SCHEMA_ERROR")
        self.assertEqual(result["sanitized_payload"]["code"], "ERR_SCHEMA_VIOLATION")
        self.assertIsNone(result["sanitized_payload"]["patch"])

    def test_generic_openrouter_adapter_parses_response(self):
        response = {"choices": [{"message": {"content": "generic reply"}}]}
        messages = [{"role": "user", "content": "hello"}]
        with patch.object(bridge.urllib.request, "urlopen",
                          return_value=FakeResponse(json.dumps(response).encode())) as open_url:
            result = bridge._call_openrouter_generic(messages, "test-key", model="test-model")

        self.assertEqual(result, "generic reply")
        request = open_url.call_args.args[0]
        self.assertEqual(json.loads(request.data)["model"], "test-model")
        self.assertIn("Bearer test-key", request.headers["Authorization"])

    def test_call_gateway_uses_local_endpoint(self):
        response = {"choices": [{"message": {"content": "gw"}}]}
        with patch.object(bridge.urllib.request, "urlopen",
                          return_value=FakeResponse(json.dumps(response).encode())) as open_url:
            result = bridge._call_gateway([{"role": "user", "content": "hi"}])

        self.assertEqual(result, "gw")
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url,
                         bridge.GATEWAY_BASE.rstrip("/") + "/chat/completions")
        self.assertNotIn("Authorization", request.headers)

    def test_patch_vibe_argv_removes_molt_flags_but_keeps_prompt(self):
        prompt, oomf, scopes = bridge.patch_vibe_argv(
            ["build", "thing", "--oomf", "4", "--elevate", "network", "write"])
        self.assertEqual(prompt, "build thing")
        self.assertEqual(oomf, 4)
        self.assertEqual(scopes, {"network", "write"})


if __name__ == "__main__":
    unittest.main()
