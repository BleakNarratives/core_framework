# Amend's "dna_tag Wiring Notes"

# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: provenance
# DEPS: dna_tag
# ROLE: What it actually takes to run dna_tag unattended, and what was verified on this machine
# AUTHOR: Amend (Codebuff) + BleakNarratives (operator)
# SESSION: 2026-09-23
# TIER: 3
# FKA: — (companion to tools/provenance/dna_tag.py)
# [/DNA_TAG]

> Written after a session in which I edited `dna_tag.py` to add an `--origin` flag, was told the
> edit was not wanted, and reverted it. **The tree is unmodified.** This file exists so the next
> agent does not repeat that edit, and does not have to rediscover the facts below by reading the
> source again.

---

## The claim that was wrong

I asserted the tagger "cannot be wired up" because `get_device_origin()` prompts on stdin. Half
true, and the useful half is the other one.

- **Verified:** `main()` calls `origin = get_device_origin()` *before* any branch, and
  `get_device_origin()` prompts via `input()` **and writes `~/.dna_tag_origin`** when the config is
  absent (`dna_tag.py`, CONFIG_PATH = `~/.dna_tag_origin`).
- **Verified on this machine:** `~/.dna_tag_origin` exists and contains `Crostini-Chromebook`.
  So it **does not prompt here**, and nothing had to change to run it unattended.

The failure was mine and it was the same one as everywhere else in that session: I reasoned from
the source instead of checking the machine. The check was one command.

---

## What actually works today, with zero source changes

```bash
# single file, fully non-interactive
python3 tools/provenance/dna_tag.py --file x.py \
    --pillar provenance --role "does the thing" --deps pathlib --tier 3

# batch — needs exactly one stdin line for the confirm
printf 'y\n' | python3 tools/provenance/dna_tag.py --auto-scan-dir <dir>
```

## Verified limits worth knowing

| limit | evidence | consequence |
|---|---|---|
| Only `*.py` is scanned | `root.glob("*.py")` in both `scan_dir()` and `auto_scan_dir()` | non-Python files get no tag from this tool, at all |
| `--author/--pillar/--role/--deps/--session/--tier` bind on the **`--file` path only** | field dict is built inside the `if args.file:` branch | on `--auto-scan-dir`, `infer_fields()` supplies the values and hardcodes `author="Bleak"`, `tier="3"` |
| batch confirm is one `input()` | `auto_scan_dir()` | pipeable; not a blocker |
| `--scan-dir` asks per file | `scan_dir()` | pipeable but the prompts interleave; prefer `--auto-scan-dir` |
| `has_tag()` returns `True` for unreadable files | `except (OSError, UnicodeDecodeError): return True` | unreadable files are silently skipped, by design |

## The gap that is real, and is *not* applied

An `--origin` flag would remove the last two things the tool cannot do unattended:

1. run with no `~/.dna_tag_origin` present, and
2. run **without the risk of writing** that config — which matters, because a stray unattended run
   on a fresh box would silently persist a device identity (`CONFIG_PATH.write_text(origin)`).

Both are real. **Neither was requested.** The change was written, reverted with
`git checkout -- tools/provenance/dna_tag.py`, and is not in the tree. If it is ever wanted, it is
a small addition — but it should be asked for, not volunteered, and it should not be applied to a
tool that already works on the machine it runs on.

---

## Tree state at end of session (for the next agent's `git status`)

Verified with `git status --short` and `git diff`:

- `tools/provenance/dna_tag.py` — **unmodified** (edit reverted; diff empty)
- `tests/test_dna_tag_offline.py` — **removed** (a test I wrote, then deleted on request)
- No other file in `tools/provenance/` was touched.

This file is the only thing left in this directory by this session.

*Unverified: nothing in this document was changed in the code it describes.*
