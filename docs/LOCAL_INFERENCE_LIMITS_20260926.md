# Local inference on this box — measured limits

Date: 2026-09-26. Everything below is a measurement, not an estimate. Commands
and outputs are reproducible; the numbers will differ on a different host.

## Host

| property | value |
|---|---|
| kernel | `6.6.147-09642-gea7f90d2e99e` (custom, ChromiumOS-derived: `/opt/google/cros-containers`) |
| distro | Debian 13 (trixie), container |
| CPU | Intel N200, 4 cores, no GPU |
| RAM | 2.6 GiB total |
| swap | 6.0 GiB `/swapfile` at priority -2 |
| disk | 17–22 GiB free |

## The binding constraint is RAM, and the agent is the competitor

The resident agent stack holds roughly 500 MB before any model loads:

```
PID 29116  223 MB  freebuff (python)
PID 30124  125 MB  next-server
PID 30158   74 MB  freebuff (node wrapper)
```

A 1.3 GB model therefore lands on a box with ~600 MiB available. That is the
whole story; everything below is a consequence.

## zram is NOT available here — do not retry

This is the one that costs the most time to rediscover.

```
$ sudo modprobe zram num_devices=1
modprobe: FATAL: Module zram not found in directory /lib/modules/6.6.147-09642-gea7f90d2e99e
$ ls /lib/modules/
ls: cannot access '/lib/modules/': No such file or directory
```

`/lib/modules` **does not exist**. The host supplies a custom kernel and the
container has no module tree, so no loadable modules are available. zram is
also not built into the kernel (`/dev/zram*` absent). The `zram-tools` package
installs and `zramswap.service` enables cleanly, then fails at start with
`Module zram not found`.

`zramswap.service` has been disabled again and `/etc/default/zramswap`
restored to its packaged state, so it does not fail on every boot.

## Measured model behaviour

| model | size | result |
|---|---|---|
| `gemma:2b` | 1.7 GB | never completed in 300 s. 109 GB paged out, load avg 13 on 4 cores, benchmark process wedged in `D` state |
| `llama3.2:1b` | 1.3 GB | works. **4.12 gen tok/s** at session start, 20.6 s one-time load |

`llama3.2:1b` produces correct, coherent answers. The 1B class is genuinely
usable here; 2B is not.

### Throughput decays as the session grows

Same model, same parameters, measured hours apart:

```
early in session   num_ctx=512  num_thread=2  ->  4.12 tok/s, 33.5 s total
later in session   num_ctx=512  num_thread=2  ->  FAILED (timeout)
later in session   num_ctx=1024 num_thread=2  ->  2.17 tok/s, 25.0 s load
```

Available memory fell from ~885 MiB to ~234 MiB over the session while swap
climbed to 2.3 GiB. A model that fits at session start does not fit by the end
of one. This is a shared-box ceiling, not a misconfiguration.

### Thread count: fewer is faster

`num_thread=4` was **slower** than `num_thread=2` (51.7 s vs 33.5 s) and the
model was evicted and reloaded (16 s), because all 4 cores are shared with the
agent. Do not "use all cores" on this host.

## Current Ollama configuration

`/etc/systemd/system/ollama.service.d/limit.conf`, applied and active:

| setting | value | why |
|---|---|---|
| `OLLAMA_KEEP_ALIVE` | `60s` | default 5m pins 1.3 GB against the agent; a reload is cheaper than an OOM kill |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | no second resident model |
| `OLLAMA_NUM_PARALLEL` | `1` | concurrency here just thrashes |
| `OLLAMA_CONTEXT_LENGTH` | `1024` | 2048 timed out at 120 s; 1024 is the only setting that reliably completed |

`llama3.2:1b` is the model that is installed and working. `gemma:2b` was
removed after it proved unable to run.

## What would actually change the ceiling

1. **More RAM.** The only real fix. 4–8 GB makes the 2–3B class viable and
   would remove the thrash entirely. Cannot be done from inside the container.
2. **A GPU.** Not present. Moves the problem off the 4 shared cores.
3. **Running the model when the agent is not resident.** The contention is
   agent-vs-model, so time-slicing them beats swapping between them.

## Speculative decoding: unavailable here, still the best next win

Verified blockers, not assumptions:

1. `ollama 0.34.4` exposes **no** speculative/draft flags at all
   (`ollama serve --help` confirms).
2. No `llama.cpp` binary is installed. Building it would need the target model
   (505 MB resident) *plus* a draft model *plus* a C++ link, against 546 MiB
   available. That OOMs.

It is still the highest-value remaining win: 2-3x on CPU with a small draft
model. Enablement steps are in `docs/SESSION_COMPLETION_20260926.md`.

Related levers that are real but also memory-bound on this host: MoE (fixes
FLOPs, not bytes -- a 30B-A3B at 4-bit is still ~16 GB resident), KV-cache
quantization, and IQ-quants at 2-3 bits.

## What did NOT work (do not repeat)

- zram: no module tree (§ above).
- `gemma:2b`: thrashes to death.
- More threads: actively slower.
- Larger context: actively slower.
- Speculative decoding via ollama: not supported.
