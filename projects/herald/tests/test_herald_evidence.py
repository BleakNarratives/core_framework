"""Herald x Foxwood: the offer can cite real artifacts, and the registry enforces it.

Two claims are under test here, and neither is about email formatting.

1. A draft may point at bounded, hashed artifacts drawn from a Foxwood ledger, and
   those artifacts must not become new material about the offer. ABOUT.md stays the
   only place a claim about the operator may come from.

2. ABOUT_EVIDENCE.md's last may-not-claim bullet -- no ScholarScout-derived or
   quarantined material as Foxwood evidence -- was prose before this. It is now a
   gate, and a refused source kills the run instead of quietly downgrading to
   "no evidence available", which is how a broken pipe comes to read as a good one.

Everything here is offline: the ledger is a temporary directory, the model call is
patched, and no socket is opened.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
HERALD = HERE.parent
REPO_ROOT = HERALD.parent.parent
sys.path.insert(0, str(HERALD))

import outreach_agent as oa  # noqa: E402

from src.foxwood_research import ResearchLedger  # noqa: E402

LEADS = """# LEADS

* **[u/dev]** [HIRING] fix our legacy Django monolith
  - Link: https://www.reddit.com/r/forhire/comments/aaa/bbb/
  - Matched: `[hiring]`
  - Contact: email:jobs@acme.test, dm
"""


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.ledger = ResearchLedger(self.dir / "ledger")

    def quiet(self, fn, *args, **kwargs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            result = fn(*args, **kwargs)
        return result, buf.getvalue()

    def claim(self, text, url="https://example.test/record", license_note="public terms",
              origin="network"):
        source = self.ledger.add_source(
            title="A public record", url=url, publisher="Example",
            excerpt="A bounded excerpt.", license_note=license_note, origin=origin)
        return self.ledger.add_claim(text=text, source_ids=[source.source_id],
                                     confidence="high"), source

    def call_main(self, argv, reply="Subject: Hi\n\nShort body."):
        leads = self.dir / "LEADS.md"
        if not leads.is_file():
            leads.write_text(LEADS)
        with patch.object(oa, "LEADS_FILE", leads), \
             patch.object(oa, "DRAFTS_FILE", self.dir / "DRAFTS.md"), \
             patch.object(oa, "STATE_FILE", self.dir / ".state.json"), \
             patch.object(oa, "complete", lambda prompt, model=None: reply):
            rc, out = self.quiet(oa.main, argv)
        return rc, out, self.dir / "DRAFTS.md"


class TestEvidenceLoading(Base):
    def test_a_claim_becomes_one_source_line_with_its_hash_and_licence(self):
        claim, source = self.claim("The gateway rotates keys per provider.")
        rows = oa.load_evidence(self.ledger.root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_id"], source.source_id)
        self.assertEqual(rows[0]["content_hash"], source.content_hash)
        self.assertEqual(rows[0]["license_note"], "public terms")
        self.assertEqual(rows[0]["claim_id"], claim.claim_id)

    def test_named_claims_are_the_only_ones_taken(self):
        first, _ = self.claim("First claim.")
        second, _ = self.claim("Second claim.", url="https://example.test/two")
        rows = oa.load_evidence(self.ledger.root, [second.claim_id])
        self.assertEqual([row["claim_id"] for row in rows], [second.claim_id])
        self.assertNotIn(first.claim_id, {row["claim_id"] for row in rows})

    def test_an_unknown_claim_id_raises_rather_than_selecting_something_else(self):
        # Silently falling back to "the most recent few" would mean the operator
        # asked for one artifact and got a different one, which they would never see.
        self.claim("Something.")
        with self.assertRaises(RuntimeError):
            oa.load_evidence(self.ledger.root, ["claim-not-in-this-ledger"])

    def test_selection_is_capped_not_unbounded(self):
        for index in range(6):
            self.claim(f"Claim number {index}.", url=f"https://example.test/{index}")
        self.assertEqual(len(oa.load_evidence(self.ledger.root, [], 2)), 2)
        self.assertEqual(len(oa.load_evidence(self.ledger.root, [], 99)), 6)

    def test_a_missing_ledger_directory_raises(self):
        with self.assertRaises(RuntimeError):
            oa.load_evidence(self.dir / "nowhere")

    def test_a_ledger_with_no_claims_raises(self):
        with self.assertRaises(RuntimeError):
            oa.load_evidence(self.ledger.root)


class TestTheRegistryGateIsThePoint(Base):
    """ABOUT_EVIDENCE.md's last bullet, enforced instead of hoped for."""

    def test_a_foreign_source_is_refused_at_load_time(self):
        # Built the way a pre-gate ledger would be: no floor configured.
        stale = ResearchLedger(self.dir / "stale", foreign_roots=())
        source = stale.add_source(
            title="Copied material", url="https://example.test/x", publisher="unknown",
            excerpt="foreign", origin="ScholarScout/src/core.py")
        stale.add_claim(text="Something borrowed.", source_ids=[source.source_id])
        with self.assertRaises(Exception) as caught:
            oa.load_evidence(stale.root)
        self.assertIn("ScholarScout", str(caught.exception))

    def test_the_refusal_is_the_real_registry_not_a_local_copy(self):
        # If this ever stops naming PROVENANCE.md, someone has reimplemented the
        # rule here, and the two copies will drift.
        stale = ResearchLedger(self.dir / "stale2", foreign_roots=())
        source = stale.add_source(title="T", url="https://example.test/y", publisher="P",
                                  excerpt="E", origin="ScholarScout/thing.py")
        stale.add_claim(text="x", source_ids=[source.source_id])
        with self.assertRaises(Exception) as caught:
            oa.load_evidence(stale.root)
        self.assertIn("PROVENANCE.md", str(caught.exception))

    def test_an_ordinary_source_passes(self):
        self.claim("Ordinary evidence.")
        self.assertEqual(len(oa.load_evidence(self.ledger.root)), 1)

    def test_the_repo_root_is_found_by_walking_up(self):
        self.assertEqual(oa.find_repo_root(), REPO_ROOT)


