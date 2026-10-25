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


if __name__ == "__main__":
    unittest.main()
