# AUTOMATION BUDGET

Measured 2026-09-15, uptime 23h37m. Every number here came from systemd's own
accounting (`systemctl --user show <unit> -p CPUUsageNSec`), not from estimation.
Re-run the measurement before trusting this after a change; it is a snapshot, not
a law.

## The headline that overturns the assumption

The five-minute timers were suspected of being the load. **They are not.**

| Service | CPU used | Nature |
|---|---|---|
| `cros-garcon.service` | **37,032.99s** | Chromebook container infra — **not ours** |
| `overseer-daemon.service` | **321.96s** | continuous daemon |
| `implore-research.service` | **256.91s** | continuous daemon |
| `codebuff-bridge.service` | 37.78s | |
| `kilo-dvm-health.service` | 29.13s | timer, twice daily |
| `higgins-kindred.service` | 14.55s | **Higgins is alive and running** |
| `round-engine.service` | 4.04s | 5-minute timer |
| `agent-asset-snapshot.service` | 2.07s | timer |
| `ai-gateway.service` | **1.28s** | ours — a full day of key rotation for ~1s |
| `swarm-orch.service` | 1.12s | 5-minute timer |
| **total across 30 services** | **37,713.9s** | |

Excluding Chromebook infrastructure, the entire owned stack costs roughly
**681s of CPU per day**. Two daemons — `overseer-daemon` and
`implore-research` — are **579s of that 681s, about 85%**.

## CORRECTION — the "85%" reading was wrong

The sentence that used to sit here claimed those two daemons were 85% of owned
CPU and were the thing to chase. **That was a misreading, and it is precisely the
trap this document's own caveats section warns about.** Those numbers are
*cumulative CPU since the units started on 2026-09-14 13:22* — about 24 hours of
wall clock, not a share of load.

Checked live instead of inferred:

| Unit | CPU now | RSS now | Service memory |
|---|---|---|---|
| `overseer-daemon` | 0.2% | 10.2 MB | 28.7 MB |
| `implore-research` | 0.3% | 5.3 MB | 2.4 MB |

301s of CPU across 86,400s of wall clock is **~0.35% average**. Both daemons are
steady, cheap and long-lived. Neither is a drain. Neither should be touched on
this evidence.

**Where the load actually is:**

- `cros-garcon` — 37,033s CPU. Chromebook container infrastructure, not this repo,
  and not something a change here can fix.
- **The Freebuff client — 436–566 MB RSS and 45–80% CPU**, measured the same day.

The largest discretionary consumer on this box is the agent client itself. That
is the entire argument for `projects/lean` (25.1 MB, idle CPU), and it
is a stronger argument than anything in this table.

**Conclusion that survives both readings: adding more timers is cheap.** What is
not cheap is a resident client. Optimize there, not here.

## Memory, at the same moment

```
total 2680 MB   used 1704 MB   free 194 MB   available 976 MB
load average: 1.44, 1.23, 1.02
```

194 MB free on a 2,680 MB box with load above 1.0. This is the real constraint,
and it is why the Freebuff client holding 436–566 MB mattered as much as it did.

## The collision window

Three things fire inside the same 8-second span at the top of every hour:

```
:00:00  cron  whorl-automation/staggered_trigger.sh
:00:38  timer swarm-orch.service
:00:42  timer fleet-dashboard.service
```

Then, still inside the same hour:

```
:15     cron  Whorl/scripts/guard_daemon.sh
:20     timer canon-guard.service
```

Scheduling something new at `:00`, `:15` or `:20` puts it on top of existing
work. That is the whole reason to pick windows deliberately instead of by feel.

## The off-peak definition (derived, not assumed)

| Window | Verdict | Use for |
|---|---|---|
| **01:00–06:00** | **Best** | anything CPU-bound: validation sweeps, catalogue refreshes, backups, analysis |
| 06:00–09:00 | Good | medium work; machine is warming up |
| **:00, :15, :20 of any hour** | **Avoid** | collision with the table above |
| 09:00–23:00 | Peak | interactive work only — this is when you are actually using the box |
| 23:00–01:00 | Fair | the hourly cron still runs; nothing else is awake |

Practical rule: **put new heavy work at 03:00**, which sits inside the best window
and collides with nothing measured here.

## What this changes

1. **Do not add timers to save CPU.** They cost ~1–4s per day each. The instinct
   that "more timers = more load" is not supported by these numbers.
2. **Do not chase `overseer-daemon` or `implore-research`.** See the correction
   above: they average ~0.35% CPU each. The instinct to blame the biggest
   cumulative number is the mistake this doc already made once.
3. **`ai-gateway` is effectively free** (1.28s/day), so routing more tools through
   it costs nothing measurable. This removes the last argument against
   centralizing every CLI through the gateway.
4. **The recurring memory problem is not the timers either.** 194 MB free with
   daemons resident — that is a resident-set question, not a schedule question.

## Honest caveats

- CPU seconds are **cumulative since boot**, not per-invocation. A 5-minute timer
  that has run 280 times and used 4s total is genuinely cheap; the number does not
  distinguish "runs often and is cheap" from "ran once and was expensive."
- `cros-garcon` is included only because it dominated the listing and excluding it
  silently would have made the table misleading. It is Chromebook infrastructure
  and outside this repo's control.
- No per-invocation timing was captured. If a specific timer is suspected, the
  precise tool is `systemd-analyze blame` or per-run timing in the unit itself.
- Load average includes time before this session. It is a rough signal, not
  attribution.
