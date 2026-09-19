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

# Measured 2026-09-17, verbatim in shape: given `--about-file ABOUT.md`, six of ten
# replies were the prompt itself returned as the completion. It contains both marker
# phrases on purpose -- the check matches either one, and a fixture with only one
# would not prove that.
ECHOED_PROMPT = (
    "Write one short outreach email from me to someone who posted about work.\n"
    "\nTheir post:\n"
    "  title: Lumen Labs | Robotics / Hardware Engineer | San Francisco, CA\n"
    "  posted by: Daniel_Van_Zant\n"
    "  source: https://news.ycombinator.com/item?id=49667711\n"
    "\nWhat I actually offer, and the only thing you may claim about me:\n"
    "\"\"\"\n"
    "I make LLM coding agents cheap enough to run on hardware you already own.\n"
    "\"\"\"")

# Written the way the *old* contact_hints() wrote it: an ATS URL under a bare
# `link:` prefix, from before application forms had a category of their own. This is
# what the existing LEADS.md is full of -- 144 link hints -- so the reader has to
# grade that data by the new rule, not by the prefix it was stored with.
APPLY_ONLY_LEAD = """* **[u/ats]** Hiring: platform engineer
  - Link: https://news.ycombinator.com/item?id=999
  - Matched: `who-is-hiring`
  - Contact: link:https://jobs.ashbyhq.com/acme/1234
"""

# A company domain and a job document, and nothing else. This is the shape of the
# 13 leads that took the count from 45 to 35, written the old way on purpose.
VENUE_ONLY_LEAD = """* **[u/co]** Hiring: backend engineer
  - Link: https://news.ycombinator.com/item?id=998
  - Matched: `who-is-hiring`
  - Contact: link:https://acme.test, link:https://acme.notion.site/backend-jd
"""

