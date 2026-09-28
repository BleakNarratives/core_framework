"""The taps rite: an append-only burial that cannot shame the person it buries.

A streak that reaches 3 or more buys one extra day of grace in
`src/skill/gambit.py`. When the count resets, that is the whole estate, and the
record shows a bare `streak: 0` with nothing noting what stood there. `tools/taps`
writes the missing note: an append-only obituary, a gambit-shaped tombstone, and a
salute page.

These tests pin the parts that would fail quietly:

  * a second burial must not erase the first one's line — append-only is a mode,
    not a promise, so it is checked by writing twice;
  * the 48h figure taps prints must be the rule gambit actually applies, which is
    checked by driving a real `InstarEngine` in a temp store rather than trusting
    the constant;
  * `--gambit-store` must be a read. `InstarEngine._load` persists a fresh state
    file when it cannot find one, so a careless implementation would plant a fake
    grave — this asserts the bytes are untouched;
  * the eulogy must stay tender. `ODDS_BRIDGE.md` forbids streak shaming, so the
    shaming tokens are an invariant, not a style note.

Everything here is offline and deterministic: temp roots, `--at` for timestamps,
and no TTS process unless a test opts in (none do).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAPS_DIR = ROOT / "tools" / "taps"
TAPS_PY = TAPS_DIR / "taps.py"
TAPS_HTML = TAPS_DIR / "taps.html"
AT = "2026-09-22T12:00:00+00:00"


def load_taps():
    """Load the tool from its file, without touching `sys.path`.

    Same reason as `tests/test_decision_log.py`: `tools/` holds several standalone
    scripts with generic module-level names, and importing them through the package
    is how one tool's constant ends up shadowing another's. The module is registered
    under a name nothing else will claim and unregistered on failure.
    """
    if not TAPS_PY.is_file():
        raise ImportError(f"taps moved; expected {TAPS_PY}")
    spec = importlib.util.spec_from_file_location("taps_under_test", TAPS_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


taps = load_taps()
from src.skill import gambit  # noqa: E402

OBIT_SLOT_RE = re.compile(r"const OBIT_JSON = (\".*?\");", re.S)


def injected_obit(html: str) -> dict:
    """Read the page's obituary the way the page does: JSON.parse on the literal.

    The slot is a JSON string literal holding JSON, so the literal the browser
    evaluates is exactly what `json.loads` sees here. Anything that breaks that
    round-trip would show the demo obituary in a real browser while looking correct
    in the file, which is the failure this reproduces.
    """
    match = OBIT_SLOT_RE.search(html)
    if match is None:
        raise AssertionError("page lost its OBIT_JSON slot")
    return json.loads(json.loads(match.group(1)))


class TapsWiringTest(unittest.TestCase):
    def test_tool_tree_is_where_this_suite_expects_it(self):
        self.assertTrue(TAPS_PY.is_file(), f"missing {TAPS_PY}")
        self.assertTrue(TAPS_HTML.is_file(), f"missing {TAPS_HTML}")
        self.assertTrue((TAPS_DIR / "README.md").is_file(), "taps README is missing")

    def test_salute_count_matches_the_page(self):
        html = TAPS_HTML.read_text(encoding="utf-8")
        match = re.search(r"const RIBBONS = (\d+);", html)
        self.assertIsNotNone(match, "taps.html lost its RIBBONS constant")
        self.assertEqual(
            int(match.group(1)),
            taps.SALUTE_COUNT,
            "SALUTE_COUNT in taps.py and RIBBONS in taps.html have drifted apart",
        )


class TapsRecordTest(unittest.TestCase):
    def test_second_burial_does_not_erase_the_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            argv = [
                "--skill", "med-triage-copilot", "--user", "bubba",
                "--streak", "4", "--unit", "weeks", "--root", tmp,
                "--at", AT, "--quiet",
            ]
            self.assertEqual(taps.main(argv), 0)
            self.assertEqual(taps.main(argv + ["--unit", "days"]), 0)

            lines = (Path(tmp) / "obituary.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2, "obituary is not append-only")
            first, second = (json.loads(line) for line in lines)
            self.assertEqual(first["streak"]["days"], 28)
            self.assertEqual(second["streak"]["days"], 4)

            grave = taps.grave_path(Path(tmp), "bubba", "med-triage-copilot")
            self.assertEqual(len(grave.read_text(encoding="utf-8").splitlines()), 2)

    def test_obituary_records_self_reported_provenance_and_grace(self):
        with tempfile.TemporaryDirectory() as tmp:
            taps.main([
                "--skill", "med-triage-copilot", "--user", "bubba",
                "--streak", "4", "--unit", "weeks", "--root", tmp,
                "--at", AT, "--quiet",
            ])
            obit = json.loads(
                (Path(tmp) / "obituary.jsonl").read_text(encoding="utf-8").strip()
            )
            self.assertEqual(obit["provenance"]["source"], "self-reported")
            self.assertFalse(obit["provenance"]["verified"])
            self.assertEqual(obit["grace"]["hours"], 48)
            self.assertEqual(obit["grace"]["rule"], taps.GRACE_RULE)
            self.assertEqual(obit["grace"]["spent_until"], "2026-09-24T12:00:00+00:00")
            self.assertFalse(obit["gambit"]["found"])
            # A record written before any browser ran cannot claim the rite was heard.
            self.assertEqual(obit["audio"]["status"], taps.AUDIO_UNVERIFIED)
            self.assertFalse(obit["audio"]["verified"])

    def test_negative_streak_is_a_usage_error(self):
        result = subprocess.run(
            [sys.executable, str(TAPS_PY), "--streak", "-1", "--root", tempfile.gettempdir()],
            capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


class TapsAudioNoteTest(unittest.TestCase):
    """A browser fact recorded without rewriting the record it belongs to."""

    def _bury(self, tmp):
        return [
            "--skill", "med-triage-copilot", "--user", "bubba",
            "--streak", "4", "--unit", "weeks", "--root", tmp,
            "--at", AT, "--quiet",
        ]

    def test_audio_note_records_silence_and_leaves_the_obituary_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taps.main(self._bury(tmp))
            obituaries = root / "obituary.jsonl"
            before = hashlib.sha256(obituaries.read_bytes()).hexdigest()

            taps.main(self._bury(tmp) + [
                "--audio-status", "unavailable", "--audio-reason", "no Web Audio",
            ])

            lines = (root / "audio_notes.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            note = json.loads(lines[0])
            self.assertEqual(note["type"], "audio_note")
            self.assertEqual(note["status"], "unavailable")
            self.assertEqual(note["reason"], "no Web Audio")
            self.assertEqual(note["obituary_lines"], 1, "the note must point at its burial")
            self.assertFalse(note["provenance"]["verified"])

            self.assertEqual(
                hashlib.sha256(obituaries.read_bytes()).hexdigest(),
                before,
                "recording the silence rewrote the obituary",
            )
            self.assertEqual(
                len(obituaries.read_text(encoding="utf-8").splitlines()), 1,
                "an audio note must not bury the streak a second time",
            )

            taps.main(self._bury(tmp) + ["--audio-status", "ok"])
            self.assertEqual(
                len((root / "audio_notes.jsonl").read_text(encoding="utf-8").splitlines()),
                2,
                "audio notes are not append-only",
            )

    def test_note_counts_the_burials_it_belongs_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taps.main(self._bury(tmp))
            taps.main(self._bury(tmp) + ["--audio-status", "unavailable"])
            note = json.loads((root / "audio_notes.jsonl").read_text(encoding="utf-8").strip())
            self.assertEqual(note["matched_obituaries"], 1, "note lost track of its burial")

            # A note about a burial that is not in this root still records the fact,
            # and says out loud that it stands alone rather than looking attached.
            lonely = subprocess.run(
                [sys.executable, str(TAPS_PY), "--skill", "never-buried-here", "--user", "bubba",
                 "--root", tmp, "--audio-status", "ok"],
                capture_output=True, text=True, timeout=60, check=False,
            )
            self.assertEqual(lonely.returncode, 0, lonely.stdout + lonely.stderr)
            self.assertIn("warning", lonely.stdout)
            lines = (root / "audio_notes.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2, "the standalone note should still be kept")
            self.assertEqual(json.loads(lines[-1])["matched_obituaries"], 0)

    def test_unknown_audio_status_is_a_usage_error(self):
        result = subprocess.run(
            [sys.executable, str(TAPS_PY), "--audio-status", "probably",
             "--root", tempfile.gettempdir()],
            capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


class TapsGambitBoundaryTest(unittest.TestCase):
    """The rule taps restates, and the file taps promises not to touch."""

    def _state(self, store: Path, user: str, skill: str, streak: int, history=None) -> Path:
        path = store / f"{user}__{skill}.json"
        path.write_text(json.dumps({
            "user_id": user, "skill": skill, "instar": 1, "xp": 0, "streak": streak,
            "best_ms": None, "last_challenge_at": None, "next_due_at": None,
            "history": history or [], "calibrated": False, "unlocked_at": {"1": 1.0},
        }), encoding="utf-8")
        return path

    def test_grace_hours_match_what_gambit_actually_applies(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "instars"
            store.mkdir()
            user, skill = "taps-selftest", "gambit-rule"
            self._state(store, user, skill, streak=2)

            engine = gambit.InstarEngine(user_id=user, store_dir=str(store))
            question = gambit.CHALLENGE_BANK["_generic"][0]
            result = engine.submit(skill, " ".join(question["a_keywords"]), elapsed_ms=12000)

            self.assertTrue(result["passed"], "self-test answer should pass")
            self.assertEqual(result["streak"], 3, "streak did not reach the grace threshold")
            due_in = result["next_challenge_due"] - time.time()
            self.assertAlmostEqual(
                due_in,
                taps.grace_hours(result["streak"]) * 3600,
                delta=10,
                msg="taps' restated 48h rule no longer matches gambit's own behavior",
            )
            self.assertEqual(taps.grace_hours(2), 24)
            self.assertEqual(taps.grace_hours(3), 48)

    def test_gambit_store_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "instars"
            store.mkdir()
            live = self._state(store, "bubba", "med-triage-copilot", streak=4)
            before = hashlib.sha256(live.read_bytes()).hexdigest()

            taps.main([
                "--skill", "med-triage-copilot", "--user", "bubba",
                "--streak", "4", "--unit", "weeks", "--root", str(Path(tmp) / "grave"),
                "--gambit-store", str(store), "--at", AT, "--quiet",
            ])

            after = hashlib.sha256(live.read_bytes()).hexdigest()
            self.assertEqual(before, after, "taps wrote to the live gambit state")
            obit = json.loads(
                (Path(tmp) / "grave" / "obituary.jsonl").read_text(encoding="utf-8").strip()
            )
            self.assertTrue(obit["gambit"]["found"])
            self.assertEqual(obit["gambit"]["streak"], 4)
            self.assertEqual(obit["gambit"]["instar"], 1)

    def test_missing_gambit_state_reads_as_absent_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "instars"
            self.assertIsNone(taps.read_gambit_state(store, "nobody", "nothing"))
            self.assertFalse(store.exists(), "a read created the store directory")

    def test_run_is_named_from_the_ledger_the_miss_ended(self):
        history = [
            {"type": "challenge", "instar": 2, "q": "a", "ratio": 1.0,
             "points": 15, "passed": True, "elapsed_ms": 24800, "ts": 1000.0},
            {"type": "challenge", "instar": 2, "q": "b", "ratio": 0.5,
             "points": 0, "passed": False, "elapsed_ms": 30000, "ts": 2000.0},
            {"type": "challenge", "instar": 2, "q": "c", "ratio": 1.0,
             "points": 15, "passed": True, "elapsed_ms": 11800, "ts": 3000.0},
            {"type": "challenge", "instar": 3, "q": "d", "ratio": 1.0,
             "points": 20, "passed": True, "elapsed_ms": 15200, "ts": 4000.0},
            {"type": "challenge", "instar": 3, "q": "the one that did not land",
             "ratio": 0.2, "points": 0, "passed": False, "elapsed_ms": 9000, "ts": 5000.0},
        ]
        run = taps.streak_run(history)
        self.assertEqual(run["passes"], 2, "run should stop at the earlier miss")
        self.assertEqual(run["points"], 35)
        self.assertEqual(run["fastest_ms"], 11800)
        self.assertEqual((run["instar_first"], run["instar_last"]), (2, 3))
        self.assertEqual(run["last_call"]["question"], "the one that did not land")
        self.assertEqual(run["started"], "1970-01-01")

    def test_run_is_absent_when_the_streak_is_still_standing(self):
        standing = [{"type": "challenge", "q": "a", "points": 10, "passed": True, "ts": 1.0}]
        self.assertIsNone(taps.streak_run(standing), "a living streak has no obituary")
        self.assertIsNone(taps.streak_run([]))
        self.assertIsNone(taps.streak_run(None))
        self.assertIsNone(taps.streak_run([{"type": "challenge", "q": "a", "passed": False}]))
        self.assertIsNone(taps.streak_run(["not a dict", 7]), "malformed ledger must not raise")

    def test_obituary_and_eulogy_name_what_the_run_earned(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "instars"
            store.mkdir()
            self._state(store, "bubba", "med-triage-copilot", streak=0, history=[
                {"type": "challenge", "instar": 3, "q": "hydrate at oomf", "ratio": 1.0,
                 "points": 20, "passed": True, "elapsed_ms": 11800, "ts": 1758000000.0},
                {"type": "challenge", "instar": 3, "q": "the last call", "ratio": 0.2,
                 "points": 0, "passed": False, "elapsed_ms": 9000, "ts": 1758600000.0},
            ])
            taps.main([
                "--skill", "med-triage-copilot", "--user", "bubba",
                "--streak", "4", "--unit", "weeks", "--root", str(Path(tmp) / "grave"),
                "--gambit-store", str(store), "--at", AT, "--quiet",
            ])
            obit = json.loads(
                (Path(tmp) / "grave" / "obituary.jsonl").read_text(encoding="utf-8").strip()
            )
            run = obit["gambit"]["run"]
            self.assertEqual(run["passes"], 1)
            self.assertEqual(run["points"], 20)
            self.assertEqual(obit["gambit"]["history_len"], 2)

            text = taps.eulogy(obit)
            self.assertIn("1 consecutive passes", text)
            self.assertIn("20 points", text)
            self.assertIn("fastest answer 11.8s", text)
            self.assertIn("did not land", text)
            for token in taps.SHAMING_TOKENS:
                self.assertNotIn(token, text.lower())

    def test_no_state_file_says_so_instead_of_inventing_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            taps.main([
                "--skill", "med-triage-copilot", "--streak", "4", "--unit", "weeks",
                "--root", tmp, "--at", AT, "--quiet",
            ])
            obit = json.loads(
                (Path(tmp) / "obituary.jsonl").read_text(encoding="utf-8").strip()
            )
            self.assertFalse(obit["gambit"]["found"])
            self.assertIsNone(obit["gambit"]["run"])
            self.assertIn("self-reported", obit["gambit"]["note"])
            self.assertNotIn("What the run left", taps.eulogy(obit))


class TapsTendernessTest(unittest.TestCase):
    def test_eulogy_never_shames(self):
        for streak in (0, 1, 3, 4):
            obit = taps.build_obituary(
                skill="med-triage-copilot", user="bubba", streak=streak, unit="weeks",
                ended_on=taps.parse_at(AT), recorded_at=taps.parse_at(AT),
            )
            text = taps.eulogy(obit).lower()
            for token in taps.SHAMING_TOKENS:
                self.assertNotIn(token, text, f"eulogy shames with {token!r} at streak={streak}")
            self.assertIn(str(taps.grace_hours(streak)), text)


class TapsRitePageTest(unittest.TestCase):
    def test_rendered_page_carries_the_obituary_and_stays_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "rite.html"
            taps.main([
                "--skill", "med-triage-copilot", "--user", "bubba",
                "--streak", "4", "--unit", "weeks", "--root", tmp,
                "--at", AT, "--html", str(out), "--quiet",
            ])
            html = out.read_text(encoding="utf-8")
            self.assertNotIn(taps.OBIT_PLACEHOLDER, html, "obituary slot was not filled")
            obit = injected_obit(html)
            self.assertEqual(obit["skill"], "med-triage-copilot")
            self.assertEqual(obit["streak"]["days"], 28)
            self.assertEqual(obit["grace"]["hours"], 48)
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)

    def test_template_without_the_slot_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.html"
            bad.write_text("<html>no slot here</html>", encoding="utf-8")
            with self.assertRaises(ValueError):
                taps.render_rite(bad, {"skill": "x"})

    def test_page_resumes_the_audio_context_and_explains_silence(self):
        """A suspended AudioContext makes every scheduled note inaudible.

        The page cannot be heard from this test, but it can be checked for the two
        things that caused the silence: never calling resume(), and failing quietly
        when audio is unavailable at all.
        """
        html = TAPS_HTML.read_text(encoding="utf-8")
        self.assertIn("audio.resume()", html, "a suspended context is never resumed")
        self.assertIn('id="audiohint"', html, "silence has no explanation on the page")
        self.assertIn("recordSilence", html, "silence is displayed but never recorded")
        self.assertIn('id="audiorecord"', html, "the record has nowhere to show the audio status")
        # resume must happen before any note is scheduled, not after
        ensure = html.index("async function ensureAudio()")
        thud = html.index("async function thud()")
        self.assertLess(ensure, thud)

    def test_salute_page_is_keyboard_reachable_and_motion_aware(self):
        html = TAPS_HTML.read_text(encoding="utf-8")
        self.assertIn('aria-live="polite"', html, "the ribbon count is never announced")
        self.assertIn("prefers-reduced-motion", html, "the motion preference is ignored")
        self.assertIn("focus-visible", html, "keyboard focus is invisible")
        # Space with the button focused salutes once, not twice: the window handler
        # stands down when a button already handled the key, and ignores key repeat.
        self.assertIn('closest("button")', html)
        self.assertIn("e.repeat", html)

    def test_page_opens_standalone_with_a_demo_obituary(self):
        html = TAPS_HTML.read_text(encoding="utf-8")
        self.assertIn(taps.OBIT_SLOT, html, "unrendered page would be invalid JS")
        self.assertIn("DEMO_OBIT", html)
        # Mirrors the page's try/catch: an uninjected slot fails to parse and the
        # demo obituary takes over instead of the page breaking.
        with self.assertRaises(ValueError):
            injected_obit(html)


# ── the page's own runtime, where a JavaScript engine exists ─────
# No browser is available here (no Chromium, Chrome, or Firefox), and none should be
# installed to check a decoration. A DOM shim cannot judge how the prairie looks, but
# it can catch the failures that are invisible in the file: a salute that fires twice
# from one keypress, a rite that loops when a reader asked for less motion, and an
# audio failure that leaves no trace. Skipped rather than failed where node is absent.
PAGE_SHIM = """
const els = {};
const listeners = {window: [], canvas: [], elements: []};
function mk(id){
  const el = {id, textContent: "", innerHTML: "", attrs: {},
    getAttribute(k){ return this.attrs[k]; }, setAttribute(k, v){ this.attrs[k] = v; },
    classList: {on: false, add(){ this.on = true; }, remove(){ this.on = false; }},
    addEventListener(ev, fn){ listeners.elements.push([id, ev, fn]); },
    closest(sel){ return (id === "salute" && sel === "button") ? el : null; },
    focus(){}};
  els[id] = el; return el;
}
global.els = els; global.listeners = listeners; global.RAF_COUNT = 0;
global.MATCH_REDUCED = %(reduced)s;
const ctxProxy = new Proxy({}, {get: (t, k) => k in t ? t[k] : (() => ({addColorStop(){}})), set: () => true});
global.document = {getElementById: (id) => els[id] || mk(id), addEventListener(){}, createElement: () => mk("tmp")};
global.window = {addEventListener(ev, fn){ listeners.window.push([ev, fn]); }, devicePixelRatio: 1};
global.window.matchMedia = () => ({matches: MATCH_REDUCED, addEventListener(){}});
global.requestAnimationFrame = () => { RAF_COUNT++; return 0; };
"""

PAGE_PRELUDE = """
const key = (targetId, repeat) => listeners.window.find(([e]) => e === "keydown")[1](
  {code: "Space", repeat: !!repeat, preventDefault(){}, target: els[targetId] || null});
