# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: introspection
# DEPS: ast,html,json,os,re
# ROLE: one-shot codebase familiarity — import graph + force-directed HTML
# AUTHOR: Bleak
# SESSION: 2026-09-08
# TIER: 2
# [/DNA_TAG]

#!/usr/bin/env python3
"""
codemap.py — one-shot codebase familiarity tool.

Walks a directory tree of .py files, builds an import graph (who imports
whom), flags likely orphans/stubs, and writes a single self-contained
HTML file with a force-directed graph you can click through.

No deps beyond stdlib. Read-only — never writes into your project tree.

Usage:
    python3 codemap.py /path/to/project [--out report.html] [--min-lines 5]

Example for RootBase on the Chromebook:
    python3 codemap.py ~/RootBase --out ~/codemap_rootbase.html
"""

import argparse
import ast
import html
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "venv", ".venv", "env",
    "_ARCHIVED", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".idea", ".vscode",
}

STUB_MARKERS = re.compile(
    r"\b(TODO|FIXME|NotImplementedError|pass\s*#\s*stub|raise NotImplementedError)\b"
)


def find_py_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(".py"):
                yield Path(dirpath) / fn


def module_name(path: Path, root: Path):
    rel = path.relative_to(root).with_suffix("")
    parts = rel.parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else path.stem


def analyze_file(path: Path):
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return None, [], 0, False, f"unreadable: {e}"

    n_lines = src.count("\n") + 1
    is_stub = bool(STUB_MARKERS.search(src)) or n_lines < 5

    imports = []
    try:
        tree = ast.parse(src, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
    except SyntaxError as e:
        return None, [], n_lines, is_stub, f"syntax error: {e}"

    return src, imports, n_lines, is_stub, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="project directory to scan")
    ap.add_argument("--out", default="codemap_report.html")
    ap.add_argument("--min-lines", type=int, default=0,
                     help="hide files below this line count from the graph (still counted in summary)")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    files = sorted(find_py_files(root))
    if not files:
        print(f"No .py files found under {root}", file=sys.stderr)
        sys.exit(1)

    mod_to_path = {}
    for p in files:
        mod_to_path[module_name(p, root)] = p

    nodes = []
    edges = []
    errors = []
    local_mods = set(mod_to_path.keys())

    for p in files:
        mod = module_name(p, root)
        src, imports, n_lines, is_stub, err = analyze_file(p)
        if err:
            errors.append((str(p.relative_to(root)), err))
        local_imports = sorted(set(i for i in imports if i in local_mods and i != mod))
        nodes.append({
            "id": mod,
            "path": str(p.relative_to(root)),
            "lines": n_lines,
            "is_stub": is_stub,
            "n_local_imports": len(local_imports),
        })
        for imp in local_imports:
            edges.append({"source": mod, "target": imp})

    indeg = {n["id"]: 0 for n in nodes}
    outdeg = {n["id"]: 0 for n in nodes}
    for e in edges:
        outdeg[e["source"]] = outdeg.get(e["source"], 0) + 1
        indeg[e["target"]] = indeg.get(e["target"], 0) + 1

    orphans = [n for n in nodes if indeg.get(n["id"], 0) == 0 and outdeg.get(n["id"], 0) == 0]
    stubs = [n for n in nodes if n["is_stub"]]
    hubs = sorted(nodes, key=lambda n: indeg.get(n["id"], 0), reverse=True)[:15]

    graph_nodes = [n for n in nodes if n["lines"] >= args.min_lines]
    graph_ids = {n["id"] for n in graph_nodes}
    graph_edges = [e for e in edges if e["source"] in graph_ids and e["target"] in graph_ids]

    for n in graph_nodes:
        n["indeg"] = indeg.get(n["id"], 0)
        n["outdeg"] = outdeg.get(n["id"], 0)
        n["orphan"] = n["indeg"] == 0 and n["outdeg"] == 0

    data = {
        "root": str(root),
        "generated_summary": {
            "total_files": len(nodes),
            "total_edges": len(edges),
            "orphans": len(orphans),
            "stubs": len(stubs),
            "errors": len(errors),
        },
        "nodes": graph_nodes,
        "edges": graph_edges,
        "orphans": [{"id": n["id"], "path": n["path"], "lines": n["lines"]} for n in orphans][:200],
        "stubs": [{"id": n["id"], "path": n["path"], "lines": n["lines"]} for n in stubs][:200],
        "hubs": [{"id": n["id"], "path": n["path"], "indeg": indeg.get(n["id"], 0)} for n in hubs],
        "errors": errors[:100],
    }

    html_out = TEMPLATE.replace("__DATA__", json.dumps(data))
    out_path = Path(args.out).expanduser().resolve()
    out_path.write_text(html_out, encoding="utf-8")

    print(f"Scanned {len(nodes)} files, {len(edges)} local import edges.")
    print(f"Orphans (no in/out local imports): {len(orphans)}")
    print(f"Likely stubs (TODO/NotImplementedError/<5 lines): {len(stubs)}")
    if errors:
        print(f"Files with syntax errors: {len(errors)}")
    print(f"Report written to: {out_path}")


TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Codebase Map</title>
<style>
  body { margin:0; font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#0d1117; color:#c9d1d9; }
  #header { padding: 14px 20px; border-bottom: 1px solid #21262d; }
  #header h1 { margin:0; font-size: 16px; color:#e6edf3; }
  #header .path { font-size: 12px; color:#8b949e; margin-top:4px; word-break: break-all; }
  #stats { display:flex; gap:18px; padding: 10px 20px; flex-wrap:wrap; font-size:13px; }
  .stat { background:#161b22; border:1px solid #21262d; border-radius:6px; padding:8px 14px; }
  .stat b { color:#e6edf3; font-size:16px; display:block; }
  #main { display:flex; height: calc(100vh - 110px); }
  #graph { flex: 1 1 auto; position:relative; }
  #side { width: 340px; border-left:1px solid #21262d; overflow-y:auto; padding: 10px; font-size:12px; }
  #side h3 { color:#e6edf3; font-size:13px; margin: 14px 0 6px; }
  #side ul { list-style:none; margin:0; padding:0; }
  #side li { padding:4px 6px; border-radius:4px; cursor:default; }
  #side li:hover { background:#161b22; }
  .tag { display:inline-block; font-size:10px; padding:1px 6px; border-radius:10px; margin-left:6px; }
  .tag.orphan { background:#3d1e1e; color:#ff7b72; }
  .tag.stub { background:#3d321e; color:#f0b429; }
  svg { width:100%; height:100%; }
  .node circle { stroke: #0d1117; stroke-width:1.5px; cursor:pointer; }
  .node text { font-size:9px; fill:#c9d1d9; pointer-events:none; }
  .link { stroke:#30363d; stroke-width:1px; }
  #tooltip { position:absolute; background:#161b22; border:1px solid #30363d; padding:8px 10px; border-radius:6px; font-size:12px; pointer-events:none; display:none; max-width:280px; }
  #tooltip b { color:#e6edf3; }
</style>
</head>
<body>
<div id="header">
  <h1>Codebase Map</h1>
  <div class="path" id="rootpath"></div>
</div>
<div id="stats"></div>
<div id="main">
  <div id="graph"><svg></svg><div id="tooltip"></div></div>
  <div id="side">
    <h3>Hubs (most depended-on)</h3>
    <ul id="hublist"></ul>
    <h3>Orphans (no local links)</h3>
    <ul id="orphanlist"></ul>
    <h3>Likely stubs</h3>
    <ul id="stublist"></ul>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script>
const data = __DATA__;

document.getElementById('rootpath').textContent = data.root;

const stats = data.generated_summary;
const statBox = document.getElementById('stats');
const statDefs = [
  ['Files', stats.total_files],
  ['Local import edges', stats.total_edges],
  ['Orphans', stats.orphans],
  ['Likely stubs', stats.stubs],
  ['Parse errors', stats.errors],
];
statDefs.forEach(([label, val]) => {
  const d = document.createElement('div');
  d.className = 'stat';
  d.innerHTML = `<b>${val}</b>${label}`;
  statBox.appendChild(d);
});

function fillList(id, items, render) {
  const ul = document.getElementById(id);
  if (!items.length) { ul.innerHTML = '<li style="color:#6e7681">none</li>'; return; }
  items.forEach(it => {
    const li = document.createElement('li');
    li.innerHTML = render(it);
    ul.appendChild(li);
  });
}
fillList('hublist', data.hubs, h => `${h.id} <span style="color:#6e7681">(${h.indeg} in)</span>`);
fillList('orphanlist', data.orphans, o => `${o.id} <span style="color:#6e7681">${o.lines}L</span>`);
fillList('stublist', data.stubs, s => `${s.id} <span style="color:#6e7681">${s.lines}L</span>`);

const svg = d3.select('svg');
const width = document.getElementById('graph').clientWidth;
const height = document.getElementById('graph').clientHeight;
const g = svg.append('g');
svg.call(d3.zoom().scaleExtent([0.1, 4]).on('zoom', (e) => g.attr('transform', e.transform)));

const nodes = data.nodes.map(n => ({...n}));
const links = data.edges.map(e => ({...e}));

const sim = d3.forceSimulation(nodes)
  .force('link', d3.forceLink(links).id(d => d.id).distance(70).strength(0.3))
  .force('charge', d3.forceManyBody().strength(-140))
  .force('center', d3.forceCenter(width/2, height/2))
  .force('collide', d3.forceCollide(14));

const link = g.append('g').selectAll('line')
  .data(links).join('line').attr('class', 'link');

const node = g.append('g').selectAll('g')
  .data(nodes).join('g').attr('class', 'node')
  .call(d3.drag()
    .on('start', (e,d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
    .on('drag', (e,d) => { d.fx=e.x; d.fy=e.y; })
    .on('end', (e,d) => { if (!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }));

function radius(d) { return Math.min(4 + Math.sqrt(d.lines||1), 18); }
function color(d) {
  if (d.orphan) return '#ff7b72';
  if (d.is_stub) return '#f0b429';
  if (d.indeg > 5) return '#58a6ff';
  return '#3fb950';
}

node.append('circle')
  .attr('r', radius)
  .attr('fill', color);

node.append('text')
  .attr('dx', d => radius(d) + 3)
  .attr('dy', 3)
  .text(d => d.id.length > 22 ? d.id.slice(0,20)+'…' : d.id);

const tooltip = document.getElementById('tooltip');
node.on('mouseover', (e,d) => {
  tooltip.style.display = 'block';
  tooltip.innerHTML = `<b>${d.id}</b><br>${d.path}<br>${d.lines} lines · in:${d.indeg} out:${d.outdeg}` +
    (d.orphan ? '<br><span style="color:#ff7b72">orphan</span>' : '') +
    (d.is_stub ? '<br><span style="color:#f0b429">looks like a stub</span>' : '');
}).on('mousemove', (e) => {
  tooltip.style.left = (e.pageX + 12) + 'px';
  tooltip.style.top = (e.pageY + 12) + 'px';
}).on('mouseout', () => tooltip.style.display = 'none');

sim.on('tick', () => {
  link.attr('x1', d=>d.source.x).attr('y1', d=>d.source.y)
      .attr('x2', d=>d.target.x).attr('y2', d=>d.target.y);
  node.attr('transform', d => `translate(${d.x},${d.y})`);
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
