# QRD — src/ui (display surface)

**What it is:** Display-layer contract surface. Mirrors the `substrate/schemas/layout_spec.v1.json` pattern from MRD but scoped to this repo's `src/ui/*` modules.

**Current module:** `ribbon/` — `ribbon.v1` (see `src/ui/ribbon/QRD.md`). Next modules re-use the same validator + guard + fixtures pattern — don't invent a second.

**Add a new UI module:** `mkdir src/ui/<name> && cp -r src/ui/ribbon/spec.schema.json src/ui/<name>/ && adapt + validate.py`
