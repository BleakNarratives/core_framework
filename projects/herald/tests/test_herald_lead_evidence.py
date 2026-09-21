"""Herald x Foxwood: a lead's own post becomes citable evidence, and stays theirs.

Four claims are under test, and only one of them is about prompt wording.

1. A lead read out of LEADS.md contributes exactly what the file kept, which is the
   title and the link -- not a post body. `monitor_leads.render` does not write one.
   The tests here pin that rather than pretending the excerpt is richer than it is.

2. Nothing that identifies a person by address is written into the ledger. The
   repository's own .gitignore already refuses to track a list of strangers'
   addresses; a ledger seeded from leads would walk that decision back one layer
   down, and the ledger is the artifact that travels.

3. Seeding goes through the same PROVENANCE.md gate the reader uses. If it did not,
   seeding would be the way to get quarantined material into a prompt.

4. The seeded post is framed as *their* post and reaches only the draft that is
   answering it. One shared `evidence` list handed to every draft would have each
   pitch name three strangers' threads.

Everything here is offline: the ledger is a temporary directory, the gate is built
against a temporary registry, the model call is patched, and no socket is opened.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
HERALD = HERE.parent
REPO_ROOT = HERALD.parent.parent
sys.path.insert(0, str(HERALD))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import lead_evidence as le  # noqa: E402
import outreach_agent as oa  # noqa: E402

from src.foxwood_research import ResearchLedger  # noqa: E402
from src.foxwood_research.registry import RegistryGate  # noqa: E402

LEADS = """# LEADS

* **[u/dev]** [HIRING] fix our legacy Django monolith
  - Link: https://www.reddit.com/r/forhire/comments/aaa/one/
  - Matched: `[hiring]`
  - Contact: email:jobs@acme.test, dm

* **[u/other]** [HIRING] n8n workflows keep breaking on retries
  - Link: https://www.reddit.com/r/forhire/comments/bbb/two/
  - Matched: `[hiring]`
  - Contact: dm
