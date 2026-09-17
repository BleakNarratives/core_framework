"""Offline tests for the herald pipeline.

Both transports are replaced with fixtures — `monitor_leads.fetch` and
`hn_leads._get` — so a suite run cannot depend on Reddit's rate limiter, on
Algolia, or on what month it happens to be. Nothing here opens a socket.

Run it with the venv interpreter, which is where pytest lives on this box. The
default `python3` is a shim in ~/bin with no pytest installed:

    ~/venv/bin/python -m pytest projects/herald/tests -q
    ~/venv/bin/python -m unittest discover -s projects/herald/tests -t projects/herald -v

Several tests here are marked as regressions and name the bug they pin, because
two of the worst defects in this pipeline were silent: a dedupe key that collapsed
263 distinct posts into one, and a filter that would have admitted freelancers as
buyers.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
HERALD = HERE.parent
sys.path.insert(0, str(HERALD))

import hn_leads              # noqa: E402
import monitor_leads as ml   # noqa: E402
import outreach_agent as oa  # noqa: E402


ATOM_FEED = b"""<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>[HIRING] fix our legacy Django monolith</title>
<link href="https://www.reddit.com/r/forhire/comments/aaa/bbb/"/>
<author><name>/u/dev</name></author><updated>2026-09-16T01:02:03Z</updated>
<content type="html">&lt;p&gt;Email jobs@acme.test &lt;a href="https://acme.test"&gt;site&lt;/a&gt;&lt;/p&gt;</content>
</entry>
<entry><title>[FOR HIRE] dev available, open to hiring managers</title>
<link rel="alternate" href="https://www.reddit.com/r/forhire/comments/ccc/ddd/"/>
<author><name>/u/freelancer</name></author><published>2026-09-15T00:00:00Z</published>
<content type="html">&lt;p&gt;DM me&lt;/p&gt;</content>
</entry>
<entry><title>PSA: coding agents pad their diffs</title>
<link href="https://www.reddit.com/r/forhire/comments/eee/fff/"/>
<author><name>/u/chat</name></author>
<content type="html">&lt;p&gt;discussion&lt;/p&gt;</content>
</entry>
</feed>"""

HN_STORY = {"objectID": "49522897", "created_at": "2026-09-01T15:00:00Z",
            "title": "Ask HN: Who is hiring? (September 2026)"}

HN_HITS = [
    # a real job post, with an address
    {"objectID": "1", "parent_id": "49522897", "author": "acme",
     "created_at": "2026-09-02T00:00:00Z",
     "comment_text": "<p>Acme | Backend Engineer | Remote | $150k<br>Email jobs@acme.test</p>"},
    # the OP's own rules comment -- not a job
    {"objectID": "2", "parent_id": "49522897", "author": "whoishiring",
     "created_at": "2026-09-01T15:00:00Z",
     "comment_text": "<p>Please state the location and whether remote is allowed.</p>"},
    # a reply to a job -- discussion, not a job
    {"objectID": "3", "parent_id": "1", "author": "curious",
     "created_at": "2026-09-02T01:00:00Z",
     "comment_text": "<p>Do you sponsor visas?</p>"},
    # a job post with only an application link
    {"objectID": "4", "parent_id": "49522897", "author": "noaddr",
     "created_at": "2026-09-03T00:00:00Z",
     "comment_text": "<p>Noaddr | Ops | Onsite<br>Apply at https://acme.test/jobs</p>"},
]

LEAD_FIXTURE = """# LEADS

* **[u/dev]** [HIRING] fix our legacy Django monolith
  - Link: https://www.reddit.com/r/forhire/comments/aaa/bbb/
  - Matched: `[hiring]`
  - Contact: email:jobs@acme.test, dm
  - Posted: 2026-09-16T01:02:03Z
* **[u/noaddr]** Hiring: ops person
  - Link: https://www.reddit.com/r/forhire/comments/ccc/ddd/
  - Matched: `hiring`
* **[Reddit r/ChatGPTCoding]** what is your budget
  - URL: https://www.reddit.com/r/ChatGPTCoding/comments/1wdfc5x/x/
