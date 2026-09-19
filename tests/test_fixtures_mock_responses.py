"""Tests for the shared mock-response fixtures.

`tests/fixtures/mock_responses.py` existed with no consumer: nothing in `tests/`
imported it, so its payloads and patch helpers were unverified code that future
offline tests were meant to build on. This file is that consumer, and it checks the
two things a fixture library can get wrong quietly:

1. **The payloads.** A typo in a mocked error body does not fail loudly — it just
   makes the next test assert against a fiction. Every named payload is therefore
   checked for the shape the producers claim: provider errors carry an `error`
   object with a message, and the valid drafts and pings carry the OpenAI-style
   `choices[0].message.content` shape that `inference_bridge.py` parses.
2. **The patch helpers.** A patcher that leaks, over-serves, or fails to restore
   turns a passing suite into a lying one, so each one is asserted to serve its
   responses in order, to refuse to over-serve, and to restore the original on exit.

The Groq rate-limit pair gets its own test because the distinction is load-bearing:
one 429 is retryable and the other is not.
"""
from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
import unittest
from unittest import mock

from tests.fixtures import mock_responses as mr


class PayloadShapeTest(unittest.TestCase):
    """The payloads must match what the real providers return."""

    def test_every_named_error_payload_is_an_error_object(self):
        bundles = {"groq": mr.GROQ_ERRORS, "openrouter": mr.OPENROUTER_ERRORS}
        for provider, bundle in bundles.items():
            self.assertTrue(bundle, f"{provider} has no error payloads")
            for name, payload in bundle.items():
                with self.subTest(provider=provider, payload=name):
                    self.assertIsInstance(payload, dict)
                    self.assertIn("error", payload)
                    self.assertIsInstance(payload["error"], dict)
                    message = payload["error"].get("message")
                    self.assertIsInstance(message, str)
                    self.assertTrue(message.strip(), "empty error message")

    def test_valid_drafts_carry_the_choices_shape(self):
        for name, payload in mr.VALID_DRAFTS.items():
            with self.subTest(draft=name):
                content = payload["choices"][0]["message"]["content"]
                self.assertIsInstance(content, str)
                self.assertTrue(content.strip())

    def test_ping_responses_carry_the_same_shape(self):
        for name, payload in mr.PING_RESPONSES.items():
            with self.subTest(ping=name):
                self.assertIsInstance(
                    payload["choices"][0]["message"]["content"], str
                )

    def test_the_retryable_and_non_retryable_429s_are_distinguishable(self):
        # The retry loop keys off exactly this difference, so a fixture that made
        # them identical would quietly turn "stop, billing" into "retry forever".
        retryable = mr.GROQ_429_TPM["error"]
        exhausted = mr.GROQ_429_QUOTA_EXHAUSTED["error"]
        self.assertNotEqual(retryable["code"], exhausted["code"])
        self.assertEqual(exhausted["code"], "insufficient_quota")
        self.assertIn("credit", exhausted["message"].lower())
        self.assertIn("try again in", retryable["message"].lower())

    def test_raw_bodies_are_what_their_names_claim(self):
        self.assertEqual(mr.EMPTY_BODY, b"")
        self.assertEqual(json.loads(mr.EMPTY_JSON_OBJECT), {})
        # These two are the interesting ones: one is not JSON at all, the other is
        # valid JSON that simply has no `choices`.
        with self.assertRaises(json.JSONDecodeError):
            json.loads(mr.INVALID_JSON_BODY)
        self.assertNotIn("choices", json.loads(mr.MISSING_CHOICES_BODY))


