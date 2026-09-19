# Blue Sky Meeting — CLI MVP

Blue Sky Meeting is a local-first collaboration room for assembling agents,
applications, webpages, and humans around a brief. This first slice is deliberately
small and offline: it manages rooms, participants, briefs, deterministic rounds,
events, and exports without contacting providers or executing external agents.

## Quick start

From the repository root:

```bash
python -m projects.blue_sky_meeting.blue_sky --state-dir .blue-sky create-room launch-plan --label "Launch Plan"
python -m projects.blue_sky_meeting.blue_sky --state-dir .blue-sky add-agent launch-plan strategist --role "brand strategist" --adapter builtin
python -m projects.blue_sky_meeting.blue_sky --state-dir .blue-sky set-brief launch-plan --text "Create a launch plan for a local-first AI collaboration console."
python -m projects.blue_sky_meeting.blue_sky --state-dir .blue-sky run launch-plan --rounds 2
python -m projects.blue_sky_meeting.blue_sky --state-dir .blue-sky export launch-plan --format markdown --out launch-plan.md
```

## Current contract

- Room state is JSON under the selected state directory.
- Every mutation appends an event with actor, action, and timestamp.
- Participants carry an adapter name governed by an explicit adapter protocol.
- Only the deterministic `builtin` adapter is enabled in v0.1; external adapter names cannot execute anything.
- Every contribution carries provenance and `requires_approval: true`.
- Exports contain no credentials and do not send or publish anything.

## Next seams

1. Implement isolated CLI, local model, webpage, and API adapters behind the protocol.
2. Human approval gates before external execution.
3. Branching/merging of room ideas.
4. Thin local dashboard over the same room JSON/event contract.
