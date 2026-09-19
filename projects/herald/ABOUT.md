<!-- The `--about` paragraph, and nothing else. This file is fed verbatim to
     `outreach_agent --about-file ABOUT.md`, so every word in it is prompt tokens
     and every sentence in it is a claim the model may repeat. Evidence for each
     claim, the narrow variants, and the list of things the model may NOT claim
     live in ABOUT_EVIDENCE.md. Do not grow this file: see the note at the bottom
     of that one. -->

I make LLM coding agents cheap enough and contained enough to run on hardware you
already own. I run a self-hosted, OpenAI-compatible gateway fronting twelve provider
pools that rotates keys per provider, so a 429 cools one key instead of ending the
run and a revoked key gets quarantined instead of retried forever. The client on top
of it is stdlib-only Python: ~25 MB resident against 436–566 MB measured for the
commercial client on the same machine, 79 tests, no animation loop. I also wrote the
containment that makes an agent safe to leave running — file edits and shell commands
approved as separate tiers, and every path-taking tool confined to the working
directory by resolving the path, not by asking the model nicely. It is all code you
can read and run. I take small fixed-price jobs with a defined end; no retainers.
Based in [TIMEZONE]. [YOUR RATES OR "rate on request"].
