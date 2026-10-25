"""Tests for bin/ingest_keys.py -- the parts that used to misassign keys.

The old version searched a whole file for a 30+ char token and wrote
vault["keys"]["COHERE_API_KEY"]. These tests pin the rules that replaced it.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path.home() / "bin"))
import ingest_keys as ik  # noqa: E402

GROQ = "gsk_ABCDEFGHIJKLMNOPQRSTUVWX"
HF = "hf_ABCDEFGHIJKLMNOPQRSTUVWX"
GEM = "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
BARE_SK = "sk-ffffffffffffffffffffffffffffffff"


class Shapes(unittest.TestCase):
    def test_unique_prefix_is_decisive(self):
        self.assertEqual(ik.provider_for_shape(GROQ), ("groq", 1))
        self.assertEqual(ik.provider_for_shape(HF)[0], "huggingface")
        self.assertEqual(ik.provider_for_shape(GEM)[0], "gemini")

    def test_ambiguous_prefix_is_not_decisive(self):
        provider, matches = ik.provider_for_shape(BARE_SK)
        self.assertIsNone(provider)
        self.assertGreater(matches, 1)


class Parsing(unittest.TestCase):
    def test_unique_shape_wins(self):
        found, _, _ = ik.parse_assignments(f"key: {GROQ}")
        self.assertEqual(found["groq"], [GROQ])

    def test_label_places_an_ambiguous_key(self):
        found, unassigned, _ = ik.parse_assignments(f"OPENAI_API_KEY={BARE_SK}")
        self.assertEqual(found["openai"], [BARE_SK])
        self.assertEqual(unassigned, [])

    def test_label_never_overrides_a_unique_shape(self):
        """A gsk_ key filed under GEMINI is a mistake, not an instruction."""
        found, _, conflicts = ik.parse_assignments(f"GEMINI={GROQ}")
        self.assertNotIn("gemini", found)
        self.assertEqual(conflicts[0]["label"], "gemini")
        self.assertEqual(conflicts[0]["shape"], "groq")

    def test_bare_ambiguous_key_is_reported_not_guessed(self):
        found, unassigned, _ = ik.parse_assignments(f"here is one {BARE_SK}")
        self.assertEqual(found, {})
        self.assertEqual(unassigned, [BARE_SK])

    def test_comment_lines_are_ignored(self):
        found, unassigned, _ = ik.parse_assignments(f"# {GROQ}\n")
        self.assertEqual((found, unassigned), ({}, []))

    def test_duplicate_key_is_not_added_twice(self):
        found, _, _ = ik.parse_assignments(f"{GROQ}\n{GROQ}")
        self.assertEqual(found["groq"], [GROQ])

    def test_prose_mention_before_key_anchors_it(self):
        found, _, _ = ik.parse_assignments(f"my huggingface token {HF}")
        self.assertEqual(found["huggingface"], [HF])


class Merge(unittest.TestCase):
    def test_appends_to_existing_pool(self):
        self.assertEqual(ik.merge_pool("a", ["b", "c"]), "a,b,c")

    def test_deduplicates(self):
        self.assertEqual(ik.merge_pool("a,b", ["b", "c"]), "a,b,c")

    def test_empty_existing_pool(self):
        self.assertEqual(ik.merge_pool("", ["a"]), "a")


class VaultWrite(unittest.TestCase):
    def test_writes_the_schema_the_vault_actually_uses(self):
        blob = {"keys": {}}
        ik.apply_keys(blob, {"groq": [GROQ]}, {"groq": "live"}, "2026-10-25")
        self.assertEqual(blob["keys"]["groq"]["key"], GROQ)
        self.assertEqual(blob["keys"]["groq"]["status"], "live")
        self.assertEqual(blob["keys"]["groq"]["added"], "2026-10-25")
        self.assertNotIn("GROQ_API_KEY", blob["keys"])

    def test_unverified_status_when_the_probe_did_not_run(self):
        blob = {"keys": {}}
        ik.apply_keys(blob, {"cohere": ["x"]}, {"cohere": "unverified"}, "2026-10-25")
        self.assertEqual(blob["keys"]["cohere"]["status"], "unverified")

    def test_a_failed_probe_is_never_marked_live(self):
        blob = {"keys": {}}
        ik.apply_keys(blob, {"groq": [GROQ]}, {"groq": "HTTP_401"}, "2026-10-25")
        self.assertEqual(blob["keys"]["groq"]["status"], "unverified")

    def test_existing_pool_survives_an_ingest(self):
        blob = {"keys": {"groq": {"key": "old", "status": "live"}}}
        ik.apply_keys(blob, {"groq": [GROQ]}, {"groq": "live"}, "2026-10-25")
        self.assertEqual(blob["keys"]["groq"]["key"], f"old,{GROQ}")


class Masking(unittest.TestCase):
    def test_mask_never_contains_the_whole_key(self):
        out = ik.mask(GROQ)
        self.assertNotIn(GROQ, out)
        self.assertIn("...", out)

    def test_short_values_are_fully_hidden(self):
        self.assertEqual(ik.mask("abc"), "***")


class ProbeTargets(unittest.TestCase):
    """A probe is only trustworthy if the route actually checks the key.

    These tests pin the endpoint shapes that were validated by hand against the
    live services on 2026-10-25: unauthenticated -> 401/403, and a bogus key ->
    401/403. A route that answers 200 to a bogus key belongs in NO_PROBE.
    """

    def test_every_probe_is_https_with_a_known_auth_style(self):
        styles = {"bearer", "goog", "xi", "anthropic"}
        for provider, target in ik.PROBES.items():
            self.assertTrue(target[0].startswith("https://"), provider)
            self.assertIn(target[1], styles, provider)
            self.assertIn(len(target), (2, 4), provider)
            if len(target) == 4:
                self.assertEqual(target[2], "POST", provider)

    def test_public_routes_are_not_used_as_probes(self):
        """These answered 200 to a deliberately invalid key; a 200 proves nothing."""
        for provider in ("bazaar", "sageox", "puter"):
            self.assertNotIn(provider, ik.PROBES)
            self.assertIn(provider, ik.NO_PROBE)

    def test_sambanova_probe_needs_a_real_model_to_reach_auth(self):
        """An empty body answers 400 for every key, so this probe must not use one."""
        _, _, method, body = ik.PROBES["sambanova"]
        self.assertEqual(method, "POST")
        self.assertIn('"model"', body)
        self.assertIn('"max_tokens": 1', body)
        self.assertNotEqual(body.strip(), "{}")
        self.assertNotIn("sambanova", ik.NO_PROBE)

    def test_zenmux_is_not_a_probe(self):
        """403 for good and bad keys alike -- indistinguishable, so not a probe."""
        self.assertNotIn("zenmux", ik.PROBES)

    def test_every_no_probe_entry_states_a_reason(self):
        for provider, why in ik.NO_PROBE.items():
            self.assertTrue(why.strip(), provider)
        self.assertFalse(set(ik.PROBES) & set(ik.NO_PROBE))


class ProbeSemantics(unittest.TestCase):
    def setUp(self):
        self.real = ik.urllib.request.urlopen
        self.seen = {}

    def tearDown(self):
        ik.urllib.request.urlopen = self.real

    def _fake(self, code=None, payload=b"{}"):
        class Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

        def urlopen(req, timeout=None):
            self.seen["req"] = req
            if code is None:
                return Resp()
            raise ik.urllib.error.HTTPError(req.full_url, code, "err", {}, None)

        ik.urllib.request.urlopen = urlopen

    def test_authenticated_but_malformed_post_counts_as_accepted(self):
        """400 on a deliberate empty body means auth passed; no tokens spent."""
        self._fake(code=400)
        self.assertEqual(ik.probe("aimlapi", "sk-test"), "live")
        self.assertEqual(self.seen["req"].get_method(), "POST")
        self.assertEqual(self.seen["req"].data, b"{}")

    def test_rejected_key_is_not_live(self):
        self._fake(code=401)
        self.assertEqual(ik.probe("aimlapi", "sk-test"), "HTTP_401")

    def test_a_400_on_a_get_proves_nothing(self):
        self._fake(code=400)
        self.assertEqual(ik.probe("groq", "gsk_x"), "HTTP_400")

    def test_elevenlabs_uses_its_own_header(self):
        self._fake()
        ik.probe("elevenlabs", "sk-test")
        headers = {k.lower(): v for k, v in self.seen["req"].header_items()}
        self.assertEqual(headers.get("xi-api-key"), "sk-test")
        self.assertNotIn("authorization", headers)

    def test_unreachable_is_not_a_verdict_about_the_key(self):
        def boom(req, timeout=None):
            raise ik.urllib.error.URLError("no route")

        ik.urllib.request.urlopen = boom
        self.assertEqual(ik.probe("groq", "gsk_x"), "unreachable")


if __name__ == "__main__":
    unittest.main()
