#!/usr/bin/env python3
"""
Validate a MOLT marketplace bundle.

Checks:
 - SKILL.md exists and has valid YAML frontmatter (name, version, scout, oracle, privileges)
 - sidecar.json exists and validates against sidecar.schema.json (if jsonschema is available, else structural check)
 - sidecar.schema.json exists and is valid JSON Schema
 - daemon/scout.py + daemon/config.yaml exist
 - LICENSE.md + LISTING.md exist
 - hydrated zero-bloat claim present in LISTING.md / SKILL.md

Usage:
  python tools/marketplace/validate_bundle.py projects/MOLT/marketplace/bundles/saas-churn-oracle
  python tools/marketplace/validate_bundle.py --all
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLES = ROOT / "projects" / "MOLT" / "marketplace" / "bundles"

REQUIRED = ["SKILL.md", "sidecar.json", "sidecar.schema.json", "daemon/scout.py", "daemon/config.yaml", "LICENSE.md", "LISTING.md"]

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)

def _parse_frontmatter(text: str):
    m = FRONTMATTER_RE.search(text)
    if not m: return None, "missing YAML frontmatter (--- ... ---)"
    raw = m.group(1)
    # lightweight check without yaml dep
    needed = ["name:", "version:", "scout:", "oracle:", "privileges:"]
    missing = [k for k in needed if k not in raw]
    if missing:
        return None, f"frontmatter missing keys: {missing}"
    # try real yaml if available
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(raw)
        return data, None
    except Exception:
        return {"_raw": raw}, None

def validate_one(bundle: Path) -> tuple[bool, list[str]]:
    errs, warns = [], []
    if not bundle.is_dir():
        return False, [f"not a directory: {bundle}"]
    for rel in REQUIRED:
        if not (bundle / rel).exists():
            errs.append(f"missing {rel}")

    # SKILL.md frontmatter + hydrated claim
    sk = bundle / "SKILL.md"
    if sk.exists():
        txt = sk.read_text(encoding="utf-8", errors="ignore")
        _, e = _parse_frontmatter(txt)
        if e: errs.append(f"SKILL.md: {e}")
        if "0 tool calls" not in txt and "Hydrated" not in txt:
            warns.append("SKILL.md: should mention '0 tool calls' / Hydrated zero-bloat pitch")
        # gambit
        if "gambit" not in txt.lower():
            warns.append("SKILL.md: gambit frontmatter/section missing (human-doc tandem)")

    # sidecar.json structural
    sj = bundle / "sidecar.json"
    sch = bundle / "sidecar.schema.json"
    if sj.exists():
        try:
            data = json.loads(sj.read_text())
            for k in ("skill", "version", "hydrated_at", "feeds"):
                if k not in data:
                    errs.append(f"sidecar.json missing key: {k}")
            if "entitlements" not in data:
                warns.append("sidecar.json: entitlements missing (needed for retainer model)")
        except Exception as e:
            errs.append(f"sidecar.json invalid JSON: {e}")
    if sch.exists():
        try:
            schema = json.loads(sch.read_text())
            if "$schema" not in schema or "properties" not in schema:
                warns.append("sidecar.schema.json: looks incomplete (no $schema/properties)")
        except Exception as e:
            errs.append(f"sidecar.schema.json invalid JSON: {e}")
        # optional jsonschema validation
        if sj.exists() and sch.exists():
            try:
                import jsonschema  # type: ignore
                jsonschema.validate(json.loads(sj.read_text()), json.loads(sch.read_text()))
            except ImportError:
                pass
            except Exception as e:
                warns.append(f"sidecar.json does not validate against schema: {e}")

    # LISTING.md hydrated pitch
    lst = bundle / "LISTING.md"
    if lst.exists():
        t = lst.read_text(errors="ignore")
        if "0 tool calls" not in t:
            warns.append("LISTING.md: should include '0 tool calls' hydrated pitch")
        if "70" not in t and "90" not in t:
            warns.append("LISTING.md: should include '70–90% API savings' pitch")

    # daemon
    cfg = bundle / "daemon/config.yaml"
    if cfg.exists():
        c = cfg.read_text(errors="ignore")
        if "entitlements" not in c:
            warns.append("daemon/config.yaml: entitlements.active missing (retainer gate)")
        if "interval" not in c:
            errs.append("daemon/config.yaml: interval missing")

    ok = len(errs) == 0
    msgs = []
    for e in errs: msgs.append(f" {e}")
    for w in warns: msgs.append(f" {w}")
    if ok and not warns:
        msgs.append(" all checks passed")
    elif ok:
        msgs.append(" valid (warnings only)")
    return ok, msgs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", nargs="?", help="path to bundle dir")
    ap.add_argument("--all", action="store_true", help="validate all bundles/*")
    args = ap.parse_args()

    targets = []
    if args.all or not args.bundle:
        targets = sorted([p for p in BUNDLES.iterdir() if p.is_dir() and (p / "SKILL.md").exists()])
        # also include bundles that may be category folders without SKILL.md
        if not targets:
            print(f"no bundles found in {BUNDLES}")
            sys.exit(1)
    else:
        targets = [Path(args.bundle)]

    all_ok = True
    for b in targets:
        ok, msgs = validate_one(b)
        print(f"\n{b.relative_to(ROOT) if b.is_relative_to(ROOT) else b}: {'PASS' if ok else 'FAIL'}")
        for m in msgs: print(m)
        if not ok: all_ok = False

    # summary
    print("\n" + ("All bundles PASS" if all_ok else "Some bundles FAIL — see above"))
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
