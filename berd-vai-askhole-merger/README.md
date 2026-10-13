# Berdical AI — Local Outreach Review Control Room

**Purpose:** review unsent outreach without accidentally sending it. See actual local project signals, choose an unsent Pytch item, stage a provenance-linked copy, review its source text, and export only after human approval. The original Pytch database remains read-only.

**Project status:** usable offline MVP; network scouting and message delivery are intentionally disabled. All generated outreach is a draft for human review.

## What it does

- Imports a local CSV of businesses or accepts a single lead in the web UI.
- Adds AskHole's local vertical economics and user-supplied evidence with provenance labels.
- Produces a deterministic first-pass outreach draft without requiring an LLM or API key.
- Stores leads, evidence, drafts, approvals, and audit events in a local SQLite database.
- Provides separate Berd personas and skills for research, hard-nosed review, and compliance checks.
- Hides a Type III force-multiplier easter egg on each lead page: exactly three cross-project use-case potentials, explicitly exploratory and never treated as a lead score.
- Runs in a small Flask UI on `127.0.0.1`.

## Start on ChromeOS

Berd and the local model are optional. Python 3.10+ and Flask are required; Flask is already present in this ChromeOS Linux environment.

```bash
cd ~/berd-vai-askhole-merger
python3 app.py
```

Open **http://127.0.0.1:8765** in Chrome. If that port is already occupied, run `PORT=18765 python3 app.py` and open **http://127.0.0.1:18765** instead. Stop the server with Ctrl+C.

Check the project without contacting services:

```bash
python3 -m unittest discover -s tests -v
```

## First workflow

1. Open **Pytch → unsent queue** from the signal room.
2. Choose one row and **Stage for review**. Berdical copies its business/source/body evidence into its own ledger; it does not modify Pytch or copy the raw email address.
3. Review the lead provenance and source body, then generate a conservative draft.
4. Record a human review; approve the exact text hash for manual export.
5. Export manually. **No email, SMS, webhook, scraping, or automatic contact is implemented.**

Independent intake remains available at `/intake`.

CSV import example:

```csv
name,vertical,city,website,rating,review_count,notes
Example Plumbing,plumber,Example City,,4.1,18,"Manually supplied notes; source: owner-provided spreadsheet"
```

## Berd setup

Berd is already installed separately on this machine. Start Berd, then create a project that attaches only this directory. For example, from the Linux terminal:

```bash
~/.local/share/xyz.block.berd/bin/berdctl project create \
  --name "Berdical AI" \
  --instructions "Use this project's local-first workflow. Keep all messages as drafts; never contact leads." \
  --working-dir "$HOME/berd-vai-askhole-merger"
```

If Berd's CLI is not available in the current app session, create the project through Berd's UI and choose this directory. Agent and skill instructions are in `berd/`; importing them into Berd's saved personas/skills is an explicit separate action.

## Source map

- `vertical_ai/`: legacy review discovery and outreach prototype. Its live Google scraping and SMTP example are **not imported or executed**.
- AskHole v3 intake: economics data and compact direct-response structure are adapted. Its network providers and shell dispatchers are **not copied**.
- `vertical_ai_engine/`: Coach Bleak / Veritas legacy analysis/FOIA prototype. Catalogued as a separate archive, not merged as factual lead intelligence.
- Berd: desktop project/persona/skill/session host. The workbench is an ordinary attached folder, not a Berd plugin or modification to Block's app.
- Local tool chain: deterministic Python + SQLite + Flask now; optional Ollama and Berd agent personas for later reviewed assistance.

See `docs/ARCHITECTURE.md`, `docs/SAFETY.md`, `docs/SOURCES.md`, and `docs/ROADMAP.md` before extending the prototype.
