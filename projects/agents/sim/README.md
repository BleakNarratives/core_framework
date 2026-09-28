# Tideglass

Tideglass is an early, local-only prototype for exploring possible market
responses to a proposed action. This first slice is a transparent Monte Carlo
scenario sampler, not a trained predictive model or a claim about what the
market will do.

## Run a scenario

Scouting agents should pass structured **claims/observations**, with provenance,
separately from human-authored probability assumptions. The JSON contract uses
`action`, `stakeholders`, and optional `observations`. Unknown keys are rejected
so a misspelled field cannot silently change the meaning of a run. Observation
values are retained for audit/context and are deliberately not learned from.

Save a local scenario file, for example. Observations may also contain just a
qualitative `claim` (with no `metric`/`value`); `content_sha256` is optional:

```json
{
  "action": "Offer a small paid pilot",
  "stakeholders": [
    {
      "name": "early adopters",
      "adoption": {"low": 0.4, "likely": 0.6, "high": 0.8},
      "competitor_response": {"low": 0.2, "likely": 0.4, "high": 0.6},
      "regulatory_pushback": {"low": 0.0, "likely": 0.1, "high": 0.3}
    }
  ],
  "observations": [
    {
      "source": "https://example.test/report",
      "observed_at": "2026-09-27T00:00:00Z",
      "claim": "The report says 25 people signed up for the pilot.",
      "metric": "pilot signups",
      "value": 25,
      "unit": "people",
      "verified": false
    }
  ]
}
```

Run locally; output is JSON suitable for another offline pipeline step:

```bash
python -m projects.agents.sim.tideglass scenario.json --runs 2000 --seed 17
```

The same scenario and seed yield the same output. Invalid, oversized, duplicate-key,
or unknown-field files fail closed with a nonzero exit status. Scenario files
cannot self-assert verified evidence. The CLI does not fetch observation URLs.

The Python API remains available from the repository root:

```python
from projects.agents.sim.tideglass import (
    ProbabilityRange,
    Stakeholder,
    simulate_market_response,
)

stakeholders = [
    Stakeholder(
        "early adopters",
        adoption=ProbabilityRange(0.4, 0.6, 0.8),
        competitor_response=ProbabilityRange(0.2, 0.4, 0.6),
        regulatory_pushback=ProbabilityRange(0.0, 0.1, 0.3),
    ),
    Stakeholder(
        "incumbents",
        adoption=ProbabilityRange(0.1, 0.2, 0.4),
        competitor_response=ProbabilityRange(0.5, 0.7, 0.9),
        regulatory_pushback=ProbabilityRange(0.1, 0.3, 0.5),
    ),
]

report = simulate_market_response(
    "Offer a small paid pilot",
    stakeholders,
    runs=2_000,
    seed=17,
)
print(report.to_dict())
```

## Scout and BI architecture

The monitor at `site_monitor.py` checks Swarms Marketplace category pages
(agents, prompts, tools, bundles) and TAAFT's `just-released` feed. It discovers
same-origin HTTPS listing links and same-origin sitemap URLs; it does not use a
browser, run site JavaScript, or call an undocumented listing API. Whether every
listing is discoverable depends on each site's public HTML/sitemap and robots
policy, so this is a bounded metadata monitor, not a guarantee of a complete
archive. Per source it stores at most 20,000 listing records.

Each invocation checks at most 30 listing/detail pages total by default, reads
and caches each site's `robots.txt`, rate-limits per host, uses conditional HTTP
validators when offered, and checkpoints pending discovery/detail URLs. For a
large first scan, run it repeatedly and inspect `pending_urls` in the JSON output
until queued work is drained; the first pass records a baseline, and subsequent
discoveries emit `new` events. Metadata changes emit `updated`; known detail
pages are refreshed every six hours by default. A 429/503 persists a bounded
backoff and stops further requests to that site for the invocation. Robots
fetch failures or disallowed URLs are not bypassed.

A project-local GitHub Actions workflow is provided at
`.github/workflows/tideglass-daily-monitor.yml`. It runs daily at 12:17 UTC and
can also be started manually with `workflow_dispatch`. It restores and saves the
state file with the Actions cache, runs one bounded poll, then publishes the
report as the workflow summary and a 30-day artifact. As with any cache, state
retention is best-effort; if the cache is evicted, the monitor must establish a
new baseline. Scheduled workflows run only when this workflow is present on the
repository's default branch and Actions are enabled. No host cron job is
installed.

The scheduled workflow makes real public HTTP requests. Review the workflow and
robots policy before enabling Actions; it uses no credentials and requests no
write permission to repository contents.

Run once from the repo root:

```bash
python -m projects.agents.sim.site_monitor --state .tideglass-monitor.json
```

Print a concise report for today's UTC date using saved events only (no crawl):

```bash
python -m projects.agents.sim.site_monitor --state .tideglass-monitor.json --daily-report
```

Choose a date explicitly when reviewing older discoveries:

```bash
python -m projects.agents.sim.site_monitor --state .tideglass-monitor.json --daily-report --date 2026-09-27
```

The report counts only `new` events for that UTC day, groups them by source and
URL-path category, and shows up to five example listings. Categories are simple
path-based labels, not an AI-generated interpretation of what is trending. The
state file contains compact listing metadata and a bounded event history, not
full page bodies. Add `.tideglass-monitor.json` to your local ignore rules if
you choose a different tracked working directory. Listing content remains
unverified and is not used as executable instructions or training data.

`bi_scouts.py` provides a separate bounded specialist-coordination interface.
Caller-supplied runners can analyze collected findings concurrently, but this
project does not yet wire an LLM framework or turn findings into forecasts.
Keep source claims untrusted until independently checked. Swarms framework was
not found as an installed/project dependency, so no Swarms import is required.

## Trust boundary

- `Stakeholder` probability ranges are explicit human assumptions. Each range
  contains low, most-likely, and high probabilities for a triangular sampler.
- `MarketObservation` records a source and observation time, plus a qualitative
  `claim`, numeric `metric`/`value`, or both. Optional `content_sha256` carries a
  Scout-supplied digest; Tideglass does not verify it or authenticate the source.
  The JSON loader forces `verified` to false and rejects attempts to self-assert
  verification. Observations remain provenance context and never change the
  simulation until a separately tested calibration method is introduced.
- Output metrics are simulated shares of stakeholder archetypes with adoption,
  competitor response, or regulatory pushback. Samples are independent by
  assumption; they are not headcounts, market shares, or empirical forecasts.
- Site-monitor records and Scout reports are unverified discovery artifacts,
  not verified facts, forecasts, investment advice, or permission to use a
  listing. TAAFT's robots policy allows search/reference, explicitly disallows
  AI training; Tideglass does not train on monitored content.
- A seed makes runs reproducible. The report labels the model
  `uncalibrated` and includes a caveat rather than implying predictive validity.
- There are no network calls, provider/model calls, or third-party dependencies.

Verify with:

```bash
python -m unittest tests.test_tideglass tests.test_tideglass_polymarket tests.test_tideglass_bi_scouts tests.test_tideglass_site_monitor -v
```
