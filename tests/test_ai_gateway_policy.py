"""Tests for the free-only routing policy, the key reaper, and loadout validation.

These three are one feature, not three. `policy.toml` declares which pools are
free, `ai_gateway.py` refuses to route to anything else, `ai_gateway_reap.py`
probes only the ones still allowed, and `loadout` refuses to emit a class naming
a refused pool. Break any link and the guarantee is gone while the others still
look fine, which is exactly the failure mode this suite exists to catch.

Offline and hermetic: every path is redirected into a temp dir, `call_upstream`
is stubbed so no test can reach a provider, and the reaper's network function is
replaced by a counter that would fail loudly if a non-free pool were probed.
No live keys, no live services, no spend.

The three tests worth knowing about:
  * `test_free_only_fails_closed_without_a_policy_file` — the direction of the
    failure matters more than the refusal itself.
  * `test_free_tier_quota_is_not_death` — the bug this whole change set grew out
    of. Google 429s a free key that has simply burned its daily allowance, and
    that used to quarantine the key as dead auth for an hour.
  * `test_reaper_never_probes_a_non_free_pool` — the reaper makes real API
    calls. Sweeping a paid pool would be the most expensive thing in the stack.
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import time
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))


def load_script(name: str):
    """Import an extensionless script from bin/ as a module.

    `bin/loadout` has no .py suffix because it is a command on PATH.
    importlib.import_module cannot see those, so the file is loaded explicitly
    rather than renaming it just to suit a test.
    """
    import importlib.util
    from importlib.machinery import SourceFileLoader
    path = BIN / name
    loader = SourceFileLoader(f"_bin_{name}", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def write_policy(path: Path, free_only: str = "true",
                 providers: dict | None = None) -> None:
    providers = providers or {
        "groq": {"tier": "free"},
        "openrouter": {"tier": "free"},
        "puter": {"tier": "paid", "reason": "402 subscription required"},
        "swarms": {"tier": "unknown", "reason": "402 since 2026-09-25"},
    }
    lines = [f"free_only = {free_only}", ""]
    for name, entry in providers.items():
        lines.append(f"[providers.{name}]")
        lines.append(f'tier = "{entry["tier"]}"')
        if entry.get("reason"):
            lines.append(f'reason = "{entry["reason"]}"')
        lines.append("")
    path.write_text("\n".join(lines))


class PolicyHarness(unittest.TestCase):
    """Points the gateway at a temp policy/vault, and stubs the network."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.policy = root / "policy.toml"
        self.vault = root / "vault.json"
        self.health = root / "pool_health.json"
        write_policy(self.policy)

        self.vault.write_text(json.dumps({
            "keys": {
                "groq": {"key": "gsk_livekey0000000000000000000001", "status": "live"},
                "puter": {"key": "puter_key000000000000000000000001", "status": "live"},
                "swarms": {"key": "swarms_key00000000000000000000001", "status": "live"},
                "google": {"key": "AIzaRetiredKey0000000000000000000",
                           "status": "retired",
                           "retire_reason": "key leaked",
                           "retired_at": "2026-09-07"},
            },
            "keys_by_provider": {
                "groq": ["gsk_livekey0000000000000000000001",
                         "gsk_livekey0000000000000000000002"],
                "puter": ["puter_key000000000000000000000001"],
                "swarms": ["swarms_key00000000000000000000001"],
                # The retired key is still sitting in the pool, which is the bug
                # the retired-status gate exists to close.
                "google": ["AIzaRetiredKey0000000000000000000"],
            },
        }))

        self.gw = importlib.import_module("ai_gateway")
        self._saved = (self.gw.POLICY_PATH, self.gw.VAULT_JSON,
                       self.gw.POOL_HEALTH, self.gw.POLICY_CACHE_KEYS
                       if hasattr(self.gw, "POLICY_CACHE_KEYS") else None)
        self.gw.POLICY_PATH = self.policy
        self.gw.VAULT_JSON = self.vault
        self.gw.POOL_HEALTH = self.health
        self.gw._policy_cache.clear()
        self.calls: list[tuple] = []

        def _fake_call_upstream(provider, model, body, timeout=60, meta=None):
            self.calls.append((provider, model))
            if meta is not None:
                meta["provider"] = provider
                meta["model"] = model
            return 200, {"choices": [{"message": {"content": "ok"}}]}

        self.gw.call_upstream = _fake_call_upstream
        for table in ("_key_state", "_rotation", "_provider_dead"):
            getattr(self.gw, table).clear()

    def tearDown(self):
        self.gw.POLICY_PATH, self.gw.VAULT_JSON, self.gw.POOL_HEALTH = (
            self._saved[0], self._saved[1], self._saved[2])
        self.gw._policy_cache.clear()
        self.tmp.cleanup()


