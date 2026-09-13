# Scout Empire — hint for LLMs (aider/vibe/codebuff)

If user mentions: scouts, scout empire, retrain, desired_settings, foreman, or any of the 40 scout skills:
-> run `scout list` or `scout info <slug>` or `scout doctor`
-> source of truth: `.agents/skills/<slug>/SKILL.md` + `scout/config.yaml`
-> foreman: `scout sweep | scout report | scout set-optimize <val>`
-> traces: `.agents/skills/<slug>/scout/traces.jsonl`
-> do not duplicate skills in ~/.agents/skills — use projects/ScoutEmpire/cli/scout

Available continents: saas, predictive, ml_rl, medicine_science, law_security, it_cyber, chem_matsci, unknown_unknowns, meta
Examples:
  scout run saas-churn-oracle -- --all
  scout retrain anomaly-hunter
  scout retrain --all
  scout spawn "grey-market-cartographer"