class TestEvidenceInThePrompt(Base):
    def test_no_evidence_leaves_the_prompt_byte_for_byte_as_it_was(self):
        # The feature must be additive: an operator who passes no ledger gets exactly
        # the prompt the previous version sent.
        entry = oa.parse_leads(LEADS)[0]
        self.assertEqual(oa.build_prompt(entry, "I do X."),
                         oa.build_prompt(entry, "I do X.", []))

    def test_evidence_appears_with_its_hash_and_licence(self):
        claim, source = self.claim("The gateway rotates keys per provider.")
        entry = oa.parse_leads(LEADS)[0]
        rows = oa.load_evidence(self.ledger.root)
        prompt = oa.build_prompt(entry, "I do X.", rows)
        self.assertIn(source.source_id, prompt)
        self.assertIn(source.content_hash[:12], prompt)
        self.assertIn("public terms", prompt)

    def test_the_offer_is_still_the_only_place_a_claim_comes_from(self):
        # The block's own rules, asserted on the prompt text. Without these three
        # lines the artifacts become a second source of claims about the operator.
        self.claim("Something true.")
        entry = oa.parse_leads(LEADS)[0]
        prompt = oa.build_prompt(entry, "I only do X.", oa.load_evidence(self.ledger.root))
        self.assertIn("What I actually offer, and the only thing you may claim about me:", prompt)
        self.assertIn("I only do X.", prompt)
        self.assertIn("Never say or imply they exist inside their system", prompt)
        self.assertIn("Do not claim anything about them beyond the title", prompt)

    def test_the_refusal_escape_hatch_survives_the_new_block(self):
        self.claim("Something true.")
        entry = oa.parse_leads(LEADS)[0]
        prompt = oa.build_prompt(entry, "I do X.", oa.load_evidence(self.ledger.root))
        self.assertIn("NO FIT", prompt)

    def test_a_draft_records_what_it_rested_on(self):
        self.claim("Something true.")
        entry = oa.parse_leads(LEADS)[0]
        rows = oa.load_evidence(self.ledger.root)
        block = oa.render(entry, "S", "B", "NOW", evidence=rows)
        self.assertIn("- Evidence:", block)
        self.assertIn(rows[0]["source_id"], block)
        self.assertIn(rows[0]["content_hash"][:12], block)

    def test_a_draft_with_no_evidence_has_no_evidence_line(self):
        entry = oa.parse_leads(LEADS)[0]
        self.assertNotIn("- Evidence:", oa.render(entry, "S", "B", "NOW"))


