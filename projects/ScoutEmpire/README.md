# Scout Empire — 40 self-evolving SKILL.md scouts + foreman

> Tiny scouts attached to every skill. They retrain on desired_settings, log traces, A/B promotion. Set and evolve.

## Structure
```
projects/ScoutEmpire/
  README.md           # this
  manifest.json       # inventory of all 40 scouts
  scouts/             # symlink farm -> .agents/skills/*/scout (no copy, always live)
  traces/             # aggregated traces mirror (optional, for analytics)
  docs/
    CATALOG.md        # human catalog of 40 skills by continent
    FOREMAN.md        # how to herd the empire
    DESIRED_SETTINGS.md # tuning guide
  cli/
    scout             # unified CLI: bin/scout -> projects/ScoutEmpire/cli/scout
```

## Quickstart (while hunting the prop)
```bash
scout list                          # 40 scouts + status
scout run saas-churn-oracle --all   # run any scout's score
scout retrain talent-singularity-scout
scout sweep                         # foreman sweeps all 40
scout report                        # portfolio report
scout set-optimize revenue_retained # global desired_settings
scout spawn "grey-market-cartographer"  # new scout draft
```

## Where scouts live (source of truth)
`.agents/skills/<slug>/scout/` — _project does not duplicate_, `scouts/` are symlinks.

## The 40 (8 continents)
- **SaaS:** churn-oracle, pricing-optimizer, onboarding-architect
- **Predictive:** prophet-on-steroids, anomaly-hunter, causal-inference-lab
- **ML/RL:** rl-env-designer, reward-shaper-pro, ml-pipeline-autotuner, robo-manipulation-trainer
- **Medicine/Science:** med-triage-copilot, trial-architect, paper-to-protocol, lab-optimizer
- **Law/Security:** case-linker, forensics-chain, fortress-assessor, perimeter-sentry
- **IT/Cyber:** incident-commander, infra-cost-killer, adversary-emulator, purple-validator, phish-resilience-drill, bci-signal-cleaner
- **Chemistry/MatSci:** synthesis-planner, hazard-guardian, materials-discoverer
- **Unknown unknowns (deep):** epistemic-immune-system, memory-hole-archivist, water-food-grid-nexus, off-grid-escape-hatch, supply-chain-ghost-mapper, jurisdiction-arbitrageur, bureaucracy-judo, regulatory-premonition, talent-singularity-scout, provenance-oracle, failure-library, black-swan-bounty
- **Meta:** scout-foreman (herds all 40)
```