const click = () => listeners.elements.find(([id, ev]) => id === "salute" && ev === "click")[2]();
const tick = () => new Promise(r => setTimeout(r, 5));
"""

PAGE_RITE = """
(async () => {
  key("salute", false); await tick();          // button focused: must not stack with its own click
  const focused = raised;
  click(); await tick();
  const clicked = raised - focused;
  key("stage", false); await tick();
  const fromKey = raised - focused - clicked;
  key("stage", true); await tick();            // held key must not repeat
  const held = raised - focused - clicked - fromKey;
  for (let i = raised; i < 21; i++) await click();
  await new Promise(r => setTimeout(r, 600));
  console.log(JSON.stringify({focused_press: focused, click: clicked, key_press: fromKey,
    held_press: held, raf_calls: RAF_COUNT, raised: raised, folded: folded,
    eulogy: !!els.eulogy.classList.on, audio_record: els.audiorecord.textContent,
    label: els.salute.getAttribute("aria-label")}));
})();
"""


@unittest.skipUnless(shutil.which("node"), "no JavaScript engine to run the page in")
class TapsPageRuntimeTest(unittest.TestCase):
    def _rite(self, reduced: bool) -> dict:
        html = TAPS_HTML.read_text(encoding="utf-8")
        script = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        script = script.replace(
            'const canvas = document.getElementById("stage");',
            'const canvas = {clientWidth: 800, clientHeight: 600, getContext: () => ctxProxy,'
            ' addEventListener(ev, fn){ listeners.canvas.push([ev, fn]); }};',
        )
        shim = PAGE_SHIM.replace("%(reduced)s", "true" if reduced else "false")
        with tempfile.TemporaryDirectory() as tmp:
            driver = Path(tmp) / "rite.js"
            driver.write_text(shim + script + PAGE_PRELUDE + PAGE_RITE, encoding="utf-8")
            result = subprocess.run(
                [shutil.which("node"), str(driver)],
                capture_output=True, text=True, timeout=120, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_full_rite_runs_once_per_press_without_looping(self):
        out = self._rite(reduced=False)
        self.assertEqual(out["focused_press"], 0, "space with the button focused saluted twice")
        self.assertEqual(out["click"], 1)
        self.assertEqual(out["key_press"], 1)
        self.assertEqual(out["held_press"], 0, "a held key repeated the salute")
        self.assertEqual(out["raised"], taps.SALUTE_COUNT)
        self.assertEqual(out["raf_calls"], 1, "the prairie should loop exactly once here")
        self.assertEqual(out["label"], "start the rite over")

    def test_reduced_motion_requests_no_animation_frame(self):
        out = self._rite(reduced=True)
        self.assertEqual(out["raf_calls"], 0, "reduced motion still looped the prairie")
        self.assertEqual(out["raised"], taps.SALUTE_COUNT)
        self.assertTrue(out["folded"], "ribbons should settle at once under reduced motion")
        self.assertTrue(out["eulogy"], "the eulogy should arrive promptly under reduced motion")

    def test_silent_rite_is_recorded_on_the_page(self):
        # The shim has no Web Audio, so every run is a silent one: the page must
        # leave a visible record of it rather than only being quiet.
        out = self._rite(reduced=False)
        self.assertIn("audio: unavailable", out["audio_record"])
        self.assertIn("--audio-status unavailable", out["audio_record"])


if __name__ == "__main__":
    unittest.main()