"""


class Base(unittest.TestCase):
    def quiet(self, fn, *args, **kwargs):
        """Run something chatty; return (result, everything it printed).

        Both streams, not just stdout. The tools report progress on stdout and
        failures on stderr, so capturing one and asserting on it is how you get a
        test suite that passes while the error messages are unverified -- and
        those messages are the entire user-facing report of this pipeline.
        """
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            result = fn(*args, **kwargs)
        return result, buf.getvalue()

    def tmpdir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)


# ── dedupe + the URL-identity bug ────────────────────────────────────────────

class TestDedupeIdentity(unittest.TestCase):
    def test_repeated_runs_add_nothing(self):
        known = set()
        entry = {"uid": "https://r.example/a", "title": "t"}
        self.assertEqual(len(ml.new_entries([entry], known)), 1)
        self.assertEqual(len(ml.new_entries([entry], known)), 0)

    def test_normalize_url_ignores_query_fragment_slash_and_case(self):
        self.assertEqual(ml.normalize_url("https://R.example/A/?utm=1#x"),
                         ml.normalize_url("https://r.example/A"))

    def test_regression_hn_item_urls_all_collapse_to_one_key(self):
        # THE BUG. normalize_url drops the query, and on HN the query IS the
        # identity. Measured 2026-09-17: 263 real job posts deduplicated to a
        # single recorded entry, silently, because a collapse looks exactly like
        # "already seen". This test pins the limitation so nobody routes HN
        # identity through normalize_url again.
        first = ml.normalize_url("https://news.ycombinator.com/item?id=111")
        second = ml.normalize_url("https://news.ycombinator.com/item?id=222")
        self.assertEqual(first, second)
        self.assertNotIn("id=", first)

    def test_regression_hn_ids_in_distinguishes_them(self):
        # The fix: the item id is the key.
        found = hn_leads.hn_ids_in(
            "- Link: https://news.ycombinator.com/item?id=111\n"
            "- Link: https://news.ycombinator.com/item?id=222\n")
        self.assertEqual(found, {"hn:111", "hn:222"})

    def test_hn_ids_in_is_silent_on_a_file_with_none(self):
        self.assertEqual(hn_leads.hn_ids_in(LEAD_FIXTURE), set())


# ── monitor_leads: parsing, filtering, contact extraction ────────────────────

class TestAtomParsing(unittest.TestCase):
    def setUp(self):
        self.entries = ml.parse_atom(ATOM_FEED, "test source")

    def test_parses_every_entry(self):
        self.assertEqual(len(self.entries), 3)

    def test_author_leading_slash_is_stripped(self):
        self.assertEqual(self.entries[0]["author"], "u/dev")

    def test_rel_less_link_is_taken(self):
        self.assertEqual(self.entries[0]["url"],
                         "https://www.reddit.com/r/forhire/comments/aaa/bbb/")

    def test_rel_alternate_link_is_taken(self):
        self.assertEqual(self.entries[1]["url"],
                         "https://www.reddit.com/r/forhire/comments/ccc/ddd/")

    def test_updated_is_used_when_published_is_absent(self):
        self.assertEqual(self.entries[0]["published"], "2026-09-16T01:02:03Z")

    def test_body_and_links_are_captured_from_html_content(self):
        self.assertIn("jobs@acme.test", self.entries[0]["body"])
        self.assertIn("https://acme.test", self.entries[0]["links"])

    def test_junk_raises_rather_than_yielding_nothing(self):
        # A silent empty list would look identical to "no new posts".
        with self.assertRaises(ET.ParseError):
            ml.parse_atom(b"<feed><not closed", "x")


class TestHiringFilter(unittest.TestCase):
    def keep(self, title):
        return ml.is_hiring({"title": title})

    def test_hiring_tag_is_kept(self):
        self.assertTrue(self.keep("[HIRING] need a python dev")[0])

    def test_bare_hiring_word_is_kept(self):
        self.assertTrue(self.keep("Hiring: someone to untangle this")[0])

    def test_for_hire_is_rejected_even_though_it_contains_hiring(self):
        # THE HARD CASE. A loose `hiring` substring admits a freelancer
        # advertising themselves, which is the opposite of a lead.
        kept, _ = self.keep("[FOR HIRE] Senior dev, open to hiring managers")
        self.assertFalse(kept)

    def test_for_hire_lowercase_is_also_rejected(self):
        self.assertFalse(self.keep("[for hire] react developer")[0])

    def test_a_discussion_title_is_rejected(self):
        self.assertFalse(self.keep("My agent keeps destroying my codebase")[0])

    def test_the_admitting_tag_is_reported(self):
        self.assertEqual(self.keep("[HIRING] x")[1], "[hiring]")


class TestContactExtraction(unittest.TestCase):
    def hints(self, body, links=()):
        return ml.contact_hints({"body": body, "links": list(links)})

    def test_email_is_recorded(self):
        self.assertIn("email:jobs@acme.test", self.hints("write to jobs@acme.test"))

    def test_external_link_is_recorded(self):
        self.assertIn("link:https://shop.test/contact",
                      self.hints("see https://shop.test/contact"))

    def test_reddit_permalink_is_not_contact_information(self):
        got = self.hints("see https://www.reddit.com/r/forhire/comments/a/b/")
        self.assertFalse([h for h in got if "reddit" in h])

    def test_dm_is_recorded_last(self):
        got = self.hints("email me x@y.test or DM me")
        self.assertEqual(got[-1], "dm")

    def test_html_hrefs_are_captured(self):
        html = '<p>hi <a href="https://cal.test/me">book</a></p>'
        self.assertIn("https://cal.test/me", ml.hrefs(html))


class TestMonitorLeadsMain(Base):
    def run_main(self, argv, feed=None, raises=None):
        tmp_leads = self.tmpdir() / "LEADS.md"
        def fake_fetch(url, timeout=20):
            if raises:
                raise raises
            return feed if feed is not None else ATOM_FEED
        with patch.object(ml, "LEADS_FILE", tmp_leads), \
             patch.object(ml, "fetch", fake_fetch), \
             patch.object(ml, "FEED_DELAY_SECONDS", 0):
            rc, out = self.quiet(ml.main, argv)
        return rc, out, tmp_leads

    def test_dry_run_writes_nothing(self):
        rc, out, leads = self.run_main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertFalse(leads.exists())
        self.assertIn("dry run", out)

    def test_real_run_appends_only_hiring_entries(self):
        rc, _, leads = self.run_main(["--limit", "10"])
        self.assertEqual(rc, 0)
        text = leads.read_text()
        self.assertIn("Django monolith", text)
        self.assertNotIn("open to hiring managers", text)   # the [FOR HIRE] post
        self.assertNotIn("pad their diffs", text)           # the discussion post

    def test_second_run_adds_nothing(self):
        tmp_leads = self.tmpdir() / "LEADS.md"
        with patch.object(ml, "LEADS_FILE", tmp_leads), \
             patch.object(ml, "fetch", lambda url, timeout=20: ATOM_FEED), \
             patch.object(ml, "FEED_DELAY_SECONDS", 0):
            self.quiet(ml.main, [])
            first = tmp_leads.read_text()
            _, out = self.quiet(ml.main, [])
            self.assertEqual(tmp_leads.read_text(), first)
        self.assertIn("nothing new", out)

    def test_require_contact_drops_posts_with_no_route(self):
        rc, out, leads = self.run_main(["--dry-run", "--require-contact"])
        self.assertIn("1 new", out)   # only the email post qualifies

    def test_every_feed_failing_returns_nonzero(self):
        rc, out, leads = self.run_main([], raises=urllib.error.URLError("down"))
        self.assertEqual(rc, 1)
        self.assertFalse(leads.exists())
        self.assertIn("every feed failed", out)

    def test_a_rate_limit_is_reported_not_swallowed(self):
        err = urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        rc, _, _ = self.run_main([], raises=err)
        self.assertEqual(rc, 1)


# ── hn_leads ────────────────────────────────────────────────────────────────

class TestHnParsing(unittest.TestCase):
    def test_first_line_skips_blanks(self):
        self.assertEqual(hn_leads.first_line("\n\n  Acme | Dev  \nmore"), "Acme | Dev")

    def test_first_line_clips_and_handles_empties(self):
        self.assertEqual(len(hn_leads.first_line("x" * 400)), 120)
        self.assertEqual(hn_leads.first_line(""), "(no text)")

    def test_top_level_job_post_is_kept(self):
        self.assertTrue(hn_leads.is_job_post(HN_HITS[0], "49522897"))

    def test_the_op_rules_comment_is_not_a_job(self):
        self.assertFalse(hn_leads.is_job_post(HN_HITS[1], "49522897"))

    def test_a_reply_is_not_a_job(self):
        # Nested replies are discussion about a job, sometimes hostile.
        self.assertFalse(hn_leads.is_job_post(HN_HITS[2], "49522897"))

    def test_keying_is_on_the_item_id_not_a_collapsed_url(self):
        entry = hn_leads.to_entry(HN_HITS[0], "src")
        self.assertEqual(entry["uid"], "hn:1")
        self.assertNotEqual(entry["uid"], ml.normalize_url(entry["url"]))

    def test_two_posts_get_distinct_uids(self):
        a = hn_leads.to_entry(HN_HITS[0], "s")["uid"]
        b = hn_leads.to_entry(HN_HITS[3], "s")["uid"]
        self.assertNotEqual(a, b)

    def test_contact_is_extracted(self):
        self.assertIn("email:jobs@acme.test",
                      hn_leads.to_entry(HN_HITS[0], "s")["contact"])

    def test_has_email_separates_an_address_from_an_apply_link(self):
        self.assertTrue(hn_leads.has_email(hn_leads.to_entry(HN_HITS[0], "s")))
        self.assertFalse(hn_leads.has_email(hn_leads.to_entry(HN_HITS[3], "s")))


class TestHnTransport(unittest.TestCase):
    def test_find_thread_ignores_the_non_hiring_sibling_thread(self):
        payload = {"hits": [
            {"objectID": "9", "title": "Ask HN: Who wants to be hired? (September 2026)"},
            {"objectID": "8", "title": "Ask HN: Who is hiring? (September 2026)"}]}
        with patch.object(hn_leads, "_get", lambda url, timeout=30: payload):
            self.assertEqual(hn_leads.find_thread()["objectID"], "8")

    def test_find_thread_raises_when_the_format_changes(self):
        with patch.object(hn_leads, "_get", lambda url, timeout=30: {"hits": []}):
            with self.assertRaises(RuntimeError):
                hn_leads.find_thread()

    def test_comments_are_paginated(self):
        # A one-page fetch returns a silent subset: the thread has 403 comments
        # and Algolia caps a response. Looks complete, is not.
        pages = {
            0: {"hits": [{"objectID": str(i)} for i in range(3)], "nbPages": 2},
            1: {"hits": [{"objectID": str(i)} for i in range(3, 5)], "nbPages": 2},
        }
        def fake_get(url, timeout=30):
            return pages[[p for p in pages if f"page={p}" in url][0]]
        with patch.object(hn_leads, "_get", fake_get):
            self.assertEqual(len(hn_leads.fetch_comments("1")), 5)


class TestHnLeadsMain(Base):
    def run_main(self, argv, leads_text=""):
        leads = self.tmpdir() / "LEADS.md"
        if leads_text:
            leads.write_text(leads_text)
        with patch.object(hn_leads, "LEADS_FILE", leads), \
             patch.object(hn_leads, "find_thread", lambda: HN_STORY), \
             patch.object(hn_leads, "fetch_comments", lambda sid: HN_HITS):
            rc, out = self.quiet(hn_leads.main, argv)
        return rc, out, leads

    def test_dry_run_writes_nothing(self):
        rc, out, leads = self.run_main(["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertFalse(leads.exists())
        self.assertIn("dry run", out)

    def test_counts_email_and_any_route_separately(self):
        _, out, _ = self.run_main(["--dry-run"])
        # 2 job posts (the OP comment and the reply are excluded), 1 with email.
        self.assertIn("2 top-level job posts", out)
        self.assertIn("1 publish an email", out)
        self.assertIn("2 publish any route", out)

    def test_real_run_appends_qualified_posts(self):
        rc, _, leads = self.run_main([])
        self.assertEqual(rc, 0)
        text = leads.read_text()
        self.assertIn("jobs@acme.test", text)
        self.assertIn("Matched: `who-is-hiring`", text)
        self.assertNotIn("Please state the location", text)   # OP rules comment
        self.assertNotIn("Do you sponsor visas", text)        # nested reply

    def test_require_email_drops_link_only_posts(self):
        _, _, leads = self.run_main(["--require-email"])
        self.assertIn("jobs@acme.test", leads.read_text())
        self.assertNotIn("acme.test/jobs", leads.read_text())

    def test_an_already_recorded_item_id_is_not_readded(self):
        # The regression: with URL-based keys this dedupe silently failed and
        # every HN post collapsed to one.
        existing = ("* **[acme]** Acme | Backend Engineer\n"
                    "  - Link: https://news.ycombinator.com/item?id=1\n")
        _, out, leads = self.run_main([], leads_text=existing)
        self.assertIn("1 new", out)
        self.assertEqual(leads.read_text().count("item?id=1"), 1)

    def test_second_run_is_a_no_op(self):
        leads = self.tmpdir() / "LEADS.md"
        with patch.object(hn_leads, "LEADS_FILE", leads), \
             patch.object(hn_leads, "find_thread", lambda: HN_STORY), \
             patch.object(hn_leads, "fetch_comments", lambda sid: HN_HITS):
            self.quiet(hn_leads.main, [])
            first = leads.read_text()
            _, out = self.quiet(hn_leads.main, [])
            self.assertEqual(leads.read_text(), first)
        self.assertIn("nothing new", out)


# ── outreach_agent ──────────────────────────────────────────────────────────

class TestLeadParsing(unittest.TestCase):
    def setUp(self):
        self.entries = oa.parse_leads(LEAD_FIXTURE)

    def test_all_entries_parse(self):
        self.assertEqual(len(self.entries), 3)

    def test_both_the_old_url_and_new_link_shapes_are_read(self):
        self.assertTrue(oa.source_of(self.entries[0]).endswith("/bbb/"))
        self.assertTrue(oa.source_of(self.entries[2]).endswith("/x/"))

    def test_contacts_and_emails_are_split(self):
        self.assertEqual(oa.contacts_of(self.entries[0]), ["email:jobs@acme.test", "dm"])
        self.assertEqual(oa.emails_of(self.entries[0]), ["jobs@acme.test"])

    def test_no_contact_yields_no_email(self):
        self.assertEqual(oa.emails_of(self.entries[1]), [])


class TestQualify(unittest.TestCase):
    def setUp(self):
        self.entries = oa.parse_leads(LEAD_FIXTURE)

    def test_a_hiring_post_with_contact_qualifies(self):
        self.assertEqual(oa.qualify(self.entries[0]), (True, ""))

    def test_hiring_without_contact_is_rejected_with_that_reason(self):
        ok, why = oa.qualify(self.entries[1])
        self.assertFalse(ok)
        self.assertIn("no way to make contact", why)

    def test_a_non_hiring_entry_is_rejected_with_a_different_reason(self):
        ok, why = oa.qualify(self.entries[2])
        self.assertFalse(ok)
        self.assertIn("not a hiring post", why)

    def test_the_two_failure_reasons_are_distinguishable(self):
        # They fail for different reasons and must not collapse into one zero.
        self.assertNotEqual(oa.qualify(self.entries[1])[1],
                            oa.qualify(self.entries[2])[1])


class TestDrafting(unittest.TestCase):
    def test_subject_is_split_when_present(self):
        self.assertEqual(oa.split_subject("Subject: Hi\n\nBody."), ("Hi", "Body."))

    def test_a_missing_subject_is_not_an_error(self):
        self.assertEqual(oa.split_subject("just a body"), ("", "just a body"))

    def test_mailto_encodes_subject_and_body(self):
        link = oa.mailto("a@b.test", "S & T", "x y")
        self.assertTrue(link.startswith("mailto:a@b.test?subject=S%20%26%20T&body=x%20y"))

    def test_prompt_carries_the_offer_verbatim(self):
        entry = oa.parse_leads(LEAD_FIXTURE)[0]
        prompt = oa.build_prompt(entry, "I only do X.")
        self.assertIn("I only do X.", prompt)
        self.assertIn("NO FIT", prompt)   # the model may refuse

    def test_render_attaches_a_send_link_when_there_is_an_address(self):
        entry = oa.parse_leads(LEAD_FIXTURE)[0]
        block = oa.render(entry, "S", "B", "NOW")
        self.assertIn("open in your mail client", block)
        self.assertIn("draft only", block)

    def test_render_says_so_when_there_is_no_address(self):
        entry = oa.parse_leads(LEAD_FIXTURE)[1]
        block = oa.render(entry, "S", "B", "NOW")
        self.assertNotIn("mailto:", block)
        self.assertIn("no email published", block)

    def test_drafted_sources_keys_on_the_source_not_the_title(self):
        entry = oa.parse_leads(LEAD_FIXTURE)[0]
        block = oa.render(entry, "S", "B", "NOW")
        self.assertEqual(oa.drafted_sources(block), {oa.source_of(entry)})
        # An entry that merely mentions a link is not a draft.
        self.assertEqual(oa.drafted_sources(LEAD_FIXTURE), set())


class TestOutreachMain(Base):
    def run_main(self, argv, reply="Subject: Hi\n\nShort body."):
        leads = self.tmpdir() / "LEADS.md"
        drafts = self.tmpdir() / "OUTREACH_DRAFTS.md"
        leads.write_text(LEAD_FIXTURE)
        with patch.object(oa, "LEADS_FILE", leads), \
             patch.object(oa, "DRAFTS_FILE", drafts), \
             patch.object(oa, "complete", lambda prompt, model=None: reply):
            rc, out = self.quiet(oa.main, argv)
        return rc, out, drafts

    def test_about_is_required_and_the_reason_is_stated(self):
        rc, out, drafts = self.run_main(["--about", "   "])
        self.assertEqual(rc, 2)
        self.assertFalse(drafts.exists())
        self.assertIn("--about is required", out)

    def test_a_draft_is_written_with_the_header(self):
        rc, out, drafts = self.run_main(["--about", "I do X."])
        self.assertEqual(rc, 0)
        text = drafts.read_text()
        self.assertIn("Nothing here has been sent", text)
        self.assertIn("Subject:", text)
        self.assertIn("jobs@acme.test", text)

    def test_no_fit_is_reported_and_never_written(self):
        rc, out, drafts = self.run_main(["--about", "I do X."],
                                       reply="NO FIT — wrong stack.")
        self.assertEqual(rc, 0)
        self.assertIn("no fit", out)
        self.assertFalse(drafts.exists())

    def test_redo_is_needed_to_draft_the_same_lead_twice(self):
        leads = self.tmpdir() / "LEADS.md"
        drafts = self.tmpdir() / "OUTREACH_DRAFTS.md"
        leads.write_text(LEAD_FIXTURE)
        with patch.object(oa, "LEADS_FILE", leads), \
             patch.object(oa, "DRAFTS_FILE", drafts), \
             patch.object(oa, "complete", lambda prompt, model=None: "Subject: S\n\nB"):
            self.quiet(oa.main, ["--about", "I do X."])
            once = drafts.read_text()
            self.quiet(oa.main, ["--about", "I do X."])
            self.assertEqual(drafts.read_text(), once)

    def test_a_model_failure_is_reported_and_writes_nothing(self):
        def boom(prompt, model=None):
            raise RuntimeError("gateway down")
        leads = self.tmpdir() / "LEADS.md"
        drafts = self.tmpdir() / "OUTREACH_DRAFTS.md"
        leads.write_text(LEAD_FIXTURE)
        with patch.object(oa, "LEADS_FILE", leads), \
             patch.object(oa, "DRAFTS_FILE", drafts), \
             patch.object(oa, "complete", boom):
            rc, _ = self.quiet(oa.main, ["--about", "I do X."])
        self.assertEqual(rc, 1)
        self.assertFalse(drafts.exists())

    def test_list_mode_calls_no_model(self):
        def explode(prompt, model=None):
            raise AssertionError("--list must not call the model")
        leads = self.tmpdir() / "LEADS.md"
        leads.write_text(LEAD_FIXTURE)
        with patch.object(oa, "LEADS_FILE", leads), \
             patch.object(oa, "complete", explode):
            rc, out = self.quiet(oa.main, ["--list"])
        self.assertEqual(rc, 0)
        self.assertIn("qualified", out)


class TestNoSendCapability(Base):
    """The design decision the whole project rests on, pinned as a test.

    If someone adds a send mode, this fails loudly rather than shipping quietly.
    """

    def test_no_send_or_post_flag_is_accepted(self):
        # Behavioural, not textual. The docstring *discusses* --send at length in
        # order to refuse it, so grepping the source for the string proves
        # nothing about behaviour -- it only punishes documenting the decision.
        # What matters is that argparse rejects the flag, which is what a user
        # typing it would actually hit.
        for flag in ("--send", "--post"):
            with self.assertRaises(SystemExit, msg=f"{flag} was accepted"):
                self.quiet(oa.main, ["--about", "x", flag])

    def test_the_refusal_is_documented_rather_than_only_absent(self):
        # The inverse of the usual test: the string SHOULD be present, as prose
        # explaining why there is no such mode. An undocumented refusal is one
        # the next person re-adds.
        src = (HERALD / "outreach_agent.py").read_text()
        self.assertIn("no --send and no --post", src)

    def test_no_send_function_exists(self):
        self.assertFalse(hasattr(oa, "send"))

    def test_the_agent_cannot_reach_the_network_itself(self):
        # It shells out to bin/ai; it has no HTTP client of its own.
        src = (HERALD / "outreach_agent.py").read_text()
        self.assertNotIn("import urllib.request", src)
        self.assertNotIn("smtplib", src)

    def test_the_only_transport_is_the_shared_interface(self):
        self.assertTrue(str(oa.AI).endswith("bin/ai"))

    def test_ai_is_found_by_walking_up_not_by_counting_parents(self):
        # The move into projects/ broke a fixed-depth lookup. This pins the fix.
        self.assertEqual(oa.find_ai(), HERALD.parents[1] / "bin" / "ai")


if __name__ == "__main__":
    unittest.main()