class HelperBehaviourTest(unittest.TestCase):
    """The helpers must serve, refuse to over-serve, and restore."""

    def test_make_mock_response_serialises_and_supports_the_with_statement(self):
        payload = mr.VALID_DRAFTS["groq"]
        response = mr.make_mock_response(200, payload)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read()), payload)
        with response as entered:
            self.assertIs(entered, response)

    def test_make_mock_response_passes_bytes_through_unchanged(self):
        response = mr.make_mock_response(200, mr.INVALID_JSON_BODY)
        self.assertEqual(response.read(), mr.INVALID_JSON_BODY)

    def test_make_http_error_carries_status_and_body(self):
        error = mr.make_http_error(429, mr.GROQ_429_TPM)
        self.assertIsInstance(error, urllib.error.HTTPError)
        self.assertEqual(error.code, 429)
        self.assertEqual(json.loads(error.read()), mr.GROQ_429_TPM)

    def test_urlopen_sequence_serves_in_order_and_records_every_call(self):
        payloads = [mr.VALID_DRAFTS["groq"], mr.VALID_DRAFTS["openrouter"]]
        responses = [mr.make_mock_response(200, p) for p in payloads]
        with mr.UrlopenSequence(responses) as seq:
            bodies = [urllib.request.urlopen("https://example.test").read() for _ in payloads]
        self.assertEqual([json.loads(b) for b in bodies], payloads)
        self.assertEqual(len(seq.calls), 2)

    def test_urlopen_sequence_raises_a_queued_exception(self):
        with mr.UrlopenSequence([mr.make_http_error(503, mr.UPSTREAM_503)]):
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen("https://example.test")

    def test_urlopen_sequence_refuses_to_over_serve(self):
        # Silently re-serving the last response would hide an extra network call.
        with mr.UrlopenSequence([mr.make_mock_response(200, mr.GROQ_PING)]):
            urllib.request.urlopen("https://example.test")
            with self.assertRaises(RuntimeError):
                urllib.request.urlopen("https://example.test")

    def test_urlopen_sequence_restores_the_original_on_exit(self):
        original = urllib.request.urlopen
        with mr.patch_urlopen([mr.make_mock_response(200, mr.GROQ_PING)]) as seq:
            urllib.request.urlopen("https://example.test")
            self.assertIsNot(urllib.request.urlopen, original)
        self.assertIs(urllib.request.urlopen, original)
        self.assertEqual(len(seq.calls), 1)

    def test_urlopen_sequence_can_retarget_a_namespace(self):
        # The `target` parameter exists so a module that imported urlopen by name can
        # be patched; asserted here so it cannot silently become a no-op.
        with mock.patch.object(_namespace, "urlopen", side_effect=AssertionError("unpatched")):
            with mr.UrlopenSequence(
                [mr.make_mock_response(200, mr.GROQ_PING)],
                target=f"{__name__}._namespace.urlopen",
            ):
                _namespace.urlopen("https://example.test")

    def test_subprocess_sequence_returns_the_queued_completed_process(self):
        envelope = mr.make_bin_ai_envelope(ok=True, reply="draft text")
        queued = mr.make_completed_process(returncode=0, stdout=json.dumps(envelope))
        with mr.SubprocessRunSequence([queued]) as seq:
            result = subprocess.run(["bin/ai", "--json", "prompt"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), envelope)
        self.assertEqual(len(seq.calls), 1)

    def test_subprocess_sequence_raises_a_queued_exception(self):
        with mr.SubprocessRunSequence([FileNotFoundError("bin/ai not found")]):
            with self.assertRaises(FileNotFoundError):
                subprocess.run(["bin/ai"])

    def test_subprocess_sequence_refuses_to_over_serve(self):
        with mr.SubprocessRunSequence([mr.make_completed_process()]):
            subprocess.run(["bin/ai"])
            with self.assertRaises(RuntimeError):
                subprocess.run(["bin/ai"])

    def test_subprocess_sequence_restores_the_original_on_exit(self):
        original = subprocess.run
        with mr.patch_subprocess_run([mr.make_completed_process()]):
            self.assertIsNot(subprocess.run, original)
        self.assertIs(subprocess.run, original)


class EnvelopeContractTest(unittest.TestCase):
    """`bin/ai --json` output shape, which outreach_agent parses."""

    def test_success_envelope_carries_a_reply_and_no_error(self):
        envelope = mr.make_bin_ai_envelope(ok=True, reply="hello")
        self.assertEqual(envelope["ok"], True)
        self.assertEqual(envelope["reply"], "hello")
        self.assertNotIn("error", envelope)

    def test_failure_envelope_carries_an_error_and_no_reply(self):
        envelope = mr.make_bin_ai_envelope(ok=False, error="gateway 429")
        self.assertEqual(envelope["ok"], False)
        self.assertEqual(envelope["error"], "gateway 429")
        self.assertNotIn("reply", envelope)

    def test_model_is_echoed_only_when_named(self):
        self.assertNotIn("model", mr.make_bin_ai_envelope(reply="x"))
        self.assertEqual(mr.make_bin_ai_envelope(reply="x", model="m")["model"], "m")


class _Namespace:
    """Stand-in for a module namespace, used to test `UrlopenSequence.target`."""

    @staticmethod
    def urlopen(*args, **kwargs):  # pragma: no cover - replaced by the test
        raise AssertionError("urlopen should have been patched")


_namespace = _Namespace()


if __name__ == "__main__":
    unittest.main()
