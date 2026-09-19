# QRD — Ribbon (spec-bound animation)

**What it is:** Zero-dep ribbon draw animation bound to `ribbon.v1` contract (like `layout_spec.v1` but for ribbons). CSS works standalone; JS measures exact length.

**Where:**
- `spec.schema.json` — JSON Schema (draft-07) mirror, hand-rolled validator doesn't use it but doc does
- `ribbon.spec.json` — canonical bundle (hero-ribbon, 4 points, #7c5cff)
- `ribbon.css` — `.ribbon-wrap/.ribbon-svg/.ribbon-path` + `@keyframes ribbon-draw` + `prefers-reduced-motion`
- `ribbon.js` — reads `.ribbon-wrap[data-ribbon]` JSON, creates `<svg><path>` per ribbon, sets `--len/--dur/--easing`, adds `.animate`
- `validate.py` — zero-dep gate: duplicate id, #RRGGBB, width 0.5..32, ≥2 points, easing enum, opacity 0..1, dash numeric array, `path.closed` boolean, `direction` enum, `loop` boolean — failures → `analysis_report.json` only, bundle untouched. Malformed shapes (a ribbon, `path`, `style`, or `animation` that isn't an object) are reported as errors rather than raised, so every failure still reaches the report.
- `fixtures/{single,double,precise-width}.json` — must PASS
- `fixtures_invalid/*.json` — negative fixtures, one per rule, each tripping exactly one check; must FAIL (proves the guard trips). They live outside the CLI's sweep, so `python -m unittest tests.test_ribbon_validate -v` is what actually runs them.
- `demo.html` — file:// safe, no server needed

**Contract:** `validate_bundle(bundle, schema) → errs[]` in `validate.py`. Call it from any recompile entrypoint.

**Probe:** `python3 src/ui/ribbon/validate.py` (expect PASS + report at `analysis_report.json`)
