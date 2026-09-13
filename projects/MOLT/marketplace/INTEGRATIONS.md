# Marketplace Integrations — OpenRouter / VS Code / Vibe / Aider

Every MOLT bundle is a **hydrated runtime that works with any marketplace** — no MCP server per integration. The same `SKILL.md + sidecar.json + daemon/scout.py` works everywhere because hydration happens **before** the API call.

> **Banner:** Stop paying the MCP tool-calling tax — this prompt is already hydrated. **0 tool calls. 70–90% API savings.**

## How it works everywhere

```python
from src.skill.inference_bridge import molt_one_shot

# One call, any model, no tool loop — Scout already pre-fetched into sidecar.json
text = molt_one_shot("mcp-replacement", "what's blocked in sprint 17?", oomf_level=3, dry_run=True)
# then toss `text` at OpenRouter / Groq / Gemini / Puter — same hydrated prompt
```

Or CLI:

```bash
python -m src.skill.inference_bridge --skill mcp-replacement --dry-run "what's blocked?" | head
python -m src.skill.inference_bridge --skill negotiation-ghost --oomf 4 --dry-run "whisper for ACME call"
```

See also: `BUNDLE_SPEC.md` (bundle contract), `MCP_REPLACEMENT.md` (N→0 demo), `KID_TOOLCHAINS.md` (Kid composition).

---

## 1. OpenRouter (marketplace listing + runtime)

**Listing:** paste each bundle's `LISTING.md` into OpenRouter marketplace. Include the 70–90% banner at the top and link `sidecar.schema.json` as the typed contract.

**Runtime:** `inference_bridge.molt_one_shot` falls back to OpenRouter when `OPENROUTER_API_KEY` is set — it hydrates then calls `https://openrouter.ai/api/v1/chat/completions` with a single `messages` array (no tools).

```bash
export OPENROUTER_API_KEY="sk-or-..."
python -m src.skill.inference_bridge --skill saas-churn-oracle --oomf 3 "score account acme-corp"
# or from Python
from src.skill.inference_bridge import molt_one_shot
print(molt_one_shot("saas-churn-oracle", "score acme-corp", oomf_level=3, model="openai/gpt-4o"))
```

**Retainer:** private Scout feeds are gated via `sidecar.json: entitlements.active` + `daemon/config.yaml: license.key` + Oracle gate — works offline, so OpenRouter buyers don't need a live license server.

---

## 2. VS Code (extension / marketplace)

**What the buyer installs:** copy the bundle into the workspace (`SKILL.md -> .agents/skills/<skill>/`, `sidecar.json -> rag_storage/sidecars/<skill>.json`) and enable the cron. No extension required — but if you ship an extension, it just reads `sidecar.json`.

**Minimal VS Code mapping:**

```jsonc
// .vscode/settings.json — optional, for a thin MOLT extension
{
  "molt.skills": ["mcp-replacement", "adversary-emulator"],
  "molt.hydrateOnOpen": true,  // run `daemon/scout.py` before hydration
  "molt.oomfDefault": 3
}
```

**Command palette (if you ship an extension):**

```ts
// extension.ts — pseudocode, no MCP server
const sidecar = JSON.parse(fs.readFileSync("rag_storage/sidecars/mcp-replacement.json","utf8"));
const msgs = await hydrate("mcp-replacement", userQuery); // calls SkillManager.hydrate
vscode.window.showInformationMessage(`MOLT hydrated: 0 tool calls — sidecar ${sidecar.hydrated_at}`);
```

**Without an extension:** the bundle works as a file — VS Code + Copilot/Continue just sees the hydrated prompt via `inference_bridge --dry-run | pbcopy`.

---

## 3. Vibe CLI

Vibe already understands MOLT flags — `vibe` is patched to parse `--oomf` / `--elevate` without breaking.

```bash
# Vibe + MOLT ( Scout pre-fetches, Oracle gates, Governor confirms --elevate )
vibe "summarize standup --oomf 3"
vibe "harden repo from latest CVEs --oomf 4 --elevate network,write"
# inline --oomf in freeform prompt also works
python -m src.skill.inference_bridge --skill mcp-replacement --dry-run "summarize standup --oomf 3"
```

