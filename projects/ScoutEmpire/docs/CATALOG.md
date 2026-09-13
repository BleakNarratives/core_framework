# Scout Catalog — 40 skills

Generated 2026-09-12 • 40 scout-skills + 8 non-scout utils

## saas
- **saas-churn-oracle** — Predict churn 30/60/90 days + auto-intervention playbooks. Scout retrains on saved vs lost accounts, tunes threshold weekly. Use when asked about churn, retention, LTV, or SaaS health. _(optimize_for: revenue_retained)_
- **saas-pricing-optimizer** — Dynamic pricing, packaging, and willingness-to-pay modeling. Scout A/B tests price points and learns from conversion. _(optimize_for: ARPU_expansion)_
- **saas-onboarding-architect** — Generates onboarding flows that reduce time-to-value. Scout optimizes for activation rate. _(optimize_for: activation_rate)_

## predictive
- **prophet-on-steroids** — Time-series + causal forecasting for any metric. Scout retrains on MAPE and learns seasonality + intervention impact. _(optimize_for: forecast_accuracy)_
- **anomaly-hunter** — Streaming anomaly detection for biz metrics and logs. Scout tunes sensitivity from false-positive feedback. _(optimize_for: recall_per_alert_fatigue)_
- **causal-inference-lab** — A/B test / diff-in-diff / synthetic control designer. Scout learns what experiment designs actually moved the needle. _(optimize_for: true_causal_lift)_

## ml_rl
- **rl-env-designer** — Builds Gym envs + reward functions from description. Scout optimizes for sample efficiency and transfer. _(optimize_for: sample_efficiency)_
- **reward-shaper-pro** — Fixes reward hacking, sparse rewards, and designs shaped rewards for RL. Scout evolves rewards via human preference and environment trace. Use when asked about reward shaping, RL training, reward hacking, or sparse reward. _(optimize_for: sample_efficiency)_
- **ml-pipeline-autotuner** — End-to-end tune: data -> features -> model -> deploy. Scout hill-climbs on $/accuracy Pareto. _(optimize_for: accuracy_per_dollar)_
- **robo-manipulation-trainer** — RL for grasping in Isaac Sim. Scout handles sim2real transfer success. _(optimize_for: sim2real_success)_

## medicine_science
- **med-triage-copilot** — Symptom intake + differential + urgency score (triage assist, NOT diagnosis). Scout learns from clinician overrides. _(optimize_for: urgency_calibration)_
- **trial-architect** — Designs pharma trials, inclusion criteria, power calc. Scout optimizes for enrollment speed + FDA compliance. _(optimize_for: enrollment_per_compliance)_
- **paper-to-protocol** — Replicates paper -> executable lab protocol. Scout tracks replication success rate. _(optimize_for: replication_success)_
- **lab-optimizer** — DOE for wet lab, minimizes reagents and runs. Scout Bayesian optimization loop. _(optimize_for: yield_per_run)_

## law_security
- **case-linker** — Links MO, evidence, timelines across cases. Scout learns from detective confirmed links, strict chain-of-custody. _(optimize_for: confirmed_link_precision)_
- **forensics-chain** — Digital forensics timeline + artifact parser, court-admissible. Scout optimizes for admissibility. _(optimize_for: admissibility)_
- **fortress-assessor** — Physical + digital audit for home/business defense. Scout tunes false-alarm vs detection from break-in/pentest data. Use when asked about home security, business defense, cameras, locks, network hardening, or fortress. _(optimize_for: deterrence_per_dollar)_
- **perimeter-sentry** — Sensor fusion + drone patrol logic for perimeter. Scout tunes false alarm vs detection. _(optimize_for: detection_per_false_alarm)_

## it_cyber
- **incident-commander** — Auto RCA, runbooks, and post-mortem writer. Scout learns from MTTR and recurrence. _(optimize_for: MTTR)_
- **infra-cost-killer** — Finds $10k/mo savings in AWS/GCP. Scout optimizes for cost without perf drop. _(optimize_for: savings_per_perf)_
- **adversary-emulator** — Emulate APT TTPs for authorized purple team exercises. Scout evolves TTPs that bypass current blue detections. Use when asked about red team, adversary emulation, MITRE ATT&CK, purple team, or breach simulation. _(optimize_for: detection_gap_found)_
- **purple-validator** — Validates if blue detections fired after red emulation. Scout retrains detection rules. _(optimize_for: detection_coverage)_
- **phish-resilience-drill** — Generates + measures phishing sims (defensive training). Scout learns which lures your org falls for. _(optimize_for: click_rate_down)_
- **bci-signal-cleaner** — EEG/EMG denoise + decode intent. Scout personalizes to user's neural signature. _(optimize_for: decode_accuracy)_

