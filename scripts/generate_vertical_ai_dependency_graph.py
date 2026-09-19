#!/usr/bin/env python3
"""Generate the offline Vertical AI dependency graph reports."""
from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ("vertical_ai", "vertical_local", "vertical_radar", "vertical_radar_dupe", "vertical_ai_engine")
OUT_JSON = ROOT / "docs" / "VERTICAL_AI_DEPENDENCY_GRAPH.json"
OUT_MD = ROOT / "docs" / "VERTICAL_AI_DEPENDENCY_GRAPH.md"


def scan(project: str) -> dict:
    base = ROOT / project
    imports: set[str] = set()
    python_files = sorted(base.rglob("*.py")) if base.is_dir() else []
    for path in python_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
    manifest_path = base / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    env = [item.get("name", "") for item in manifest.get("environment", []) if isinstance(item, dict)]
    entrypoints = [item.get("path", "") for item in manifest.get("entrypoints", []) if isinstance(item, dict)]
    return {
        "scripts": entrypoints,
        "python_files": len(python_files),
        "imports": sorted(imports),
        "outputs": manifest.get("outputs", []),
        "environment": env,
        "verification": manifest.get("verification", {}),
    }


def markdown(graph: dict) -> str:
    lines = ["# Vertical AI Dependency Graph", "", f"**Generated:** {graph['generated_at']}  ", "**Mode:** offline; values and credentials excluded.", "", "| Workspace | Python files | Scripts | Imports | Outputs | Environment |", "|---|---:|---|---|---|---|"]
    for name, item in graph["projects"].items():
        lines.append("| `{}` | {} | {} | {} | {} | {} |".format(name, item["python_files"], ", ".join(item["scripts"]) or "—", ", ".join(item["imports"]) or "—", "; ".join(item["outputs"]) or "—", ", ".join(item["environment"]) or "—"))
    lines += ["", "## Verification interpretation", "", "- `PASS`: static metadata/syntax checks completed.", "- `SKIP`: live network, provider, vault, SMTP, database, or server behavior intentionally not executed.", "- `BLOCKED`: a declared package or source module is absent.", "- Secret values are never collected by this generator.", ""]
    return "\n".join(lines)


def main() -> int:
    graph = {"schema_version": 1, "generated_at": str(date.today()), "mode": "offline", "secret_values_included": False, "projects": {name: scan(name) for name in PROJECTS}}
    OUT_JSON.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(markdown(graph), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