# A profile page and nothing else: a weaker route than an address, still a route.
PROFILE_ONLY_LEAD = """* **[u/person]** Hiring: contract python work
  - Link: https://news.ycombinator.com/item?id=997
  - Matched: `who-is-hiring`
  - Contact: link:https://www.linkedin.com/in/someone
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
        # A plain company page is a venue, and the prefix now says so. It is still
        # recorded -- what changed is that it no longer reads as a way in.
        self.assertIn("venue:https://shop.test/contact",
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


class TestEmploymentType(unittest.TestCase):
    """A label, never a filter -- see `ml.employment_type` for the measurement behind it."""

    def test_full_time_markers(self):
        for title in ("Acme | Backend | Remote | Full-time | $180k",
                      "Acme | Dev | W2 only",
                      "Acme | Dev | Salaried, permanent"):
            self.assertEqual(ml.employment_type(title), "full-time", title)

    def test_contract_markers(self):
        for title in ("Acme | Dev | Contract (6 months)",
                      "Acme | Dev | Part-time | Remote",
                      "Acme | Fractional CTO",
                      "Acme | Dev | 1099 / hourly"):
            self.assertEqual(ml.employment_type(title), "contract", title)

    def test_a_post_offering_both_is_labelled_both(self):
        # Both of these are real titles from LEADS.md.
        self.assertEqual(ml.employment_type(
            "Catalyst·Wayfare AI | Agent Builder | Remote | Full-time / Part-time / Contract"),
            "both")
        self.assertEqual(ml.employment_type(
            "Squoosh.AI | Full-Stack Engineer (full-time, REMOTE) + PhD Researcher (part-time)"),
            "both")

    def test_silence_is_unstated_not_assumed_full_time(self):
        # 13 of the 35 live leads say nothing about it. Guessing on their behalf is
        # how a count starts flattering itself.
        self.assertEqual(ml.employment_type("Acme | Backend Engineer | Remote (US)"),
                         "unstated")
        self.assertEqual(ml.employment_type(""), "unstated")

    def test_a_draft_records_what_the_post_offered(self):
        entry = oa.parse_leads(LEAD_FIXTURE)[0]
        block = oa.render(entry, "S", "B", "NOW")
        self.assertIn("- Employment as stated in the post:", block)

    def test_there_is_no_employment_filter_flag(self):
        # THE DECISION, pinned behaviourally like the --send test. A contract-only
        # filter over the live file would hide 18 of 35 leads and match nothing that
        # was not already there, so the label informs a human instead of the tool
        # quietly shrinking its own list. If someone adds the filter, this fails.
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            with self.assertRaises(SystemExit):
                oa.main(["--list", "--employment", "contract"])


class TestApplicationForms(unittest.TestCase):
    """A form is a route; it is not a person.

    The URLs below are taken from the real LEADS.md, not invented, because the line
    has to be drawn from what the sources actually publish: these hosts were 53
    distinct domains and 144 link hints on 2026-09-17.
    """

    FORMS = (
        "https://jobs.ashbyhq.com/anterior/1163af7a-d1d6-41db",
        "https://careers.tether.io/o/backend-engineer-wallets-100-remote",
        "https://grnh.se/26cvuixl3us",
        "https://greenzie.applytojob.com/apply/UdRcDlWSzs/Robotics",
        "https://careers.auroraer.com/postings/8c289ab6-283b",
        "https://jobs.deel.com/swingvision/job-details/c2cc0f23",
        "https://egmn.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1",
        "https://form.jotform.com/250488763186166",
        "https://valkyrie-aero.breezy.hr/",
        "https://endlessaccess.bamboohr.com/careers/33",
        "https://obi9.ai/jobs/full-stack-engineer",
        "https://www.vcluster.com/careers?ashby_jid=516c8859-83be-4535",
        "https://newtonstree.ai/job/forward-deploy-engineer",
        "https://acme.test/jobs",
    )

    PEOPLE = (
        "https://www.linkedin.com/in/davidzhao/",
        "https://github.com/closeio",
        "https://shop.test/contact",
        "https://cal.test/me",
        "https://squoosh.ai",
        "https://mycreportfolio.com/samiksha",
        "https://drive.google.com/file/d/1Q6IQrVH3llpEqX0CRt/view",
        "mailto:jobs@acme.test",
    )

    def test_application_forms_are_recognised(self):
        for url in self.FORMS:
            self.assertTrue(ml.is_application_form(url), url)

    def test_a_persons_own_page_is_not_swept_up(self):
        # The false positive is the expensive one: a real lead silently marked
        # unreachable, with nothing on screen to say it happened.
        for url in self.PEOPLE:
            self.assertFalse(ml.is_application_form(url), url)

    def test_a_form_is_recorded_under_its_own_prefix(self):
        got = ml.contact_hints({"body": "apply at https://jobs.ashbyhq.com/acme/1",
                                "links": []})
        self.assertEqual(got, ["apply:https://jobs.ashbyhq.com/acme/1"])

    def test_a_person_page_is_recorded_as_a_profile(self):
        got = ml.contact_hints({"body": "ping https://linkedin.com/in/someone",
                                "links": []})
        self.assertEqual(got, ["profile:https://linkedin.com/in/someone"])

    def test_a_homepage_or_a_job_document_is_a_venue(self):
        # The 45 -> 35 correction. Of the 45 that survived the apply-form rule, 13
        # published no address and no DM, and what they had was a company domain or
        # a job document. A homepage is a place, not a person.
        for url in ("https://openrent.co.uk",
                    "https://squoosh.ai",
                    "https://desert-bearskin-26d.notion.site/JD",
                    "https://techcrunch.com/2026/02/19/freeform-raises-67m/",
                    "https://drive.google.com/file/d/1Q6IQ/view",
                    "https://langfuse.com"):
            self.assertEqual(ml.classify_link(url), "venue", url)

    def test_a_profile_page_is_a_route(self):
        for url in ("https://www.linkedin.com/in/davidzhao/",
                    "https://github.com/Samiksha-sudo"):
            self.assertEqual(ml.classify_link(url), "profile", url)
            self.assertTrue(ml.reaches_a_person(f"profile:{url}"), url)

    def test_an_old_bare_link_prefix_is_re_derived(self):
        # THE REGRESSION. A homepage written by the old code sat under a bare
        # `link:` and counted as contact for every entry already in the file.
        self.assertFalse(ml.reaches_a_person("link:https://openrent.co.uk"))
        self.assertTrue(ml.reaches_a_person("link:https://linkedin.com/in/x"))

    def test_a_venue_prefix_is_not_a_route(self):
        self.assertFalse(ml.reaches_a_person("venue:https://squoosh.ai"))

    def test_route_kind_names_all_five(self):
        self.assertEqual(ml.route_kind("email:a@b.test"), "email")
        self.assertEqual(ml.route_kind("dm"), "dm")
        self.assertEqual(ml.route_kind("venue:https://a.test"), "venue")
        self.assertEqual(ml.route_kind("apply:https://jobs.ashbyhq.com/a/1"), "apply")
        self.assertEqual(ml.route_kind("profile:https://github.com/x"), "profile")

    def test_reaches_a_person_reads_an_old_link_prefixed_form(self):
        # THE REGRESSION. Trusting the stored prefix would keep counting exactly the
        # links this exists to stop counting, for every entry already in the file.
        self.assertFalse(ml.reaches_a_person("link:https://jobs.ashbyhq.com/acme/1"))
        self.assertFalse(ml.reaches_a_person("apply:https://jobs.ashbyhq.com/acme/1"))

    def test_reaches_a_person_for_every_other_kind_of_hint(self):
        self.assertTrue(ml.reaches_a_person("email:jobs@acme.test"))
        self.assertTrue(ml.reaches_a_person("link:https://linkedin.com/in/x"))
        self.assertTrue(ml.reaches_a_person("dm"))


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

    def test_counts_email_person_and_form_separately(self):
        _, out, _ = self.run_main(["--dry-run"])
        # 2 job posts (the OP comment and the reply are excluded): one publishes an
        # address, the other publishes nothing but an application form.
        self.assertIn("2 top-level job posts", out)
        self.assertIn("1 publish an email", out)
        self.assertIn("1 reach a person", out)
        self.assertIn("1 apply-form only", out)

    def test_an_application_form_alone_is_not_a_way_to_reach_anyone(self):
        # THE BUG: this used to read "2 publish any route", i.e. two employers you
        # could write to, when the second was an ATS intake form.
        _, out, _ = self.run_main(["--dry-run"])
        self.assertIn("2 published some route", out)
        self.assertNotIn("2 reach a person", out)

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


class TestReplyValidation(unittest.TestCase):
    """A reply has to look like an email before it is written as one.

    Before this existed the only test was "does the text start with NO FIT", so a
    reply that was the *prompt echoed back* was written to OUTREACH_DRAFTS.md as
    copy, with an empty subject and a mailto body of "Write one short outreach
    email...". Six of ten replies did that in one run.
    """

    def test_an_echoed_prompt_is_not_an_email(self):
        self.assertIn("echoed", oa.not_an_email("", ECHOED_PROMPT))

    def test_the_echo_check_needs_only_one_marker(self):
        # Not every echo will reproduce both sentences.
        half = "What I actually offer, and the only thing you may claim about me:\n" \
               "I do backend work."
        self.assertIn("echoed", oa.not_an_email("Subject: hi", half))

    def test_a_reply_with_no_subject_line_is_rejected(self):
        # The prompt requires "Subject: <subject>" as the first line. The echoes
        # never had one, which is itself the cheapest signal that it is not an email.
        self.assertIn("Subject", oa.not_an_email("", "A short honest body."))

    def test_a_body_far_over_the_cap_is_rejected(self):
        self.assertIn("120", oa.not_an_email("Subject: S", "word " * 250))

    def test_an_empty_reply_is_rejected(self):
        self.assertEqual(oa.not_an_email("Subject: S", "   "), "empty reply")

    def test_a_normal_email_passes(self):
        self.assertEqual(
            oa.not_an_email("Subject: untangling your monolith",
                            "You mentioned a Django monolith. I refactor those. "
                            "Could I see the repo?"), "")

    def test_the_cap_is_not_so_tight_that_it_rejects_a_real_email(self):
        # The prompt asks for under 120 words. A 150-word draft is verbose, not
        # malformed, and discarding it would trade one failure for another.
        self.assertEqual(oa.not_an_email("Subject: S", "word " * 150), "")


class TestRateLimitRetries(unittest.TestCase):
    """Measured 2026-09-17: 8 of 10 calls in one run were lost to a per-minute token
    ceiling, and every one of them carried the provider's own statement of how long
    to wait. The run wrote nothing."""

    # The real wording, including its tail. The tail matters: see the billing test.
    GROQ_TPM = ('model call failed: gateway HTTP 429: Rate limit reached for model '
                '`openai/gpt-oss-120b` in organization `org_01k407mvmdfpq8m0ak32bn1wxk` '
                'service tier `on_demand` on tokens per minute (TPM): Limit 8000, '
                'Used 6651, Requested 2309. Please try again in 7.199999999s. Need '
                'more tokens? Upgrade to Dev Tier today at '
                'https://console.groq.com/settings/billing')
    NO_CREDIT = ('model call failed: gateway HTTP 429: {"error": {"message": '
                 '"You have no credits remaining. Add credits to continue."}}')

    def test_the_providers_own_wait_is_read_out_of_the_message(self):
        self.assertAlmostEqual(oa.retry_after_seconds(self.GROQ_TPM), 7.2, places=1)

    def test_a_rate_limit_that_mentions_billing_is_still_retried(self):
        # THE BUG I WROTE. A quota check on the bare word "billing" matched this
        # rate-limit message's upgrade link, so 429s that said exactly how long to
        # wait were treated as a dead account. The retry never fired once, and
        # nothing on screen said so. Pinned with the provider's real wording.
        self.assertIn("billing", self.GROQ_TPM)
        self.assertIsNotNone(oa.retry_after_seconds(self.GROQ_TPM))

    def test_an_account_out_of_credit_is_not_retried(self):
        # A 429 again, and no amount of waiting fixes billing. Retrying here would
        # turn a fast failure into a slow one.
        self.assertIsNone(oa.retry_after_seconds(self.NO_CREDIT))

    def test_an_ordinary_failure_is_not_retried(self):
        self.assertIsNone(oa.retry_after_seconds("gateway HTTP 500: boom"))

    def test_a_429_with_no_hint_still_pauses_briefly(self):
        self.assertEqual(oa.retry_after_seconds("gateway HTTP 429: rate limit"),
                         oa.MIN_WAIT)

    def test_a_retry_happens_and_waits_the_stated_time(self):
        slept, calls = [], []

        def flaky(prompt, model=None):
            calls.append(prompt)
            if len(calls) == 1:
                raise RuntimeError(self.GROQ_TPM)
            return "Subject: S\n\nBody."

        with patch.object(oa, "complete", flaky):
            got = oa.complete_with_retries("p", None, retries=3, sleep=slept.append)
        self.assertEqual(got, "Subject: S\n\nBody.")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(slept), 1)
        self.assertAlmostEqual(slept[0], 7.2, places=1)

    def test_a_quota_429_raises_without_sleeping(self):
        slept = []

        def dead(prompt, model=None):
            raise RuntimeError(self.NO_CREDIT)

        with patch.object(oa, "complete", dead):
            with self.assertRaises(RuntimeError):
                oa.complete_with_retries("p", None, retries=3, sleep=slept.append)
        self.assertEqual(slept, [])

    def test_it_gives_up_after_the_retry_budget(self):
        calls = []

        def always(prompt, model=None):
            calls.append(1)
            raise RuntimeError(self.GROQ_TPM)

        with patch.object(oa, "complete", always):
            with self.assertRaises(RuntimeError):
                oa.complete_with_retries("p", None, retries=2, sleep=lambda s: None)
        self.assertEqual(len(calls), 3)   # the first attempt plus two retries


class TestContactLineShowsOnlyRoutes(unittest.TestCase):
    """The one line you actually read must not offer a venue as a way to a person."""

    def contact_line(self, block):
        return next(l for l in block.splitlines() if l.startswith("- Contact:"))

    def test_a_venue_never_appears_on_the_contact_line(self):
        entry = oa.parse_leads(VENUE_ONLY_LEAD)[0]
        block = oa.render(entry, "", "body", "NOW")
        self.assertIn("nothing published reaches a person", self.contact_line(block))
        self.assertNotIn("http", self.contact_line(block))

    def test_places_are_still_listed_just_not_as_contact(self):
        entry = oa.parse_leads(VENUE_ONLY_LEAD)[0]
        block = oa.render(entry, "", "body", "NOW")
        self.assertIn("- Published (places, not routes):", block)
        self.assertIn("acme.test", block)

    def test_an_address_and_a_form_are_shown_apart(self):
        entry = oa.parse_leads(
            "* **[u/mix]** Hiring: python\n"
            "  - Link: https://news.ycombinator.com/item?id=1\n"
            "  - Matched: `hiring`\n"
            "  - Contact: email:jobs@acme.test, apply:https://jobs.ashbyhq.com/a/1\n")[0]
        block = oa.render(entry, "S", "body", "NOW")
        self.assertEqual(self.contact_line(block), "- Contact: email:jobs@acme.test")
        self.assertIn("Published (places, not routes)", block)
        self.assertIn("apply:https://jobs.ashbyhq.com/a/1", block)


class TestResumableRuns(Base):
    """A batch has to remember what it answered, or it cannot make progress.

    Measured 2026-09-17: three batches of 15/17/10 made 42 calls covering 19 distinct
    leads, because `todo` could only exclude leads already *drafted*. Every batch
    restarted at the first unrefused lead and spent its limit on repeats.
    """

    def run_in(self, d, argv, reply="NO FIT — wrong stack.", complete=None):
        leads = d / "LEADS.md"
        if not leads.is_file():
            leads.write_text(LEAD_FIXTURE)
        fake = complete if complete is not None else (lambda p, model=None: reply)
        with patch.object(oa, "LEADS_FILE", leads), \
             patch.object(oa, "DRAFTS_FILE", d / "OUTREACH_DRAFTS.md"), \
             patch.object(oa, "STATE_FILE", d / ".herald_state.json"), \
             patch.object(oa, "complete", fake):
            rc, out = self.quiet(oa.main, argv)
        return rc, out, d / "OUTREACH_DRAFTS.md", d / ".herald_state.json"

    def test_a_refusal_is_remembered(self):
        _, _, _, state = self.run_in(self.tmpdir(), ["--about", "I do X."])
        self.assertTrue(state.is_file())
        self.assertIn("no_fit", state.read_text())

    def test_the_next_batch_calls_nothing_when_everything_is_answered(self):
        # THE BUG. This used to re-ask the same lead every batch, for ever.
        d = self.tmpdir()
        self.run_in(d, ["--about", "I do X."])
        calls = []
        _, out, _, _ = self.run_in(d, ["--about", "I do X."],
                                   complete=lambda p, model=None: calls.append(p))
        self.assertEqual(calls, [])
        self.assertIn("already answered", out)

    def test_redo_goes_round_again_on_purpose(self):
        d = self.tmpdir()
        self.run_in(d, ["--about", "I do X."])
        calls = []
        self.run_in(d, ["--about", "I do X.", "--redo"],
                    complete=lambda p, model=None: (calls.append(p),
                                                    "NO FIT — again")[1])
        self.assertEqual(len(calls), 1)

    def test_a_transport_failure_is_not_treated_as_answered(self):
        # A failure says nothing about the lead, so the next batch may try it again.
        d = self.tmpdir()

        def boom(prompt, model=None):
            raise RuntimeError("gateway HTTP 500: upstream down")

        _, _, _, state = self.run_in(d, ["--about", "I do X."], complete=boom)
        self.assertIn("failed", state.read_text())
        self.assertIn("500", state.read_text())
        _, out, _, _ = self.run_in(d, ["--about", "I do X."],
                                  reply="NO FIT — wrong stack.")
        self.assertNotIn("already answered", out)

    def test_a_corrupt_state_file_does_not_stop_the_run(self):
        d = self.tmpdir()
        (d / ".herald_state.json").write_text("{not json at all")
        rc, out, _, state = self.run_in(d, ["--about", "I do X."])
        self.assertEqual(rc, 0)
        self.assertIn("ignoring unreadable", out)
        self.assertIn("no_fit", state.read_text())      # recovered, and rewrote it

    def test_the_run_says_how_many_it_attempted(self):
        _, out, _, _ = self.run_in(self.tmpdir(), ["--about", "I do X."])
        self.assertIn("1 lead(s) attempted this run", out)


class TestApplicationFormsAreNotLeads(unittest.TestCase):
    """A form is a route; it is not a person. The distinction the count got wrong."""

    def setUp(self):
        self.entry = oa.parse_leads(APPLY_ONLY_LEAD)[0]

    def test_an_apply_only_lead_does_not_qualify(self):
        ok, why = oa.qualify(self.entry)
        self.assertFalse(ok)
        self.assertIn("application form", why)

    def test_that_reason_differs_from_having_no_contact_at_all(self):
        # Both mean "cannot write to this", and they are different facts. Collapsing
        # them is how a form came to look like a route.
        nothing = oa.parse_leads(LEAD_FIXTURE)[1]
        self.assertNotEqual(oa.qualify(self.entry)[1], oa.qualify(nothing)[1])

    def test_the_hint_is_still_recorded_it_is_just_not_reachable(self):
        self.assertEqual(oa.reachable_of(self.entry), [])
        self.assertEqual(oa.contacts_of(self.entry),
                         ["link:https://jobs.ashbyhq.com/acme/1234"])

    def test_render_says_the_links_are_not_a_way_in(self):
        block = oa.render(self.entry, "", "body", "NOW")
        self.assertIn("reply on the thread", block)

    def test_a_venue_only_lead_does_not_qualify(self):
        entry = oa.parse_leads(VENUE_ONLY_LEAD)[0]
        ok, why = oa.qualify(entry)
        self.assertFalse(ok)
        self.assertIn("no direct route", why)
        self.assertIn("venue", why)      # the kinds present are named

    def test_a_venue_only_reason_differs_from_a_form_only_one(self):
        # "a form" and "a homepage" call for different next actions.
        venue = oa.parse_leads(VENUE_ONLY_LEAD)[0]
        form = oa.parse_leads(APPLY_ONLY_LEAD)[0]
        self.assertNotEqual(oa.qualify(venue)[1], oa.qualify(form)[1])

    def test_the_venues_are_still_recorded_on_the_entry(self):
        # Nothing is hidden: the lead is skipped, and the file still shows what it
        # published, which is how you decide whether to reply on the thread anyway.
        entry = oa.parse_leads(VENUE_ONLY_LEAD)[0]
        self.assertIn("link:https://acme.test", oa.contacts_of(entry))
        self.assertEqual(oa.reachable_of(entry), [])

    def test_a_profile_only_lead_still_qualifies(self):
        # LinkedIn and GitHub are platforms with a messaging path, so a profile is
        # a weaker route than an address but still a route.
        entry = oa.parse_leads(PROFILE_ONLY_LEAD)[0]
        self.assertEqual(oa.qualify(entry), (True, ""))
        self.assertEqual(oa.reachable_of(entry),
                         ["link:https://www.linkedin.com/in/someone"])

    def test_a_lead_with_an_address_and_a_form_still_qualifies(self):
        entry = oa.parse_leads(
            "* **[u/mix]** Hiring: python\n"
            "  - Link: https://news.ycombinator.com/item?id=1\n"
            "  - Matched: `hiring`\n"
            "  - Contact: email:jobs@acme.test, link:https://jobs.ashbyhq.com/a/1\n")[0]
        self.assertEqual(oa.qualify(entry), (True, ""))
        self.assertEqual(oa.reachable_of(entry), ["email:jobs@acme.test"])

    def test_list_mode_reports_it_as_skipped_not_as_a_lead(self):
        leads = self._tmp() / "LEADS.md"
        leads.write_text(APPLY_ONLY_LEAD)
        with patch.object(oa, "LEADS_FILE", leads), \
             patch.object(oa, "STATE_FILE", self._tmp() / ".herald_state.json"):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = oa.main(["--list"])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("0 qualified", out)
        self.assertIn("application form", out)

    def _tmp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

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
    """main(), end to end, with every path it writes redirected.

    STATE_FILE is patched here too, and that is not decoration. It is the resume
    memory, so a test that leaves it real writes verdicts into the project directory
    and the *next* test reads them -- eight unrelated tests failed exactly that way
    when the resume feature landed, all of them reporting FileNotFoundError on a
    drafts file that had correctly never been written.
    """

    def run_main(self, argv, reply="Subject: Hi\n\nShort body."):
        leads = self.tmpdir() / "LEADS.md"
        drafts = self.tmpdir() / "OUTREACH_DRAFTS.md"
        leads.write_text(LEAD_FIXTURE)
        with patch.object(oa, "LEADS_FILE", leads), \
             patch.object(oa, "DRAFTS_FILE", drafts), \
             patch.object(oa, "STATE_FILE", self.tmpdir() / ".herald_state.json"), \
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

    def test_an_echoed_prompt_is_reported_and_never_written(self):
        # THE BUG. `--about-file ABOUT.md` produced seven of these in one run and
        # the tool wrote all seven as drafts, reporting a 70% fit rate that was
        # really a count of how often the model echoed the question.
        rc, out, drafts = self.run_main(["--about", "I do X."], reply=ECHOED_PROMPT)
        self.assertFalse(drafts.exists(), "the prompt was written as a draft")
        self.assertNotIn("drafted", out)
        self.assertIn("not written", out)

    def test_a_run_of_only_malformed_replies_is_not_a_success(self):
        # Exiting 0 here would report a broken pipeline as a run that found nothing.
        rc, _, _ = self.run_main(["--about", "I do X."], reply=ECHOED_PROMPT)
        self.assertEqual(rc, 1)

    def test_a_body_with_no_subject_is_not_written(self):
        rc, out, drafts = self.run_main(["--about", "I do X."],
                                       reply="A short body with no subject line.")
        self.assertFalse(drafts.exists())
        self.assertIn("Subject", out)

    def test_a_good_reply_is_still_written_alongside_a_bad_one(self):
        # The guard must not become a filter that discards real drafts: one lead
        # qualifies in the fixture, so a good reply still has to reach the file.
        rc, out, drafts = self.run_main(["--about", "I do X."],
                                       reply="Subject: hi\n\nA short honest body.")
        self.assertEqual(rc, 0)
        self.assertIn("appended 1 draft", out)
        self.assertIn("A short honest body.", drafts.read_text())

    def test_redo_is_needed_to_draft_the_same_lead_twice(self):
        leads = self.tmpdir() / "LEADS.md"
        drafts = self.tmpdir() / "OUTREACH_DRAFTS.md"
        leads.write_text(LEAD_FIXTURE)
        with patch.object(oa, "LEADS_FILE", leads), \
             patch.object(oa, "DRAFTS_FILE", drafts), \
             patch.object(oa, "STATE_FILE", self.tmpdir() / ".herald_state.json"), \
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
             patch.object(oa, "STATE_FILE", self.tmpdir() / ".herald_state.json"), \
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
             patch.object(oa, "STATE_FILE", self.tmpdir() / ".herald_state.json"), \
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