## chem_matsci
- **synthesis-planner** — Retrosynthesis + route optimization for chemistry. Scout learns from yield/purity data to propose better routes. Use when asked about synthesis, retrosynthesis, reaction planning, or route optimization. _(optimize_for: yield_per_cost)_
- **hazard-guardian** — SDS-aware safety, incompatible reagent checker, never optimizes away safety. Compliance locked. _(optimize_for: safety_locked)_
- **materials-discoverer** — Predicts novel alloys/polymers for target property. Scout retrains on lab validation. _(optimize_for: validated_hit_rate)_

## unknown_unknowns
- **epistemic-immune-system** — Detects when you are being manipulated — narrative laundering, LLM consensus attacks, astroturfing, deepfake persuasion. Scout learns your cognitive blindspots and tunes sensitivity. Use when asked about manipulation, disinfo, bias, narrative, epistemic, or deception. _(optimize_for: deception_caught)_
- **memory-hole-archivist** — OSINT that auto-archives ephemeral signals before deletion/censorship. Scout learns what gets deleted and why. _(optimize_for: ephemeral_capture_rate)_
- **water-food-grid-nexus** — Models water table + grid stress + food supply fragility for your zipcode from satellite/utility data. Scout optimizes for days_of_autonomy. Use when asked about collapse, resilience, water, grid, food security, or autonomy. _(optimize_for: days_of_autonomy)_
- **off-grid-escape-hatch** — Designs comms/energy/money that works when internet/banks die (mesh/HAM/BTC/multisig). Scout stress-tests vs black swans. _(optimize_for: autonomy_days_offgrid)_
- **supply-chain-ghost-mapper** — Finds the ONE Taiwanese screw that kills your whole business. Scout retrains on disruption signals. _(optimize_for: single_point_found)_
- **jurisdiction-arbitrageur** — Finds where to live/incorporate/host data/sue for max freedom + min tax + max defense. Scout learns optimize stealth vs legitimacy. Use when asked about jurisdiction, tax, entity, residency, data sovereignty, or arbitrage. _(optimize_for: sovereignty_per_compliance_cost)_
- **bureaucracy-judo** — Turns permits/FOIA/grants/lawsuits into weapons. Scout learns which lever cracks which agency. _(optimize_for: days_saved)_
- **regulatory-premonition** — Predicts which laws will hit your sector 18mo early from bill/lobby/committee traces. Scout hit rate on enacted vs dead bills. _(optimize_for: enacted_prediction)_
- **talent-singularity-scout** — Finds 10x humans BEFORE they're obvious — commit velocity, latent discourse, failed startup pattern. Scout learns from hires who actually 10x'd. Use when asked about hiring, talent, 10x, cofounder, team, or talent search. _(optimize_for: 10x_hire_rate)_
- **provenance-oracle** — Makes your content provably real (C2PA, attestations) + detects deepfakes of you. Scout evolves with each new generator (Sora/Flux/Veo). Use when asked about provenance, C2PA, deepfake, attestation, watermark, or authenticity. _(optimize_for: provable_real_rate)_
- **failure-library** — Your anti-portfolio. Mines YOUR failures + others to prevent repeat. Scout optimizes for not_repeating_fuckup. _(optimize_for: repeat_prevention)_
- **black-swan-bounty** — Systematically hunts 0.1% probability * 1000x impact bets. Scout optimizes for calibration, not accuracy. _(optimize_for: calibration)_

## meta
- **scout-foreman** — Meta-skill that manages all scouts — decides when to retrain, prune, merge, or spawn skills. Set global desired_settings once and it herds the scouts. Use when asked about scouts, retrain, foreman, desired settings, or skill orchestration. _(optimize_for: revenue_retained)_

## Non-scout skills (infra)
- agentfork
- clawteam
- frontend-design
- improve-codebase-architecture
- internal-affairs
- mcp-builder
- tasksplit
- ui-ux-pro-max
