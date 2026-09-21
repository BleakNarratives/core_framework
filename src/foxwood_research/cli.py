"""Command-line interface for Foxwood Research Ledger."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ledger import ResearchLedger
from .pipe import (
    DEFAULT_SEED,
    LENSES,
    LENS_BY_NAME,
    PROMPT_CHAR_BUDGET,
    find_bin_ai,
    frame_prompt,
    lens_plan,
    load_verdicts,
    plan_label,
    resolved_keys,
    run_pipe,
    verdict_key,
)
from .registry import RegistryGate, RegistryUnavailable
from .diversity import DEFAULT_SEED_RANGE, measure_diversity
from .sources import CrossrefAdapter, OpenAlexAdapter, discover
from .synthesis import SynthesisError, synthesize

# A refusal is a legitimate finding and exits 0. A reply the pipe could not turn
# into citation-gated claims, or a gateway failure, exits 1 -- otherwise a broken
# pipe reports success, the failure herald recorded when six echoed prompts were
# written as six drafts.
_OK_VERDICTS = frozenset({"accepted", "no_evidence"})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="foxwood-research", description="Provenance-first public research discovery")
    parser.add_argument("--store", default="foxwood_data/ledger", help="ledger directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="search public bibliographic metadata")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--provider", choices=("openalex", "crossref", "both"), default="both")
    search.add_argument("--json", action="store_true", dest="as_json")

    synthesis = subparsers.add_parser("synthesize", help="turn saved sources into citation-gated claims")
    synthesis.add_argument("query")
    synthesis.add_argument("--source-id", action="append", dest="source_ids", required=True)
    synthesis.add_argument("--output", type=Path)

    pipe = subparsers.add_parser(
        "pipe",
        help="evidence -> seeded lens -> Oracle-audited, citation-gated claims")
    pipe.add_argument("query")
    pipe.add_argument("--source-id", action="append", dest="source_ids", required=True)
    pipe.add_argument("--seed", type=int, default=DEFAULT_SEED,
                      help=f"selects the lens; same seed and evidence = same question (default {DEFAULT_SEED})")
    pipe.add_argument("--lens", default="auto", choices=("auto", *(lens.name for lens in LENSES)),
                      help=f"override the seed's lens choice; known lenses: {', '.join(LENS_BY_NAME)}")
    pipe.add_argument("--rounds", type=int, default=1,
                      help="how many lenses to ask in sequence; later rounds carry the "
                           "earlier rounds' open questions, and the last round wins")
    pipe.add_argument("--model", default=None,
                      help="pin the model. Unpinned runs resolve to `auto`, which rotates "
                           "gateway pools and is therefore not reproducible")
    pipe.add_argument("--registry", default=None,
                      help="path to PROVENANCE.md (default: discovered by walking up)")
    pipe.add_argument("--output", type=Path)
    pipe.add_argument("--dry-run", action="store_true",
                      help="print each framed prompt and write nothing; calls no model")
    pipe.add_argument("--redo", action="store_true",
                      help="ask again even though this (seed, lens, evidence) is already "
                           "recorded in the verdict ledger")
    pipe.add_argument("--prompt-budget", type=int, default=PROMPT_CHAR_BUDGET,
                      help=f"max prompt characters framed in one call (default {PROMPT_CHAR_BUDGET}); "
                           "the per-frame source count stays enforced either way")

    diversity = subparsers.add_parser(
        "diversity",
        help="prove the pipe asks varied questions reproducibly; calls no model, "
             "exits 1 if the framing went static")
    diversity.add_argument("--source-id", action="append", dest="source_ids", required=True)
    diversity.add_argument("--seeds", type=int, default=len(DEFAULT_SEED_RANGE),
                           help=f"how many consecutive seeds to probe from 0 "
                                f"(default {len(DEFAULT_SEED_RANGE)})")
    diversity.add_argument("--rounds", type=int, default=1)
    diversity.add_argument("--registry", default=None)
    diversity.add_argument("--markdown", action="store_true",
                           help="print the full report instead of the one-line verdict")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    ledger = ResearchLedger(Path(args.store))
    if args.command == "search":
        adapters = []
        if args.provider in {"openalex", "both"}:
            adapters.append(OpenAlexAdapter())
        if args.provider in {"crossref", "both"}:
            adapters.append(CrossrefAdapter())
        records = discover(args.query, ledger, adapters, limit=args.limit)
        if args.as_json:
            print(json.dumps([record.__dict__ for record in records], indent=2))
        else:
            print(f"Foxwood found {len(records)} source(s) for: {args.query}")
            for record in records:
                print(f"[{record.source_id}] {record.title}")
                print(f"  {record.url}")
                print(f"  {record.publisher}; hash={record.content_hash}")
        return 0
    if args.command == "synthesize":
        packet = synthesize(args.query, ledger, args.source_ids)
        rendered = packet.to_markdown(ledger)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(args.output)
        else:
            print(rendered, end="")
        return 0
    if args.command == "pipe":
        try:
            gate = RegistryGate(args.registry) if args.registry else RegistryGate()
        except RegistryUnavailable as exc:
            print(f"provenance registry unavailable: {exc}", file=sys.stderr)
            return 1
        ids = list(dict.fromkeys(args.source_ids))
        try:
            sources = [ledger.get_source(source_id) for source_id in ids]
            for source in sources:
                gate.admit(source.origin, source.url)
            plan = lens_plan(args.seed, args.rounds, args.lens)
        except Exception as exc:
            print(f"cannot run the pipe: {exc}", file=sys.stderr)
            return 2
        label = plan_label(plan)

        # The per-frame source count is deliberately not overridable from here:
        # bounded payload is the trust boundary this pipe exists to hold.
        if args.dry_run:
            if not args.lens or args.lens == "auto":
                print(f"  seed {args.seed} selected lens: {label}")
            for index, step in enumerate(plan, start=1):
                frame = frame_prompt(step, args.query, sources, seed=args.seed,
                                     round_index=index, rounds=len(plan))
                print(f"\n--- prompt: {frame.headline()} "
                      f"({len(frame.prompt)} chars) ---")
                print(frame.prompt)
            print(f"\ndry run: {len(plan)} prompt(s); no model called, nothing written")
            return 0

        answer_key = verdict_key(label, ids)
        if not args.redo and answer_key in resolved_keys(load_verdicts(ledger.root)):
            print(f"  already answered: seed {args.seed}, lens {label} over these sources "
                  f"(--redo to ask again)")
            return 0

        if args.model:
            print(f"  model pinned: {args.model}")
        else:
            print("  no --model given: bin/ai resolves to `auto`, which rotates gateway "
                  "pools; pin it before comparing two runs")
        if find_bin_ai() is None:
            print("  no bin/ai found by walking up; pass complete= from Python instead",
                  file=sys.stderr)

        try:
            run = run_pipe(args.query, ledger, ids, seed=args.seed, lens=args.lens,
                           rounds=args.rounds, model=args.model, registry=gate,
                           prompt_budget=args.prompt_budget)
        except SynthesisError as exc:
            print(f"pipe refused before asking: {exc}", file=sys.stderr)
            return 2

        rendered = run.to_markdown(ledger)
        print(f"  verdict: {run.verdict}" + (f" — {run.why}" if run.why else ""))
        for finding in run.findings:
            mark = "BLOCKING" if finding.blocking else "advisory"
            print(f"    ({mark}) {finding.rule}: {finding.message}")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(args.output)
        else:
            print(rendered, end="")
        return 0 if run.verdict in _OK_VERDICTS else 1
    if args.command == "diversity":
        try:
            gate = RegistryGate(args.registry) if args.registry else RegistryGate()
            report = measure_diversity(ledger, list(dict.fromkeys(args.source_ids)),
                                       seeds=range(max(1, args.seeds)),
                                       rounds=args.rounds, registry=gate)
        except (RegistryUnavailable, ValueError, SynthesisError) as exc:
            print(f"cannot probe diversity: {exc}", file=sys.stderr)
            return 2
        if args.markdown:
            print(report.to_markdown(), end="")
        else:
            print(f"  {report.verdict}: {report.frames_built} frames over "
                  f"{len(report.seeds)} seeds, {len(report.lenses_reached)} lens(es) "
                  f"reached ({', '.join(report.lenses_reached)})")
            for problem in report.failures():
                print(f"    {problem}")
        # Non-zero when the pipe is static, so this can be a gate and not a report.
        return 0 if report.ok else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
