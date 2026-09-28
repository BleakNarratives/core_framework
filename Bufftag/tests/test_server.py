"""Offline contract tests for the local Bufftag HTTP server."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from Bufftag import server


class ServerCase(unittest.TestCase):
    allow_write = False
    signing_env = "BUFFTAG_TEST_KEY"

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.workspace = Path(cls.temp.name)
        cls.workspace.joinpath("sample.py").write_text("print('sample')\n", encoding="utf-8")
        os.environ.pop(cls.signing_env, None)
        cls.server = server.create_server(
            workspace=cls.workspace,
            port=0,
            allow_write=cls.allow_write,
            signing_key_env=cls.signing_env,
        )
        cls.server.RequestHandlerClass.log_message = lambda *args, **kwargs: None
        cls.host, cls.port = cls.server.server_address
        cls.base = f"http://{cls.host}:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        health = cls.request("GET", "/api/health")
        cls.token = health["api_token"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()
        os.environ.pop(cls.signing_env, None)

    @classmethod
    def request(
        cls,
        method: str,
        path: str,
        payload=None,
        *,
        token: str | None = None,
        origin: str | None = None,
        host: str | None = None,
        raw_body: bytes | None = None,
    ):
        body = raw_body
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif raw_body is not None:
            headers["Content-Type"] = "application/json"
        if origin is not None:
            headers["Origin"] = origin
        if host is not None:
            headers["Host"] = host
        if token is not None:
            headers["X-Bufftag-Token"] = token
        request = Request(cls.base + path, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=3) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return json.loads(exc.read().decode("utf-8"))


class StaticAndHealthTests(ServerCase):
    def test_index_is_local_only_and_loads_the_real_app(self):
        with urlopen(self.base + "/", timeout=3) as response:
            body = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type")
            csp = response.headers.get("Content-Security-Policy")
        self.assertIn("Bufftag // Live Provenance Terminal", body)
        self.assertIn('/src/main.js', body)
        self.assertNotIn("cdnjs.cloudflare.com", body)
        self.assertIn("text/html", content_type)
        self.assertIn("default-src 'self'", csp)

    def test_javascript_and_css_are_served_with_executable_types(self):
        for path, expected in (("/src/main.js", "text/javascript"), ("/styles.css", "text/css")):
            with self.subTest(path=path), urlopen(self.base + path, timeout=3) as response:
                self.assertIn(expected, response.headers.get("Content-Type"))
                self.assertTrue(response.read())

    def test_health_reveals_capabilities_and_a_same_origin_token(self):
        health = self.request("GET", "/api/health")
        self.assertTrue(health["ok"])
        self.assertFalse(health["allow_write"])
        self.assertEqual(health["signing"]["mode"], "unsigned")
        self.assertTrue(health["api_token"])

    def test_host_and_origin_are_restricted_to_loopback(self):
        self.assertEqual(
            self.request("GET", "/api/health", host="attacker.example")["error"]["code"],
            "host_denied",
        )
        self.assertEqual(
            self.request(
                "GET", "/api/health", origin="http://attacker.example"
            )["error"]["code"],
            "origin_denied",
        )

    def test_static_traversal_is_denied(self):
        response = self.request("GET", "/%2e%2e/server.py")
        self.assertEqual(response["error"]["code"], "path_denied")


class ReadOnlyApiTests(ServerCase):
    def test_verify_returns_a_real_report(self):
        response = self.request(
            "POST", "/api/verify", {"root": "."}, token=self.token
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["report"]["files_scanned"], 1)
        self.assertIn("sample.py", {finding["path"] for finding in response["report"]["findings"]})

    def test_propose_writes_nothing_and_marks_identity_unverified(self):
        before = self.workspace.joinpath("sample.py").read_bytes()
        response = self.request(
            "POST", "/api/propose", {"root": ".", "file": "sample.py"}, token=self.token
        )
        after = self.workspace.joinpath("sample.py").read_bytes()
        self.assertTrue(response["ok"])
        self.assertEqual(before, after)
        self.assertEqual(response["proposal"]["metadata"]["author"], "unverified")
        self.assertEqual(response["proposal"]["metadata"]["origin"], "unverified")

    def test_scope_escape_and_absolute_scope_are_rejected(self):
        for scope in ("../", "/tmp"):
            with self.subTest(scope=scope):
                response = self.request(
                    "POST", "/api/verify", {"root": scope}, token=self.token
                )
                self.assertIn(response["error"]["code"], {"scope_denied", "scope_missing"})

    def test_mutation_requires_token(self):
        response = self.request("POST", "/api/stamp", {"root": ".", "file": "sample.py"})
        self.assertEqual(response["error"]["code"], "token_denied")

    def test_oversized_body_is_refused_before_json_parsing(self):
        response = self.request(
            "POST",
            "/api/verify",
            raw_body=b"{" + (b"x" * (server.MAX_BODY_BYTES + 10)),
            token=self.token,
        )
        self.assertEqual(response["error"]["code"], "body_too_large")


class WriteEnabledApiTests(ServerCase):
    allow_write = True

    def setUp(self):
        self.target = self.workspace / "deploy.py"
        self.target.write_text("print('deploy')\n", encoding="utf-8")

    def tearDown(self):
        self.target.unlink(missing_ok=True)
        receipts = self.workspace / ".bufftag" / "receipts.jsonl"
        receipts.unlink(missing_ok=True)
        receipts.with_name("receipts.jsonl.lock").unlink(missing_ok=True)

    def _payload(self, **overrides):
        payload = {
            "root": ".",
            "file": "deploy.py",
            "origin": "test-device",
            "pillar": "test",
            "role": "deployment fixture",
            "author": "Buffy",
            "deps": "none",
            "recorded_at": "2026-09-25T12:00:00+00:00",
            "confirmation": "STAMP deploy.py",
        }
        payload.update(overrides)
        return payload

    def test_stamp_is_a_real_atomic_mutation_with_a_receipt(self):
        response = self.request("POST", "/api/stamp", self._payload(), token=self.token)
        self.assertTrue(response["ok"])
        stamped = self.target.read_text(encoding="utf-8")
        self.assertIn("# [BUFFTAG v1]", stamped)
        self.assertIn("print('deploy')", stamped)
        self.assertTrue((self.workspace / ".bufftag" / "receipts.jsonl").is_file())

    def test_exact_confirmation_and_explicit_metadata_are_required(self):
        wrong_confirmation = self.request(
            "POST", "/api/stamp", self._payload(confirmation="yes"), token=self.token
        )
        self.assertEqual(wrong_confirmation["error"]["code"], "confirmation")
        missing_author = self._payload()
        del missing_author["author"]
        incomplete = self.request(
            "POST", "/api/stamp", missing_author, token=self.token
        )
        self.assertEqual(incomplete["error"]["code"], "metadata")
        self.assertNotIn("[BUFFTAG", self.target.read_text(encoding="utf-8"))

    def test_signed_mode_fails_closed_without_server_key(self):
        response = self.request(
            "POST", "/api/stamp", self._payload(require_signed=True), token=self.token
        )
        self.assertEqual(response["error"]["code"], "signing_key_missing")
        self.assertNotIn("[BUFFTAG", self.target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