class TestPolicyGate(PolicyHarness):
    def test_free_only_defaults_on_when_the_file_is_missing(self):
        self.policy.unlink()
        self.gw._policy_cache.clear()
        self.assertTrue(self.gw.free_only(),
                        "a missing policy must fail closed, not open")

    def test_undeclared_pool_is_refused(self):
        # 'cerebras' is absent from the temp policy entirely.
        reason = self.gw.refusal_reason("cerebras")
        self.assertTrue(reason, "an undeclared pool must be refused")
        self.assertIn("tier=unknown", reason)

    def test_free_pool_is_allowed(self):
        self.assertEqual(self.gw.refusal_reason("groq"), "")

    def test_pinned_paid_pool_is_refused_without_calling_upstream(self):
        code, payload = self.gw.route("gpt-5.4-nano", {"messages": []},
                                      provider="puter")
        self.assertEqual(code, 403)
        self.assertIn("free-only", payload["error"]["message"])
        self.assertEqual(self.calls, [], "a refused pool must never be called")

    def test_auto_chain_skips_non_free_pools(self):
        self.gw.AUTO_CHAIN = ("groq", "puter", "swarms", "openrouter")
        code, _ = self.gw.route("default", {"messages": []}, provider="auto")
        self.assertEqual(code, 200)
        called = [p for p, _ in self.calls]
        self.assertIn("groq", called)
        self.assertNotIn("puter", called)
        self.assertNotIn("swarms", called)

    def test_auto_with_nothing_routable_names_every_reason(self):
        self.gw.AUTO_CHAIN = ("puter", "swarms")
        code, payload = self.gw.route("default", {"messages": []},
                                      provider="auto")
        self.assertEqual(code, 503)
        message = payload["error"]["message"]
        self.assertIn("puter", message)
        self.assertIn("swarms", message)
        self.assertEqual(self.calls, [])

    def test_free_only_false_lets_a_paid_pool_through(self):
        write_policy(self.policy, free_only="false")
        self.gw._policy_cache.clear()
        code, _ = self.gw.route("gpt-5.4-nano", {"messages": []}, provider="puter")
        self.assertEqual(code, 200)
        self.assertEqual([p for p, _ in self.calls], ["puter"])


class TestRetiredAndReapedKeys(PolicyHarness):
    def test_retired_key_never_reaches_a_pool(self):
        pools = self.gw._pools_from_vault()
        self.assertNotIn("google", pools,
                         "a retired key must not be routable")
        self.assertNotIn("AIzaRetiredKey0000000000000000000",
                         pools.get("groq", []))

    def test_live_keys_survive(self):
        self.assertEqual(len(self.gw._pools_from_vault()["groq"]), 2)

    def test_reaped_fingerprint_is_dropped_from_the_pool(self):
        doomed = self.gw._key_fingerprint("gsk_livekey0000000000000000000002")
        self.health.write_text(json.dumps({
            "schema": "concierge.pool_health/1",
            "providers": {"groq": {"keys": {
                doomed: {"state": "unpaid", "http": 402}}}},
        }))
        self.assertEqual(len(self.gw.pool_for("groq")), 1)

    def test_reaper_fail_open_is_safe(self):
        # Missing health file: routing continues exactly as before. The reaper
        # is an optimisation, so breaking it must not black out the gateway.
        self.assertEqual(len(self.gw.pool_for("groq")), 2)

    def test_rate_limited_key_is_never_reaped(self):
        self.health.write_text(json.dumps({
            "providers": {"groq": {"keys": {
                self.gw._key_fingerprint("gsk_livekey0000000000000000000002"):
                    {"state": "quota", "http": 429}}}},
        }))
        self.assertEqual(len(self.gw.pool_for("groq")), 2)

    def test_reaped_verdict_expires(self):
        import os
        doomed = self.gw._key_fingerprint("gsk_livekey0000000000000000000002")
        self.health.write_text(json.dumps({
            "providers": {"groq": {"keys": {
                doomed: {"state": "unpaid", "http": 402}}}},
        }))
        stale = self.gw.HEALTH_TTL + 3600
        os.utime(self.health, (stale, stale))
        self.assertEqual(len(self.gw.pool_for("groq")), 2,
                         "a key fixed upstream must come back on its own")


