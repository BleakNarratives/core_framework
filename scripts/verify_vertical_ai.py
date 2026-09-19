#!/usr/bin/env python3
"""Offline manifest, syntax, import-resolution, and dry-run verifier.

This verifier intentionally does not import arbitrary project entrypoints. It
parses Python with the standard-library AST, checks declared local imports, and
runs only the explicitly supported deterministic ``vertical_local`` route and
debate smoke tests. It never reads credential files, contacts a network, starts
a web server, invokes an LLM, or writes project artifacts.

Usage:
    python scripts/verify_vertical_ai.py
    python scripts/verify_vertical_ai.py --json
    python scripts/verify_vertical_ai.py --project vertical_local
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECTS = (
    "vertical_ai",
    "vertical_local",
    "vertical_radar",
    "vertical_ai_engine",
)


@dataclass
class ProjectResult:
    project: str
    manifest: str
    passed: bool = True
    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.passed = False
        self.errors.append(message)


@dataclass
class Summary:
    passed: bool
    projects: list[ProjectResult]


def load_manifest(project: str, result: ProjectResult) -> dict[str, Any] | None:
    path = ROOT / project / "manifest.json"
    if not path.is_file():
        result.fail(f"manifest missing: {path}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result.fail(f"manifest unreadable: {exc}")
        return None
    required = {"schema_version", "id", "status", "entrypoints", "dependencies", "verification"}
    missing = sorted(required - set(data))
    if missing:
        result.fail(f"manifest missing fields: {', '.join(missing)}")
    if data.get("id") != project:
        result.fail(f"manifest id {data.get('id')!r} does not match directory {project!r}")
    result.checks.append("manifest schema")
    return data


def python_files(project: str, manifest: dict[str, Any], result: ProjectResult) -> list[Path]:
    declared = manifest.get("dependencies", {}).get("python_files", [])
    files: list[Path] = []
    for relative in declared:
        path = ROOT / project / relative
        if not path.is_file():
            result.fail(f"declared Python file missing: {relative}")
        else:
            files.append(path)
    result.checks.append(f"declared files ({len(files)})")
    return files


def local_module_index(project_root: Path) -> set[str]:
    names: set[str] = set()
    for path in project_root.rglob("*.py"):
        if path.name == "__init__.py":
            relative = path.parent.relative_to(project_root)
            if relative.parts:
                names.add(".".join(relative.parts))
        else:
            relative = path.relative_to(project_root).with_suffix("")
            names.add(".".join(relative.parts))
    return names


def resolve_local_import(project_root: Path, source: Path, module: str, level: int = 0) -> bool:
    """Resolve only imports that can belong to this workspace."""
    if level:
        base = source.parent
        for _ in range(level - 1):
            base = base.parent
        candidate = base.joinpath(*module.split(".")) if module else base
        return candidate.with_suffix(".py").is_file() or (candidate / "__init__.py").is_file()

    parts = module.split(".")
    candidate_module = project_root.joinpath(*parts).with_suffix(".py")
    candidate_package = project_root.joinpath(*parts, "__init__.py")
    return candidate_module.is_file() or candidate_package.is_file()


def check_syntax_and_imports(project: str, files: list[Path], result: ProjectResult) -> None:
    project_root = ROOT / project
    local_names = local_module_index(project_root)
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            result.fail(f"syntax error in {path.relative_to(project_root)}: {exc}")
            continue
        result.checks.append(f"syntax: {path.relative_to(project_root)}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [(alias.name, 0) for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [(node.module or "", node.level)]
            else:
                continue
            for module, level in imports:
                if level:
                    if not resolve_local_import(project_root, path, module, level):
                        result.fail(f"unresolved relative import in {path.relative_to(project_root)}: {'.' * level}{module}")
                elif module.split(".", 1)[0] in {name.split(".", 1)[0] for name in local_names}:
                    if not resolve_local_import(project_root, path, module):
                        result.fail(f"unresolved local import in {path.relative_to(project_root)}: {module}")
    if not result.errors:
        result.checks.append("local import resolution")


def run_vertical_local_dry_run(result: ProjectResult) -> None:
    project_root = ROOT / "vertical_local"
    code = (
        "from debate_engine import run_debate; "
        "p=[{'id':'cfo','name':'CFO','bio':'costs','strategy':'measure'},"
        "{'id':'operator','name':'Operator','bio':'delivery','strategy':'test'}]; "
        "r=run_debate('offline verification', p, turns=1, sims=4, seed=7); "
        "assert len(r['turns']) == 1; assert r['simulations']['count'] == 4; "
        "assert set(r['scores']) == {'cfo','operator'}; print('vertical_local dry-run: ok')"
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(project_root),
    }
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode:
        result.fail(f"vertical_local dry-run failed: {completed.stderr.strip() or completed.stdout.strip()}")
    else:
        result.checks.append(completed.stdout.strip() or "vertical_local dry-run")


def run_vertical_local_route_check(result: ProjectResult) -> None:
    """Exercise FastAPI handlers directly; never start a server."""
    project_root = ROOT / "vertical_local"
    code = (
        "import app as module; "
        "paths={(route.path, tuple(sorted(getattr(route, 'methods', None) or []))) for route in module.app.routes if getattr(route, 'methods', None) is not None}; "
        "assert ('/', ('GET',)) in paths; "
        "assert ('/boardroom', ('GET',)) in paths; "
        "assert ('/generate', ('POST',)) in paths; "
        "assert module.health()['status'] == 'ok'; "
        "module.generate=lambda **kwargs: 'offline response'; "
        "request=module.GenRequest(provider='offline', model='test', prompt='ping'); "
        "assert module.gen(request)['text'] == 'offline response'; "
        "print('vertical_local routes: ok')"
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(project_root),
    }
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        if "ModuleNotFoundError" in detail and "fastapi" in detail:
            result.warnings.append("FastAPI route check skipped: fastapi is not installed")
        else:
            result.fail(f"vertical_local route check failed: {detail}")
    else:
        result.checks.append(completed.stdout.strip() or "vertical_local routes")


def verify_project(project: str) -> ProjectResult:
    result = ProjectResult(project=project, manifest=str(ROOT / project / "manifest.json"))
    manifest = load_manifest(project, result)
    if manifest is None:
        return result
    files = python_files(project, manifest, result)
    check_syntax_and_imports(project, files, result)

    verification = manifest.get("verification", {})
    if project == "vertical_local":
        if "debate_engine" not in verification.get("offline_imports", []):
            result.fail("vertical_local must declare debate_engine as an offline import")
        if "app" not in verification.get("offline_imports", []):
            result.fail("vertical_local must declare app as an offline import")
        run_vertical_local_dry_run(result)
        run_vertical_local_route_check(result)

    else:
        dry_run = str(verification.get("dry_run", ""))
        if "not_available" in dry_run:
            result.warnings.append("live-only entrypoint intentionally not executed")
        else:
            result.warnings.append("no executable offline dry-run declared")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", choices=DEFAULT_PROJECTS, action="append")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    projects = args.project or list(DEFAULT_PROJECTS)
    results = [verify_project(project) for project in projects]
    summary = Summary(all(item.passed for item in results), results)
    if args.as_json:
        print(json.dumps(asdict(summary), indent=2))
    else:
        for item in results:
            state = "PASS" if item.passed else "FAIL"
            print(f"[{state}] {item.project}")
            for check in item.checks:
                print(f"  check: {check}")
            for warning in item.warnings:
                print(f"  warn:  {warning}")
            for error in item.errors:
                print(f"  error: {error}")
        print(f"\nSummary: {'PASS' if summary.passed else 'FAIL'} ({len(results)} projects)")
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