Patch point: `src/skill/inference_bridge.patch_vibe_argv()` strips MOLT flags before passthrough so Vibe never sees them as unknown.

---

## 4. Aider

Aider loads the empire hint via `.aider.conf.yml -> projects/ScoutEmpire/cli/SKILL_HINT.md` (legacy ScoutEmpire) and MOLT via `templates/SKILL.template.md`. For MOLT bundles:

```bash
# Add MOLT hint to aider
echo "read: projects/MOLT/marketplace/BUNDLE_SPEC.md" >> .aider.conf.yml

# Use a Living Skill inside an Aider session
python -m src.skill.inference_bridge --skill bureaucracy-judo --dry-run "draft filing for parcel 42" > /tmp/hydrated.md
aider --msg "$(cat /tmp/hydrated.md)"
```

Or hydrate inside `tools/coding/smart_coder.py` — it already calls `hydrate_rag_context()` when a `SKILL.md` with frontmatter is present.

---

## Scout-foreman + Provenance-oracle (the marketplace utilities from the spec)

- **`scout-foreman`** — herds every Scout the buyer installed: `scout_health` sweeps, `memory_footprint` budgeting, `secret_rotation` via `vault-launch`. Validated as `bundles/scout-foreman/` — `$49 (free with 2+ bundles)`. Run `python projects/MOLT/marketplace/bundles/scout-foreman/daemon/scout.py` on a 15m cron.
- **`provenance-oracle`** — deepfake/C2PA verifier for media houses using **Sora / Flux / Veo**. Checks `c2pa_manifests + generator_signatures -> provenance_seal` before any write. Validated as `bundles/provenance-oracle/` — `$199–$449`. See `sidecar.schema.json` for the `provenance_seal` contract.

Both compose with any other bundle via typed sidecars — e.g. `negotiation-ghost` reads `mcp-replacement:ticket_snapshot` without calling a tool.

---

## Validate before you publish

```bash
python tools/marketplace/scaffold_bundle.py --all
python tools/marketplace/validate_bundle.py --all   # 9 PASS
python -m unittest discover -s tests -v             # 70 OK
# smoke one bundle end-to-end
python projects/MOLT/marketplace/bundles/mcp-replacement/daemon/scout.py
python -m src.skill.inference_bridge --skill mcp-replacement --dry-run "demo" | head -n 20
```

Your marketplace listing is the bundle's `LISTING.md` + the 70–90% banner. The zip is the bundle folder — see `PITCH_AND_PRICING.md → What's in the zip`.



---

## 5. Whorl Hive (Termux / Chromebook / Desktop — zero-network)

Headless nodes consume Scout intelligence via **`~/.whorl/bus/` atomic files** — no ports, no sockets.

```python
from src.skill.whorl_bus import WhorlBusDispatcher
bus = WhorlBusDispatcher(agent_name="molt-dispatcher")
bus.monitor_bus()                      # {total_inbox, dead_letters, clock_latency_ms, zero_drop}
bus.poll_inbox("molt-dispatcher")      # headless consume (Termux/Chromebook/desktop)

# Scout auto-deposits every bake: see src/skill/scout.py (bus=WhorlBusDispatcher)
# Inference auto-deposits hydrated preview: see src/skill/inference_bridge.py
```

**State branching:** `src/skill/state_snapshotter.py` → `~/.whorl/agents/molt-<skill>/vN.json + HEAD` or `rag_storage/molt_state/` fallback. `SkillManager.apply_mutation(..., snapshotter, bus)` snapshots pre-mutate; `rewind_skill(skill, version)` for zero-downtime rollback.

**Overseer:** `src/skill/governor.py` → `Governor().audit_to_overseer()` + `heartbeat_to_bus()` — Governor sessions become legible to the `Overseer` 60s sweep (`~/Overseer/rules.json`) without polling.

**Loom resume:** `src/skill/loom_weaver.py` → `LoomThreadWeaver(bus).weave(skill, prompts)` persists to `rag_storage/loom/<workflow>.json` + Whorl bus; headless nodes `resume(workflow_id, extra_prompts)` with context continuity (`ctx_digest`).

See `HIVE_MIND.md` for the full wiring order and headless bring-up.