class TestReaper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.reap = importlib.import_module("ai_gateway_reap")
        self.gw = importlib.import_module("ai_gateway")
        # PROVIDERS and pool_for get swapped below, and ai_gateway is a shared
        # module object across the whole suite. Restoring them is not tidiness:
        # leaking a stub pool_for makes every later test in the run see one key
        # where it expects two, and the failure lands in an unrelated class.
        self._saved = (self.gw.POLICY_PATH, self.gw.VAULT_JSON,
                       self.gw.POOL_HEALTH, self.gw.PROVIDERS,
                       self.gw.FALLBACK_MODEL, self.gw.pool_for)
        self.gw.POLICY_PATH = root / "policy.toml"
        self.gw.VAULT_JSON = root / "vault.json"
        self.gw.POOL_HEALTH = root / "pool_health.json"
        self.gw.VAULT_JSON.write_text(json.dumps({"keys_by_provider": {}}))
        write_policy(self.gw.POLICY_PATH, providers={
            "groq": {"tier": "free"},
            "puter": {"tier": "paid", "reason": "402 subscription required"},
            "swarms": {"tier": "unknown", "reason": "402"},
        })
        self.gw._policy_cache.clear()
        self.probed: list[str] = []

    def tearDown(self):
        (self.gw.POLICY_PATH, self.gw.VAULT_JSON, self.gw.POOL_HEALTH,
         self.gw.PROVIDERS, self.gw.FALLBACK_MODEL,
         self.gw.pool_for) = self._saved
        self.gw._policy_cache.clear()
        self.tmp.cleanup()

    def test_free_tier_quota_is_not_death(self):
        # The bug this change set exists to fix. Google says exactly this, at
        # 429, for a free key that has burned its daily allowance.
        state = self.reap._classify(
            '{"error":{"code":429,"message":"You exceeded your current quota"}}',
            429)
        self.assertEqual(state, "quota")
        self.assertNotIn(state, self.gw.DEAD_STATES)

    def test_zero_balance_is_still_death(self):
        self.assertEqual(
            self.reap._classify('{"error":{"code":429,"message":"insufficient_quota"}}',
                                429),
            "unpaid")

    def test_payment_required_is_unpaid(self):
        self.assertEqual(
            self.reap._classify('{"message":"Payment required. Visit your billing tab."}',
                                402), "unpaid")

    def test_bad_auth_is_death(self):
        self.assertEqual(self.reap._classify("Invalid API Key", 401), "auth-dead")

    def test_provider_outage_is_not_the_keys_fault(self):
        # A 5xx must never retire a key, or a bad afternoon empties the vault.
        for code in (500, 502, 503):
            state = self.reap._classify("upstream boom", code)
            self.assertEqual(state, "upstream")
            self.assertNotIn(state, self.gw.DEAD_STATES)

    def test_reaper_never_probes_a_non_free_pool(self):
        self._saved_probe_key = self.reap.probe_key

        def _record(provider, key):
            self.probed.append(provider)
            return {"state": "live", "http": 200, "model": "m", "detail": ""}

        self.reap.probe_key = _record
        self.gw.PROVIDERS = {"groq": "https://example.invalid",
                             "puter": "https://example.invalid",
                             "swarms": "https://example.invalid"}
        self.gw.FALLBACK_MODEL = {"groq": "m", "puter": "m", "swarms": "m"}
        self.gw.pool_for = lambda p: ["a-key-that-was-never-sent"] \
            if p in self.gw.PROVIDERS else []
        report = self.reap.reap(dry_run=True)
        self.assertEqual(self.probed, ["groq"],
                         f"only free pools may be probed; got {self.probed}")
        self.assertFalse(report["providers"]["puter"]["probed"])
        self.assertIn("would spend money",
                      report["providers"]["puter"]["skipped"])
        self.assertIn("tier=unknown", report["providers"]["swarms"]["skipped"])


class TestLoadoutValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.loadout = load_script("loadout")
        self.gw = importlib.import_module("ai_gateway")
        self._saved = self.gw.POLICY_PATH
        self.gw.POLICY_PATH = root / "policy.toml"
        write_policy(self.gw.POLICY_PATH)
        self.gw._policy_cache.clear()
        self.loadout.LOADOUTS = root / "loadouts.toml"
        self.tmp_root = root

    def tearDown(self):
        self.gw.POLICY_PATH = self._saved
        self.gw._policy_cache.clear()
        self.tmp.cleanup()

    def _registry(self, block: str) -> dict:
        self.loadout.LOADOUTS.write_text(
            'schema = "loadouts/1"\n\n' + block)
        return self.loadout.load_all()

    def test_auto_is_accepted_because_it_names_no_pool(self):
        self.assertEqual(self.loadout.check_model("secondary", "auto", "x"), [])

    def test_bare_model_is_rejected(self):
        problems = self.loadout.check_model("primary", "gpt-4o-mini", "x")
        self.assertEqual(len(problems), 1)
        self.assertIn("no 'provider::' prefix", problems[0])

    def test_paid_pool_is_rejected(self):
        problems = self.loadout.check_model("primary", "puter::gpt-5.4-nano", "x")
        self.assertTrue(problems)
        self.assertIn("free-only", problems[0])

    def test_unknown_pool_is_rejected(self):
        problems = self.loadout.check_model("primary", "swarms::qwen", "x")
        self.assertTrue(problems)

    def test_free_pool_is_accepted(self):
        self.assertEqual(
            self.loadout.check_model("primary", "groq::openai/gpt-oss-120b", "x"), [])

    def test_class_without_primary_fails(self):
        data = self._registry(
            '[loadouts.half]\nsecondary = "auto"\n')
        self.assertTrue(self.loadout.check_all(data))

    def test_secondary_equal_to_primary_fails(self):
        # The most common copy-paste slip, and a silently useless slot.
        data = self._registry(
            '[loadouts.dup]\n'
            'primary = "groq::openai/gpt-oss-120b"\n'
            'secondary = "groq::openai/gpt-oss-120b"\n')
        problems = self.loadout.check_all(data)
        self.assertTrue(any("identical to primary" in p for p in problems))

    def test_roles_are_validated_too(self):
        data = self._registry(
            '[loadouts.top]\n'
            'primary = "groq::openai/gpt-oss-120b"\n'
            'secondary = "auto"\n'
            '\n[loadouts.top.roles.bad]\n'
            'primary = "puter::gpt-5.4-nano"\n'
            'secondary = "auto"\n')
        problems = self.loadout.check_all(data)
        self.assertTrue(any("roles.bad" in p for p in problems),
                        f"a bad role must fail the class: {problems}")

    def test_real_registry_validates(self):
        # Guards the file this suite was written for.
        self.loadout.LOADOUTS = Path.home() / ".config" / "ai" / "loadouts.toml"
        if not self.loadout.LOADOUTS.exists():
            self.skipTest("no loadouts.toml installed")
        self.assertEqual(self.loadout.check_all(self.loadout.load_all()), [])


SAMPLE_CONFIG = '''base_url = "http://127.0.0.1:7071"

[models]
# a hand-written comment that must survive
default = "auto"
fast = "mistral::mistral-small-latest"

[headless]
max_chars = 6000
'''


