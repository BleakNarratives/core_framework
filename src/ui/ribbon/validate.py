#!/usr/bin/env python3
"""
validate.py — recompilation guard for ribbon bundles.

Checks:
  1. spec.schema.json and ribbon.spec.json parse as JSON
  2. ribbon.spec.json satisfies the hand-rolled ribbon.v1 contract (no jsonschema dep)
  3. fixtures/*.json all satisfy the same contract
  4. Per ribbon: unique id matching ^[a-z0-9_-]+$, >=2 numeric [x,y] points,
     a #RRGGBB stroke, a width within 0.5..32, and a valid easing/duration
  5. Writes analysis_report.json on EVERY run, never rewrites the bundle

fixtures_invalid/ is deliberately not scanned: it holds the negative fixtures
that prove the guard trips, and leaving them out of the sweep is what lets this
script stay green. tests/test_ribbon_validate.py asserts they are rejected, so
that proof still runs in the suite.

Exit: 0 clean, 1 bundle contract fail, 2 fixture fail.
Exit 75 is the caller's convention for "schema fail -> roll back", owned by the
recompile wrapper (see tools/guard/QRD.md); this script never exits 75.
"""
import json, pathlib, re, sys
ROOT = pathlib.Path(__file__).parent
SCHEMA = ROOT / "spec.schema.json"
BUNDLE = ROOT / "ribbon.spec.json"
FIXTURES = ROOT / "fixtures"
REPORT = ROOT / "analysis_report.json"

def load_json(p):
    try:
        return json.load(open(p))
    except Exception as e:
        return {"__error": str(e)}

def validate_bundle(bundle, schema):
    errs = []
    # top-level
    if bundle.get("version") != "ribbon.v1":
        errs.append(f"version must be 'ribbon.v1', got {bundle.get('version')!r}")
    if bundle.get("kind") != "ribbon":
        errs.append(f"kind must be 'ribbon', got {bundle.get('kind')!r}")
    ribbons = bundle.get("ribbons")
    if not isinstance(ribbons, list) or not ribbons:
        errs.append("ribbons must be non-empty array")
        return errs
    seen = set()
    for idx, r in enumerate(ribbons):
        rid = r.get("id", f"[{idx}]")
        if rid in seen:
            errs.append(f"ribbon id duplicate: {rid!r}")
        seen.add(rid)
        if not re.match(r"^[a-z0-9_-]+$", rid or ""):
            errs.append(f"ribbon id {rid!r} must match ^[a-z0-9_-]+$")
        pts = ((r.get("path") or {}).get("points"))
        if not isinstance(pts, list) or len(pts) < 2:
            errs.append(f"{rid}: path.points must have >=2 points")
        else:
            for j, pt in enumerate(pts):
                if not (isinstance(pt, list) and len(pt) == 2 and all(isinstance(x, (int, float)) for x in pt)):
                    errs.append(f"{rid}: points[{j}] must be [x,y] numbers, got {pt!r}")
        style = r.get("style") or {}
        stroke = style.get("stroke")
        if not (isinstance(stroke, str) and re.match(r"^#[0-9a-fA-F]{6}$", stroke)):
            errs.append(f"{rid}: style.stroke must be #RRGGBB, got {stroke!r}")
        w = style.get("width")
        if not (isinstance(w, (int, float)) and 0.5 <= w <= 32):
            errs.append(f"{rid}: style.width must be 0.5..32, got {w!r}")
        anim = r.get("animation")
        if anim is not None:
            if "easing" in anim and anim["easing"] not in ("linear","ease-in","ease-out","ease-in-out"):
                errs.append(f"{rid}: animation.easing invalid {anim['easing']!r}")
            if "duration_ms" in anim and not (isinstance(anim["duration_ms"], int) and anim["duration_ms"] >= 100):
                errs.append(f"{rid}: animation.duration_ms must be >=100 int")
    return errs

def main():
    schema = load_json(SCHEMA)
    bundle = load_json(BUNDLE)
    report = {"bundle": str(BUNDLE), "schema": str(SCHEMA), "errors": [], "fixture_errors": {}}

    if "__error" in schema:
        report["errors"].append(f"schema JSON parse: {schema['__error']}")
    if "__error" in bundle:
        report["errors"].append(f"bundle JSON parse: {bundle['__error']}")
    else:
        report["errors"].extend(validate_bundle(bundle, schema))

    # fixtures: every fixtures/*.json must validate
    if FIXTURES.exists():
        for f in sorted(FIXTURES.glob("*.json")):
            b = load_json(f)
            if "__error" in b:
                report["fixture_errors"][f.name] = [f"JSON parse: {b['__error']}"]
            else:
                errs = validate_bundle(b, schema)
                if errs:
                    report["fixture_errors"][f.name] = errs

    # write companion analysis_report (always, never mutates bundle)
    json.dump(report, open(REPORT, "w"), indent=2)
    has_err = bool(report["errors"]) or bool(report["fixture_errors"])
    if has_err:
        print(f"[ribbon:validate] FAIL — {len(report['errors'])} bundle errors, {len(report['fixture_errors'])} fixture files bad")
        for e in report["errors"]:
            print("  -", e)
        for fname, errs in report["fixture_errors"].items():
            print(f"  fixture {fname}:")
            for e in errs:
                print("    -", e)
        print(f"  → {REPORT} (companion, bundle untouched)")
        # single + double ribbon are deterministic fixtures; empty must fail
        sys.exit(1 if report["errors"] else 2)
    print(f"[ribbon:validate] PASS — bundle + {len(list(FIXTURES.glob('*.json')))} fixtures clean")
    print(f"  report: {REPORT}")
    sys.exit(0)

if __name__ == "__main__":
    main()
