# Foreman — herding 39 scouts

## Global desired_settings (one knob)
Edit `projects/ScoutEmpire/manifest.json` or `.agents/skills/scout-foreman/scout/config.yaml`:

```yaml
desired_settings:
  optimize_for: revenue_retained  # revenue | autonomy | sovereignty | stealth | calibration | safety
  risk_tolerance: medium
  budget_cap_month: 2000
  compliance_level: strict
  stealth_vs_legitimacy: 0.5
```

## Commands
```bash
scout sweep                         # check all 39 traces, decide retrain/promote
scout report                        # portfolio table: status, traces, next action
scout set-optimize autonomy         # propagate optimize_for
scout retrain <slug>               # single scout retrain
scout spawn "grey-market-cartographer"  # draft new SKILL.md + scout
scout list --continent unknown_unknowns
```

## Safety locks (never overridden)
- hazard-guardian: safety locked
- forensics-chain, case-linker: chain-of-custody
- med-triage-copilot: NOT A DIAGNOSIS

## Traces
Each scout: `.agents/skills/<slug>/scout/traces.jsonl`
Aggregated mirror: `projects/ScoutEmpire/traces/` (symlinked view, optional)
Foreman log: `~/.local/share/scout-foreman/promotions.jsonl`