class TestGatewayEmit(PolicyHarness):
    """emit_gateway rewrites a file people also edit by hand.

    Both tests here are regressions. The first version of this function rebuilt
    the [models] table from scratch and on its SECOND run deleted every preset
    the user had written there. Silent deletion on the second run is the part
    that matters: the first run looks fine, so nothing catches it until later.
    """

    def setUp(self):
        super().setUp()
        self.config = Path(self.tmp.name) / "config.toml"
        self.config.write_text(SAMPLE_CONFIG)
        self.loadout = load_script("loadout")
        self.loadout.AI_CONFIG = self.config
        self.loadout.AIDER_CONF = Path(self.tmp.name) / ".aider.conf.yml"
        self.registry = {
            "loadouts": {"solo": {"primary": "groq::openai/gpt-oss-120b",
                                  "secondary": "auto"}},
        }

    def test_existing_presets_and_comments_survive(self):
        for _ in range(3):
            self.loadout.emit_gateway(self.registry, dry=False)
        text = self.config.read_text()
        self.assertIn("fast = ", text)
        self.assertIn("default = ", text)
        self.assertIn("a hand-written comment that must survive", text)
        self.assertIn("[headless]", text)

    def test_emit_is_idempotent(self):
        for _ in range(3):
            self.loadout.emit_gateway(self.registry, dry=False)
        text = self.config.read_text()
        self.assertEqual(text.count(self.loadout.BLOCK_BEGIN), 1)
        self.assertEqual(text.count(self.loadout.BLOCK_END), 1)
        self.assertEqual(text.count("solo = "), 1)

    def test_result_is_still_valid_toml(self):
        self.loadout.emit_gateway(self.registry, dry=False)
        parsed = tomllib.loads(self.config.read_text())
        self.assertEqual(parsed["models"]["solo"], "groq::openai/gpt-oss-120b")
        self.assertEqual(parsed["models"]["fast"], "mistral::mistral-small-latest")
        self.assertEqual(parsed["headless"]["max_chars"], 6000)

    def test_backup_is_written_before_overwriting(self):
        self.loadout.emit_gateway(self.registry, dry=False)
        baks = list(self.config.parent.glob("config.toml.bak_*"))
        self.assertTrue(baks, "a config rewriter must leave the old version behind")
        self.assertEqual(baks[0].read_text(), SAMPLE_CONFIG)

    def test_aider_managed_keys_are_not_duplicated(self):
        # Last-one-wins in YAML, so a duplicate key still behaves — which is
        # exactly why it survives review and confuses whoever reads it next.
        self.loadout.AIDER_CONF.write_text(
            "# my notes\nmodel: old\nweak-model: old\n"
            "openai-api-base: http://old\nopenai-api-key: old\nauto-commits: false\n")
        self.loadout.emit_aider("solo", self.registry["loadouts"]["solo"], False)
        text = self.loadout.AIDER_CONF.read_text()
        for key in ("model:", "weak-model:", "openai-api-base:", "openai-api-key:"):
            self.assertEqual(text.count(f"\n{key}"), 1, f"{key} appears more than once")
        self.assertIn("auto-commits: false", text)
        self.assertIn("# my notes", text)

    def test_dry_run_writes_nothing(self):
        self.loadout.emit_gateway(self.registry, dry=True)
        self.assertEqual(self.config.read_text(), SAMPLE_CONFIG)
        self.assertEqual(list(self.config.parent.glob("*.bak_*")), [])


class TestCostAccounting(unittest.TestCase):
    def setUp(self):
        self.trace = importlib.import_module("ai_trace")
        self.tmp = tempfile.TemporaryDirectory()
        self._saved = self.trace.POLICY_PATH
        self.trace.POLICY_PATH = Path(self.tmp.name) / "policy.toml"

    def tearDown(self):
        self.trace.POLICY_PATH = self._saved
        self.tmp.cleanup()

    def test_paid_pool_is_not_reported_as_free(self):
        # puter and cerebras were both in a hardcoded FREE_PROVIDERS set while
        # answering 402. A confidently wrong $0.00 is worse than a blank.
        write_policy(self.trace.POLICY_PATH, providers={
            "groq": {"tier": "free"},
            "puter": {"tier": "paid"},
            "cerebras": {"tier": "paid"},
        })
        self.trace._policy_cache.clear()
        cost, basis = self.trace.estimate_cost("puter", "gpt-5.4-nano", 100, 100)
        self.assertIsNone(cost)
        self.assertEqual(basis, "unknown")
        cost, basis = self.trace.estimate_cost("cerebras", "gpt-oss-120b", 1, 1)
        self.assertIsNone(cost)

    def test_free_pool_is_still_free(self):
        write_policy(self.trace.POLICY_PATH, providers={"groq": {"tier": "free"}})
        self.trace._policy_cache.clear()
        self.assertEqual(self.trace.estimate_cost("groq", "gpt-oss-120b", 1, 1),
                         (0.0, "free-tier"))

    def test_missing_policy_does_not_claim_free(self):
        self.trace._policy_cache.clear()
        cost, basis = self.trace.estimate_cost("groq", "gpt-oss-120b", 1, 1)
        self.assertIsNone(cost, "fail toward 'unknown', not toward 'free'")

    def test_free_suffix_still_wins(self):
        # An OpenRouter ':free' id is billed free regardless of tier wording.
        write_policy(self.trace.POLICY_PATH,
                     providers={"openrouter": {"tier": "unknown"}})
        self.trace._policy_cache.clear()
        cost, basis = self.trace.estimate_cost(
            "openrouter", "nvidia/nemotron-3-super-120b-a12b:free", 1, 1)
        self.assertEqual((cost, basis), (0.0, "free-tier"))


