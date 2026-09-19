<!-- A product-role variant of the offer, and nothing else. Like ABOUT.md this file
     is fed verbatim to `outreach_agent --about-file`, so it is one paragraph.

     Why it exists: `ABOUT.md` pitches coding-agent cost and containment, which is
     infrastructure. Measured 2026-09-17 on the same 30 leads with a pinned model,
     that file drafted 1 lead and the one-line "backend engineer, Python,
     architecture refactoring, automation" drafted 9 -- because most "Who is hiring?"
     posts are product roles, and the model correctly refused them. This is that
     broader offer, kept inside claims ABOUT_EVIDENCE.md can still prove. -->

I build and harden Python backends, and I wire LLM features into products without
letting the spend or the agent run away. I work one bounded piece at a time — a
service, an endpoint, a tangled module — at a fixed price, and I leave the repo with
tests and a change log rather than a rewrite. The pieces I have built myself are the
same shape: a stdlib-only coding client at ~25 MB resident against 436–566 MB measured
for the commercial one on the same machine, with 79 tests; a self-hosted gateway
fronting twelve provider pools that cools a single key on a 429 instead of failing the
run; and a containment model where editing files and running shell are two separate
approvals, with every path-taking tool confined to the working directory by resolving
the path rather than by asking the model nicely. It is all code you can read and run.
I take small fixed-price jobs with a defined end; no retainers. Based in [TIMEZONE].
[YOUR RATES OR "rate on request"].