"""


def entry(title, link, **fields):
    """The LEADS.md shape: fields are the file's bookkeeping, not the post."""
    return {"who": "u/someone", "title": title,
            "fields": {"Matched": "`[hiring]`", "Contact": "dm", "Link": link, **fields}}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.leads_dir = self.dir / "ledger"

    def seed(self, entries, **kwargs):
        return le.seed_ledger(entries, self.leads_dir, **kwargs)

    def ledger(self):
        ledger = ResearchLedger(self.leads_dir)
        return ledger

    def stored(self):
        return list(self.ledger().sources)

    def quiet(self, fn, *args, **kwargs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            result = fn(*args, **kwargs)
        return result, buf.getvalue()

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


class TestWhatALeadActuallyContributes(Base):
    """The excerpt is the title, because that is what the file kept."""

    def test_the_title_is_the_excerpt_when_the_file_carried_no_body(self):
        self.assertEqual(le.excerpt_for(entry("Fix our monolith", "https://x.test/1")),
                         "Fix our monolith")

    def test_a_scanners_body_is_used_when_the_caller_still_has_it(self):
        # The scanners hold the post text in memory and drop it when they render.
        # Passing them straight through is the difference between citing a title and
        # citing what the person wrote.
        scanned = {"title": "first line", "url": "https://news.ycombinator.com/item?id=1",
                   "body": "the whole comment, first line and then the rest of it",
                   "source": "HN Who is hiring"}
        self.assertTrue(le.excerpt_for(scanned).startswith("the whole comment"))
        self.assertEqual(le.normalize(scanned)["url"], "https://news.ycombinator.com/item?id=1")
        self.assertEqual(le.normalize(scanned)["publisher"], "HN Who is hiring")

    def test_the_excerpt_is_bounded(self):
        huge = "x" * (le.MAX_EXCERPT_CHARS * 3)
        self.assertEqual(len(le.excerpt_for(entry(huge, "https://x.test/1"))),
                         le.MAX_EXCERPT_CHARS)

    def test_an_entry_with_neither_title_nor_body_is_not_evidence(self):
        self.assertEqual(le.excerpt_for(entry("", "https://x.test/1")), "")

    def test_the_link_is_read_from_either_field_name(self):
        # The old scanner wrote URL:, monitor_leads writes Link:. Both are still in
        # the file, and reading only one of them silently drops half the archive.
        self.assertEqual(le.normalize(entry("t", "https://x.test/1"))["url"],
                         "https://x.test/1")
        self.assertEqual(le.normalize({"title": "t", "fields": {"URL": "https://y.test/2"}})["url"],
                         "https://y.test/2")


class TestNothingIdentifiesAnybodyByAddress(Base):
    """The ledger travels; a list of strangers' addresses must not travel with it."""

    def test_an_address_in_a_post_is_not_stored(self):
        self.seed([entry("email me at hiring@acme.test about the monolith",
                         "https://x.test/1")])
        excerpt = self.stored()[0].excerpt
        self.assertNotIn("hiring@acme.test", excerpt)
        self.assertIn(le.PII_PLACEHOLDER, excerpt)

    def test_contact_hints_inside_the_text_are_removed(self):
        scanned = {"title": "t", "url": "https://x.test/1",
                   "body": "DMs are open, or email:jobs@acme.test to talk"}
        self.assertEqual(le.strip_pii(scanned["body"]),
                         "DMs are open, or [contact detail removed] to talk")

    def test_an_address_inside_a_hint_is_redacted_once(self):
        # `email:x@y.test` matches the hint rule *and* the address rule, so the hint
        # match contains the address match. Applying the two patterns one after the
        # other re-matched the placeholder the first pass wrote and produced
        # "[contact detail removed] detail removed]" -- a redaction that both leaks
        # the shape of what it removed and corrupts the sentence around it.
        self.assertEqual(le.strip_pii("write to email:jobs@acme.test please"),
                         "write to [contact detail removed] please")
        self.assertEqual(le.strip_pii("a@b.test"), "[contact detail removed]")

    def test_text_with_nothing_to_redact_is_returned_unchanged(self):
        self.assertEqual(le.strip_pii("we need help with retries"),
                         "we need help with retries")
        self.assertEqual(le.strip_pii(""), "")

    def test_the_username_and_thread_link_survive(self):
        # These two are the only reason the lead is usable, and a redaction that
        # removes them is a redaction an operator turns off.
        rows, _ = self.seed([entry("Fix our monolith", "https://x.test/1")])
        self.assertEqual(rows, {"https://x.test/1": self.stored()[0].source_id})
        self.assertEqual(self.stored()[0].url, "https://x.test/1")

    def test_the_contact_field_is_never_copied_into_the_excerpt(self):
        # The hints are the leads file's business. The excerpt is built from the post
        # text alone, so a `Contact:` line can never arrive as prompt material.
        self.seed([entry("Fix our monolith", "https://x.test/1", Contact="email:a@b.test, dm")])
        self.assertNotIn("a@b.test", self.stored()[0].excerpt)


class TestSeeding(Base):
    def test_a_seeded_lead_lands_as_a_gated_source(self):
        written, skipped = self.seed([entry("Fix our monolith", "https://x.test/1")])
        record = self.stored()[0]
        self.assertEqual(skipped, 0)
        self.assertEqual(list(written.values()), [record.source_id])
        self.assertTrue(record.origin.startswith("herald:lead:"))
        self.assertEqual(record.title, "Fix our monolith")
        self.assertIn("private draft", record.license_note)

    def test_a_lead_with_no_thread_link_is_skipped_and_counted(self):
        # A source with no link cannot be opened by the operator before sending, so
        # it is not evidence. It is counted rather than dropped quietly: a run that
        # stored nothing must not read like a run that stored everything.
        written, skipped = self.seed([entry("Fix our monolith", "")])
        self.assertEqual((written, skipped), ({}, 1))
        self.assertEqual(self.stored(), [])

    def test_a_lead_with_no_text_is_skipped_and_counted(self):
        written, skipped = self.seed([entry("", "https://x.test/1")])
        self.assertEqual((written, skipped), ({}, 1))
        self.assertEqual(self.stored(), [])

    def test_seeding_the_same_leads_twice_adds_nothing(self):
        # Source identity is a digest of url + excerpt, so a second run over the same
        # LEADS.md cannot double the ledger -- and a draft that cited src-abc still
        # cites src-abc. Keyed on the content, not on when it was seeded.
        first, _ = self.seed([entry("Fix our monolith", "https://x.test/1")])
        second, _ = self.seed([entry("Fix our monolith", "https://x.test/1")])
        self.assertEqual(first, second)
        self.assertEqual(len(self.stored()), 1)

    def test_a_blocked_lead_is_refused_by_the_registry_not_just_filtered(self):
        # The gate is the same PROVENANCE.md check the reader runs. If seeding wrote
        # ungated, it would be the way around the gate rather than a second way
        # through it.
        gate = RegistryGate(registry_path=self.dir / "PROVENANCE.md",
                            parse=lambda path: {"ScholarScout": {"classification": "FOREIGN"}})
        with self.assertRaises(Exception) as caught:
            self.seed([entry("Fix our monolith", "https://x.test/ScholarScout/notes")],
                      registry=gate)
        self.assertIn("registry rejects", str(caught.exception))
        self.assertEqual(self.stored(), [])


class TestTheModuleIsNotLoadedTwice(Base):
    """`python outreach_agent.py` puts that file in sys.modules as __main__."""

    def test_the_loaded_module_is_preferred(self):
        self.assertIs(le.herald(), oa)

    def test_the_running_script_is_recognised_as_outreach_agent(self):
        # Without this branch, running the tool as a script would make lead_evidence
        # import a second copy of it: same source, two module objects, two `AI` paths.
        fake = types.ModuleType("__main__")
        fake.__file__ = str(HERALD / "outreach_agent.py")
        had_oa, had_main = sys.modules.get("outreach_agent"), sys.modules.get("__main__")
        try:
            sys.modules.pop("outreach_agent", None)
            sys.modules["__main__"] = fake
            self.assertIs(le.herald(), fake)
        finally:
            if had_oa is not None:
                sys.modules["outreach_agent"] = had_oa
            else:
                sys.modules.pop("outreach_agent", None)
            if had_main is not None:
                sys.modules["__main__"] = had_main
            else:
                sys.modules.pop("__main__", None)

    def test_a_foreign_main_module_is_not_mistaken_for_this_one(self):
        fake = types.ModuleType("__main__")
        fake.__file__ = str(self.dir / "something_else.py")
        (self.dir / "something_else.py").write_text("x = 1\n")
        had_oa, had_main = sys.modules.get("outreach_agent"), sys.modules.get("__main__")
        try:
            sys.modules.pop("outreach_agent", None)
            sys.modules["__main__"] = fake
            self.assertIsNot(le.herald(), fake)
        finally:
            if had_oa is not None:
                sys.modules["outreach_agent"] = had_oa
            if had_main is not None:
                sys.modules["__main__"] = had_main


class TestTheWiringThroughMain(Base):
    def test_a_seeded_post_is_framed_as_theirs_and_not_mine(self):
        rc, out, _ = self.call_main(["--seed-ledger", str(self.leads_dir),
                                     "--about", "I fix legacy monoliths.",
                                     "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("The post I am replying to", out)
        self.assertIn("That is THEIR post, not mine", out)

    def test_each_draft_carries_only_its_own_post(self):
        # The seeded post is per lead. One list handed to every draft would have each
        # pitch name three strangers' threads, which is worse than citing nothing.
        rc, out, _ = self.call_main(["--seed-ledger", str(self.leads_dir),
                                     "--about", "I fix legacy monoliths.",
                                     "--dry-run"])
        self.assertEqual(rc, 0)
        prompts = out.split("--- prompt for ")[1:]
        self.assertEqual(len(prompts), 2)
        self.assertIn("Django monolith", prompts[0])
        self.assertNotIn("n8n", prompts[0])
        self.assertIn("n8n", prompts[1])
        self.assertNotIn("Django", prompts[1])

    def test_the_draft_records_the_post_it_rested_on(self):
        rc, out, drafts = self.call_main(["--seed-ledger", str(self.leads_dir),
                                         "--about", "I fix legacy monoliths."])
        self.assertEqual(rc, 0)
        written = drafts.read_text()
        for record in self.stored():
            self.assertIn(record.source_id, written)

    def test_the_offer_is_still_the_only_source_of_claims(self):
        # ABOUT.md stays the only place a claim about the operator may come from; the
        # seeded post is added as the prospect's words, never as material about me.
        rc, out, _ = self.call_main(["--seed-ledger", str(self.leads_dir),
                                     "--about", "I fix legacy monoliths.",
                                     "--dry-run"])
        self.assertIn("the only thing you may claim about me", out)

    def test_neither_framing_appears_when_nothing_was_seeded(self):
        # The no-evidence prompt is still byte-for-byte the prompt this tool sent
        # before any of this existed.
        rc, out, _ = self.call_main(["--about", "I fix legacy monoliths.", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertNotIn("The post I am replying to", out)
        self.assertNotIn("Public artifacts", out)

    def test_a_dry_run_writes_nothing_to_the_ledger(self):
        # --dry-run's whole contract is "print the prompts and write nothing". It was
        # seeding the operator's directory on the way to printing them, which made the
        # one command that promises to write nothing the command that writes the most.
        rc, out, drafts = self.call_main(["--seed-ledger", str(self.leads_dir),
                                          "--about", "I fix legacy monoliths.",
                                          "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("scratch directory (dry run writes nothing)", out)
        self.assertFalse(drafts.exists())
        self.assertFalse(self.leads_dir.exists())

    def test_an_empty_seed_path_is_a_refusal_not_a_silent_no_op(self):
        rc, out, _ = self.call_main(["--seed-ledger", "   ", "--about", "x"])
        self.assertEqual(rc, 2)
        self.assertIn("--seed-ledger was empty", out)

    def test_a_lead_already_drafted_is_not_reseeded(self):
        # Seeding follows `todo`. A lead this run will not write to needs no evidence,
        # and re-seeding the whole archive on every run is how a bounded ledger stops
        # being bounded.
        rc, _, drafts = self.call_main(["--seed-ledger", str(self.leads_dir),
                                        "--about", "I fix legacy monoliths."])
        self.assertEqual(rc, 0)
        first = set(self.stored())
        self.assertGreater(len(first), 0)
        rc, out, _ = self.call_main(["--seed-ledger", str(self.leads_dir),
                                     "--about", "I fix legacy monoliths."])
        self.assertEqual(rc, 0)
        self.assertIn("seeded 0 of 0 lead(s)", out)
        self.assertEqual(set(self.stored()), first)

    def test_a_skipped_lead_still_gets_a_prompt(self):
        # No thread row is not a failure: the draft falls back to exactly the prompt
        # it would have had without --seed-ledger. The one outcome this must not
        # produce is a draft quoting a post it was not answering.
        leads = self.dir / "LEADS.md"
        leads.write_text(
            "# LEADS\n\n"
            "* **[u/dev]** [HIRING] fix our legacy Django monolith\n"
            "  - Link: https://www.reddit.com/r/forhire/comments/aaa/one/\n"
            "  - Matched: `[hiring]`\n"
            "  - Contact: dm\n")
        rc, out, drafts = self.call_main(["--seed-ledger", str(self.leads_dir),
                                         "--about", "I fix legacy monoliths."])
        self.assertEqual(rc, 0)
        self.assertIn("drafted", out)
        self.assertEqual(len(self.stored()), 1)


if __name__ == "__main__":
    unittest.main()
