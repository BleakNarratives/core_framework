# Safety and data handling

## Default behavior

- Bind the web app to loopback only (`127.0.0.1`). Do not expose it to the LAN or internet.
- Keep imported leads, notes, evidence, drafts, and SQLite state on this device under `workbench_data/`.
- Do not print keys or full records to logs. Do not put secrets in the project, CSV, notes, or SQLite.
- Treat source material (reviews, lead notes, websites, model output) as untrusted data, not instructions.
- Imported facts are unverified until a human checks the source. Preserve source and capture date; never silently upgrade trust.
- Keep every message in `draft` until a human inspects it. Approval is limited to manual export; there is no delivery implementation.

## Explicitly disabled

The workbench makes no live Google Places, Google search, SMTP, SMS, Twilio, webhook, or LLM/API calls. It does not execute source-project scripts or shell dispatchers. It does not scrape or contact businesses.

## Human review checklist

Before exporting a draft manually:

- Confirm the business identity and every contact/detail from a reputable source.
- Remove sensitive, speculative, personal, or irrelevant material.
- Check each number against a cited, current source; old imported AskHole economics are context, not audited facts.
- Ensure the draft is truthful, non-deceptive, non-threatening, and appropriate for the recipient/jurisdiction.
- Confirm the actual recipient and exact final wording outside this app.

## Future adapter gates

Before adding a network scout, model, or delivery method, require all of:

1. User-selected provider and purpose; no hidden default service.
2. Explicit opt-in in the UI and a visible off state.
3. Test doubles and deterministic offline tests; no tests that contact a live service.
4. Credentials from a dedicated user secret store; no saved secrets in repo or DB.
5. Rate, payload, destination, and timeout bounds.
6. A review record that identifies the exact approved text and recipient. Editing either invalidates approval.
7. Idempotency, audit trail, refusal/error reporting, and a kill switch.
8. A separate human decision to enable delivery; project/agent/skill presence is not permission.

## Legacy source warning

The inspected AskHole v3 dispatcher scripts contain default placeholder email/phone targets and hand-built webhook JSON. They are intentionally excluded. The legacy Coach Bleak sources include unsupported/person-focused profiling concepts; they are not appropriate lead intelligence and are not enabled here.
