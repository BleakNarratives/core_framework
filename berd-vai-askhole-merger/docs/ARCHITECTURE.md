# Architecture

## Shape

```text
Browser (127.0.0.1:8765 by default; set `PORT=18765` when occupied)
  └── Flask control room + fixed wormhole catalog
       ├── live snapshot: Berdical SQLite + read-only Pytch/Whorl SQLite
       ├── selected unsent Pytch row → provenance/evidence copy into Berdical SQLite
       ├── human draft/review/hash-bound manual export workflow
       └── offline AskHole scenario math (source values labeled legacy/unverified)

Berd (optional desktop host)
  └── attached folder + user-created agents/skills from berd/ briefs

Ollama/local inference (future opt-in adapter; not called by MVP)
External scout/delivery integrations (disabled; future separately reviewed adapters)
```

## Components

- `app.py`: web UI, form handling, CSV import, export, and server entry point.
- `workbench.py`: SQLite repository and deterministic workflow logic.
- `integrations/economics.json`: compact AskHole economics input, with source labels explicitly marked unverified.
- `templates/` and `static/`: self-hosted control room, ring filters, signal list, project consoles, and local interactions. AIR filters to action-level signals while preserving wormhole navigation; TILT hides info/review/action at 35/70/92% pressure. No seasonal event theme or external browser assets.
- Dashboard metrics come from uncapped SQLite `COUNT(*)` queries for leads, unverified evidence, and drafts; they are local inventory counts, not market claims.
- `berd/`: persona and skill guidance that can be manually loaded into Berd.
- The Pytch read-only source connector queries fixed tables and never imports/executes Pytch code. A selected unsent row is staged into a local draft; content and recipient hashes preserve provenance, raw recipient addresses are omitted from the staging response, and staging is idempotent by source record ID. Review requires checking the recipient against Pytch; manual export requires a separate confirmation. The disposable-SQLite click-through test verifies the source row remains unchanged.
- `tests/`: stdlib `unittest` tests using temporary databases, no network.

## Records

- **Lead:** source system, name, vertical, location, optional public business fields, operator notes, timestamps.
- **Evidence:** lead, claim/value, source label, collection time, SHA-256 of content, trust state (`unverified`). Evidence does not prove truth.
- **Draft:** lead, rendered text, economics snapshot, evidence IDs, status (`draft`, `reviewed`, `approved-for-manual-export`), timestamp.
- **Review:** reviewer role, findings, verdict, timestamp. Review is not a send authorization.
- **Audit event:** bounded event name and record IDs. Do not put credentials, message bodies, or unnecessary personal details in event metadata.

## Workflow and privilege boundaries

1. User imports or enters data, or selects an unsent Pytch row. The importer accepts values, not executable content; Pytch is queried through fixed read-only SQL.
2. Evidence is labeled with a source and remains unverified. Free-text is never interpreted as instructions. Pytch source body is copied exactly into a local draft, while recipient data is represented by a hash until the reviewer checks it against the source.
3. Deterministic draft generation uses a known vertical economics dictionary and explicitly marks numbers as contextual estimates, not independently verified estimates. Pytch drafts preserve the exact original body instead of rewriting it.
4. Human review records findings and, for Pytch, validates the recipient against its source hash. Review and approval do not authorize sending.
5. Human approval can mark the exact hash-bound draft ready for manual export. It never enables network delivery; export is a download only.

## Extension points

Any future network scout or delivery adapter must be a separately configured component with bounded request sizes/timeouts, explicit destination allowlists, error handling, provenance, local mocks, tests, and a human approval boundary. Provider credentials must come from an OS/user secret store, never this project tree. Do not simply copy AskHole dispatch scripts or the Vertical AI SMTP example.

## Non-goals

- Not a modified Berd build, Goose extension, CRM, legal analyzer, or automatic sales agent.
- No claims that AI intake will improve a named business's outcomes.
- No automated web scraping, prospect enrichment, email, SMS, or webhook calls in the MVP.