class TestEvidenceThroughMain(Base):
    def test_an_omitted_ledger_is_not_an_error(self):
        rc, out, drafts = self.call_main(["--about", "I do X.", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("prompt for", out)
        self.assertNotIn("evidence", out.lower().split("prompt for")[0])

    def test_a_dry_run_shows_the_evidence_in_the_prompt(self):
        claim, source = self.claim("The gateway rotates keys per provider.")
        rc, out, drafts = self.call_main(
            ["--about", "I do X.", "--evidence-ledger", str(self.ledger.root), "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn(source.source_id, out)
        self.assertFalse(drafts.exists())

    def test_a_broken_ledger_fails_the_run_instead_of_drafting_without_it(self):
        # THE FAILURE THIS PREVENTS. If a requested ledger silently became "no
        # evidence", every draft would go out weaker than the operator believes,
        # and the run would report success.
        rc, out, drafts = self.call_main(
            ["--about", "I do X.", "--evidence-ledger", str(self.dir / "nope")])
        self.assertEqual(rc, 2)
        self.assertIn("cannot be loaded", out)
        self.assertFalse(drafts.exists())

    def test_a_foreign_source_stops_the_run_before_any_draft(self):
        stale = ResearchLedger(self.dir / "stale", foreign_roots=())
        source = stale.add_source(title="Copied", url="https://example.test/z",
                                  publisher="P", excerpt="E",
                                  origin="ScholarScout/src/core.py")
        stale.add_claim(text="borrowed", source_ids=[source.source_id])
        rc, out, drafts = self.call_main(
            ["--about", "I do X.", "--evidence-ledger", str(stale.root)])
        self.assertEqual(rc, 2)
        self.assertIn("ScholarScout", out)
        self.assertFalse(drafts.exists())

    def test_a_real_run_writes_the_evidence_onto_the_draft(self):
        claim, source = self.claim("The gateway rotates keys per provider.")
        rc, out, drafts = self.call_main(
            ["--about", "I do X.", "--evidence-ledger", str(self.ledger.root)])
        self.assertEqual(rc, 0)
        text = drafts.read_text()
        self.assertIn("- Evidence:", text)
        self.assertIn(source.source_id, text)

    def test_which_evidence_a_batch_used_is_remembered(self):
        claim, source = self.claim("The gateway rotates keys per provider.")
        self.call_main(["--about", "I do X.", "--evidence-ledger", str(self.ledger.root)])
        state = (self.dir / ".state.json").read_text()
        self.assertIn(source.source_id, state)
        self.assertIn(claim.claim_id, state)

    def test_naming_one_claim_uses_only_that_one(self):
        first, first_source = self.claim("First.")
        second, second_source = self.claim("Second.", url="https://example.test/two")
        rc, out, drafts = self.call_main(
            ["--about", "I do X.", "--evidence-ledger", str(self.ledger.root),
             "--evidence-claim", first.claim_id, "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn(first_source.source_id, out)
        self.assertNotIn(second_source.source_id, out)


if __name__ == "__main__":
    unittest.main()
