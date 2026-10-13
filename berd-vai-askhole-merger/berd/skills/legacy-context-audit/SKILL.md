---
name: legacy-context-audit
description: Audit imported Vertical AI, AskHole, or Coach Bleak material for provenance, reliability, relevance, and unsafe behavior before use.
---

# Legacy context audit

For each candidate legacy artifact, report its path, stated purpose, observed implementation, provenance, trust state, and allowed use. Do not execute it during an audit.

- AskHole economics values are legacy estimates with source names as supplied; source names are not independent verification.
- AskHole's dispatcher scripts and Vertical AI's SMTP example are not safe to reuse without replacing their placeholder recipient behavior and adding explicit approval.
- Vertical AI's Google scrape example is a live network action. Do not run it as part of importing.
- Coach Bleak/Veritas is a separate legacy analysis/FOIA project. Do not use its person profiling, psychological, or accusation-like features for lead outreach.
- Berd is a separate desktop agent host, not a plugin runtime granted access to all workspace files.

Return a source-to-claim map, trust labels, and a concise list of excluded components. Preserve uncertain items as uncertain.