class TestRotationReport(unittest.TestCase):
    def setUp(self):
        self.trace = importlib.import_module("ai_trace")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # rotation_report reads TWO inputs: the trace store and the reaper's
        # health file. Overriding only the first leaves the real
        # ~/.concierge/pool_health.json merged in, and the test then asserts
        # against live history while looking hermetic.
        self._saved = self.trace.POOL_HEALTH
        self.trace.POOL_HEALTH = self.root / "pool_health.json"
        self.traces = self.root / "traces"
        self.traces.mkdir()
        now = time.time()
        (self.traces / "2026-09-25.jsonl").write_text("\n".join(
            json.dumps(r) for r in [
                {"ts": now - 300, "iso": "2026-09-25T01:00:00", "provider": "groq",
                 "model": "m", "status": 200, "latency_ms": 10,
                 "key_tag": "kgood", "total_tokens": 100},
                {"ts": now - 200, "iso": "2026-09-25T02:00:00", "provider": "groq",
                 "model": "m", "status": 200, "latency_ms": 10,
                 "key_tag": "kgood", "total_tokens": 50},
                {"ts": now - 100, "iso": "2026-09-25T03:00:00", "provider": "puter",
                 "model": "m", "status": 403, "latency_ms": 10,
                 "key_tag": "kbad", "total_tokens": 0},
            ]) + "\n")

    def tearDown(self):
        self.trace.POOL_HEALTH = self._saved
        self.tmp.cleanup()

    def test_counts_per_key(self):
        report = self.trace.rotation_report(days=7,
                                            trace_dir_override=self.traces)
        by_key = {r["key"]: r for r in report["rows"]}
        self.assertEqual(by_key["kgood"]["calls"], 2)
        self.assertEqual(by_key["kgood"]["ok"], 2)
        self.assertEqual(by_key["kgood"]["total_tokens"], 150)
        self.assertEqual(by_key["kbad"]["errors"], 1)

    def test_reports_what_it_cannot_see(self):
        # A failed key is absent from the trace entirely, so the report has to
        # say so rather than implying rotation happened exactly once.
        report = self.trace.rotation_report(days=7,
                                            trace_dir_override=self.traces)
        self.assertIn("only the key that ANSWERED",
                      self.trace.format_rotation(report))

    def test_retired_key_surfaces_even_with_no_calls(self):
        # A key the reaper condemned but that never served a request is exactly
        # the one an operator needs to go and replace.
        self.trace.POOL_HEALTH.write_text(json.dumps({
            "schema": "concierge.pool_health/1", "checked_at": "now",
            "providers": {"puter": {"keys": {
                "kdead": {"state": "unpaid", "http": 402,
                          "detail": "subscription required"}}}}}) )
        report = self.trace.rotation_report(days=7,
                                            trace_dir_override=self.traces)
        by_key = {r["key"]: r for r in report["rows"]}
        self.assertIn("kdead", by_key)
        self.assertEqual(by_key["kdead"]["verdict"], "unpaid")
        self.assertEqual(by_key["kdead"]["calls"], 0)
        self.assertEqual(report["retired"], 1)

    def test_no_traces_is_not_an_error(self):
        empty = Path(self.tmp.name) / "empty"
        self.assertEqual(
            self.trace.rotation_report(days=7,
                                       trace_dir_override=empty)["keys"], 0)

    def test_override_is_actually_honoured(self):
        # Without the override the report reads the real store, which is how a
        # test that means to be hermetic quietly asserts against live history.
        report = self.trace.rotation_report(days=7,
                                            trace_dir_override=self.traces)
        self.assertEqual({r["provider"] for r in report["rows"]},
                         {"groq", "puter"})


if __name__ == "__main__":
    unittest.main()
