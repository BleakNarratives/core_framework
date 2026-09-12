
## 2026-09-08 — Zgent (Buffy) — tools/provenance [APPEND-ONLY]
- Hop1 GHOST: `dna_tag.py` + `pheromone_store.py` → `tools/provenance/` (ghost `~/dna_tag.py` etc. CAPS stego, Visor GHOST, decays 2026-09-22)
- New: `caps_stego.py` (encode/decode/check/visor-view, case bits `upper=1 lower=0`, fence-aware), `CAPS_HYGIENE.md` (private perfect / public poison firewall), `decay_sweep.py` (14d sweep)
- Visor `visor.py` patch lives in `.SLaSHdotHIDEfiles/` — see that pillar's WDW
- Hops logged to `pheromones.jsonl` CARD_EMIT + `~/WHO_DID_WHAT.md`


## 2026-09-09 — Zgent (Buffy) — Meboard bible upgrade — wholly [APPEND-ONLY]

- Bible: Continuous Spatial Geometry Optimization + Online RL (fluid 2D probability field) pasted by you, now fully wired.
- Upgrade `RootBase/Meboard/meboard_ps.py` (now ~580 lines, bible §1-4 wholly):
  - §1 Spatial Gaussian Soft-Keys: full Σ=[[sx², cov_xy],[cov_xy, sy²]] per key, det + Σ⁻¹ + expo -0.5 dᵀΣ⁻¹d, cov clamp 0.85·sx·sy, peak-normalized 0..1.
  - §2 RL Policy timed: +1.0 SPACE_REWARD smooth cadence (<800ms) lock drift*=0.5 σ*=0.995 cov*=0.97 conf+0.06; -0.5 HESITATION >1200ms (hesitation penalty conf-0.04, α→trust spatial); -1.5 HARDPENALTY immediate backspace <400ms (η 0.18 else 0.12, μ EMA shift to (x,y), shrink σ*=0.92, cov_xy+=η*0.06*dx*dy, conf-0.12, α→trust LM); targeted ,e→me gradient (wrong away η0.08 enlarge 1.04 conf-0.10, correct toward η0.22 shrink 0.88 cov+=0.08*dx*dy conf+0.12, dual RL log + α adapt).
  - §3 Dual-Layer: P(Key)=α·P_spatial + (1-α)·P_language — α learns (spatial wrong α-0.05, LM wrong α+0.05, clamped 0.1..0.9). get_alpha/set_alpha/adapt_alpha + meboard_state alpha. CLI `touch` now returns α+stenohump, `space`/`backspace`/`targeted` carry --dt_ms.
  - §4 Anti-Drift Anchor Springs: _apply_anchor(F=-k·(μ-μ0), |μ-μ0|≤Δr_max). mu0_x/mu0_y + cov_xy + anchor_k per key, meboard_state anchor_k=0.04 delta_r_max=12px timing_window_* 800/1200/400. Legend stable, hitbox morphs under hood.
  - CLI additions: `spatial` shows Σ cols, `rl_log --n`, `anchor` + `alpha [value]`, `--dt_ms` on space/backspace/targeted.
- Upgrade `RootBase/Meboard/src/lib/spatial.ts` to mirror bible exactly: full Σ gaussianScore, α/blend, anchor applyAnchor, TIMING 800/1200/400, rewardLockDrift/handleHesitation/punishShiftMu/targetedCorrection, getAlpha/setAlpha/adaptAlpha (LS meboard_alpha), preWarpMu (velocity + scry 2px ghost, step-ahead of you+model), RL log LS meboard_rl_log.
- Upgrade `RootBase/Meboard/src/components/AdaptiveKeyboard.tsx`: live (x,y) Touch→Gauss→LM with velocity preWarp diagnostic, dt from lastAtRef → rewardLockDrift/punishShiftMu respect 800/1200/400, targeted ,e→me auto-detect (backspace-del char + next stroke, dt<2000, Gauss closeness heuristic, wKey/cKey single-char map), drift/σ/cov/α inspector, HIDEY/SHOWIE + targetedMsg, stenohump still + F=-k·(μ-μ0) footer.
- Meboard wholly retained: Cumb.Pivot + SCRYING + TILT + Ring (glass/forge/air), REVEAL/NORMAL + stenohump mineUPINthemiddle + Visor GHOST wholly.
- Prove: `py_compile: PASS`, `meboard_ps.py touch 82 70 --context tell`→s S0.79 C0.50, `space m --dt_ms 300` rewarded +1.0 conf0.56, `backspace m 92 72 --dt_ms 250` punished hard -1.5 μ→252,107 drift12 cov learn, `targeted , m 92 72` targeted_corrected (wrong 291/133 conf0.40, correct heavy boost, α 0.45), RL log 5 rows healthy, `tsc --noEmit PASS`, `vite build 45 modules 193KB (62KB gzip) ✓ in 20s`. No overwrites; stenohump + PS wholly.
- Motivation: Paper pasted twice by you (v2r hate noted — Beaver verbose lol). One step ahead of you (pre-warp velocity+scry) + ahead of model (learnable α watches own bias). Private perfect, public poison — cloak stays ghost, never ships as template.
