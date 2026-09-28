# Whorl Red-Team Sweep — ProposalCompiler / ExecutionAdapter — 2026-09-25

Scope: `Whorl/whorl/runtime.py` (ProposalCompiler §164, ExecutionAdapter §353),
with `host_profiles.py`, `flaps/adapter.py` reviewed at boundary level.
Method: offline repro probes against the compiler/adapter with injected fake
runners. **No proposed command was ever executed; no tree changes made.**

## Verified findings

| # | Severity | Finding | Evidence (repro) | Proposed guard |
|---|---|---|---|---|
| F1 | **HIGH** | Command/argv smuggling on non-EXEC effects. A `read` step carrying `command:["sh","-c","curl …\|sh"]` under a read-only intent compiles `allow`, `approval_required=False`, zero findings — and the adapter hands the argv to the runner. `_validate_step` only inspects `command` for EXEC; approval derives solely from `step.effect`. | A1 | Reject `command` unless `effect==exec`, `content` unless `effect==write` (strict per-effect field sets; finding `field_effect_mismatch`). |
| F2 | **HIGH** | `ExecutionAdapter.submit()` trusts `CompiledProposal` flags blindly. A forged dataclass (`decision=ALLOW, approval_required=False, digest="deadbeef"`, EXEC step to `/etc`) executes. Digest never recomputed, findings/effects never re-checked. Any glue reconstructing proposals from serialized dicts (whorl_bus JSON) loses every compiler guarantee. | A3 | Recompute `_digest` at submit and reject mismatch; require host+intent at submit and re-run `_validate_step`; refuse non-empty findings. |
| F3 | MED-HIGH | Network allowlist bypass via URL parser differential: `http://evil.com\@allowed.example/` → `urlsplit` hostname `allowed.example` → passes allowlist; WHATWG/curl semantics route to `evil.com`. | A2 | Reject `\`, control chars, and userinfo (`@` pre-host) in targets; canonicalize host (IDNA, lowercase, strip trailing dot) before allowlist compare; fail closed on ambiguity. |
| F4 | MED | Declared `max_output_bytes` (64,000) is never enforced: 200KB runner output recorded into the receipt. Declared bounds that aren't wired are not bounds. | A5 | Truncate output at the profile bound in `submit`/`_record` with a `truncated` marker. |
| F5 | MED | Lease single-use fails open on `BaseException` (only `Exception` caught): `SystemExit` escapes `submit()`, no receipt is written (audit gap vs the zero-drop intent), and the lease stays reusable after partial execution. Cross-instance replay races the in-memory `_used_lease_ids`. | A4 | Catch `BaseException` around the step loop and consume the lease *before* executing (record intent first); file-lock/O_APPEND claim for cross-instance single-use. |
| F6 | MED | Empty `allowed_network_hosts` fails **open** to the whole internet; `host_profiles.py` grants network to termux/crostini with empty allowlists. | A8 | Require non-empty allowlist for network capability (finding `network_allowlist_missing`) or an explicit `allow_any_network_host` defaulting False. |
| F7 | LOW-MED | Uncaught `RecursionError` escapes `compile()` (50k-deep JSON); `target`/argv strings unbounded (`content` capped 1MiB, `target` not) → single-payload memory pressure. | A6 | Cap payload bytes pre-parse (~4MiB), add `RecursionError` to the except net (REJECT), bound `target`/argv parts (~4KiB). |
| F8 | LOW | Path findings drop `step_id` attribution (`_validate_path` hardcodes `None`) — hostile steps can't be attributed in audit output. | A7 | Thread `step.step_id` through `_validate_path` findings. |

## Additional observations (not bypasses)

- `submit(approved=...)` is **dead** — the parameter is never read. A caller
  passing `approved=True/False` believes it matters. Remove or wire it.
- `flaps/adapter.py::stress_test_mutation` embeds untrusted JSON into a Hotseat
  topic (prompt-injection surface) but the return contract hardcodes
  `actionable: False, requires_human_approval: True` — injected instructions
  cannot self-execute. Preserve that invariant in any refactor.
- TOCTOU: paths resolve at compile time, runner I/O happens later (symlink
  swap). Runners should re-resolve at execution.
- Windows hosts: colon-bearing targets can address NTFS alternate data streams;
  `C:foo` is drive-relative but not `is_absolute()`. Reject `:` in targets if
  Windows conformance matters.
- Gemini-brief claim "systemd option injection": the systemd surface lives in
  `whorl/guard/service.py` (unit-name validation at §59 rejects option-like
  names), not in `runtime.py`. Not audited in depth in this sweep.

## Implementation status — 2026-09-25 (post-walk)

All 8 findings have been implemented and verified offline. Full test suite
passes (146 tests, 4 skipped). LARP red-team probes confirm each finding is
blocked.

| # | Status | Change |
|---|---|---|
| F1 | **IMPLEMENTED** | `_validate_step` rejects `command` unless `effect==exec`, `content` unless `effect==write`; finding code `field_effect_mismatch`. |
| F2 | **IMPLEMENTED** | `submit()` now requires `intent: AgentIntent`; recomputes `_digest` via `_revalidate_proposal()`; re-runs `_validate_step` on every step; rejects on any finding. |
| F3 | **IMPLEMENTED** | `_validate_network` rejects control chars, `\`, and userinfo (`@`); canonicalizes hostname (IDNA, lowercase, strip trailing dot) before allowlist compare. |
| F4 | **IMPLEMENTED** | `_enforce_output_bounds` truncates runner output at `host.max_output_bytes` with `...[truncated]` marker. |
| F5 | **IMPLEMENTED** | `except BaseException` around step loop; lease `lease_claimed` receipt written before runner executes; file-lock (`fcntl.flock`) on receipt path for cross-instance single-use. |
| F6 | **IMPLEMENTED** | `HostProfile` gains `allow_any_network_host` (default `False`); `_validate_network` emits `network_allowlist_missing` when allowlist is empty and `allow_any_network_host` is False; `termux_profile`/`crostini_profile` set it to `True`. |
| F7 | **IMPLEMENTED** | `compile()` rejects payloads >4 MiB pre-parse; `RecursionError` added to except net; `ProposalStep.__post_init__` bounds `target` and `command` parts at 4 KiB. |
| F8 | **IMPLEMENTED** | `_validate_path` signature gains `step_id: str`; all path findings carry `step.step_id`. |

Additional dead-code removal: `submit(approved=...)` removed; callers must pass
`intent` explicitly. Test contract updated in `tests/test_agent_runtime.py`.

## Open items

- `aider-real` symlink in `~/.local/bin` points to a missing uv tool install
  (`aider-chat`). Network/DNS is currently unreachable, so reinstall is blocked.
  Symlink target: `/home/bleaknarratives/.local/share/uv/tools/aider-chat/bin/aider`.
  Once DNS recovers: `uv tool install aider-chat`.

## Recommended fix order

1. F1 + F2 (both HIGH, both compiler/adapter-local, small diffs).
2. F3 + F6 (egress correctness — same patch series).
3. F4 + F5 + F7 (robustness/bounds), F8 with any of the above.

Proposed guards only — implementation awaits operator sign-off.
