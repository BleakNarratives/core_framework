#!/usr/bin/env python3
"""ariadne — the thread through the labyrinth.

WHY THIS EXISTS
---------------
Every introspection tool in this tree (codemap, fartographer, triage, the
boardroom) re-scans the whole filesystem from scratch on every single run. On
53 GB / ~48,000 Python files that takes minutes, and a plain `grep` across the
tree times out entirely. That is why every map anyone built here became
unusable: the tool choked before it could answer.

ariadne indexes the tree ONCE into SQLite and then answers instantly. It does
not try to fix your code, and it does not summarize your codebase for you. It
tells you where things are and what state they are in, so you can steer.

The name is the point: Ariadne gave Theseus the thread, not the sword.

CORE IDEA — ZONES
-----------------
The reason the tree feels unnavigable is that ~5,000 files of recovered intake
dumps, archive copies, and vendor trees are mixed in with the ~48 files you
actually work on. Every file is tagged with a zone, so you can exclude the
noise instead of being drowned by it:

  canon     your actual projects (the default)
  intake    NAT-Recovery-Kernel/intake  — recovered dumps
  recovery  recovery_staged, n_recovery, _archive, GRAVEYARD ...
  vendor    node_modules, venv, site-packages ...
  cache     __pycache__, *.pyc, .cache ...

USAGE
-----
  ariadne index              build/refresh the index (incremental by mtime)
  ariadne index --deep       also hash duplicates + index Python symbols
  ariadne zones              the map of the map: what is actually here
  ariadne find <pattern>     instant path search        (no more slow grep)
  ariadne where <symbol>     where is this defined
  ariadne what <path>        what is this thing, and is it a copy?
  ariadne dupes              duplicate files by content hash
  ariadne broken             files that do not compile, canon zone only
  ariadne tour               guided orientation for re-learning the tree

Everything is read-only. ariadne never modifies your source.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

VERSION = "1.0.0"
ROOT = Path(os.environ.get("ARIADNE_ROOT", Path.home())).resolve()
DATA_DIR = Path(os.environ.get("ARIADNE_HOME", Path.home() / ".local/share/ariadne"))
DB_PATH = DATA_DIR / "index.db"

SCHEMA_VERSION = 1

# --- zones ------------------------------------------------------------------
# First match wins. Order matters: specific before general.
_ZONE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("vendor", re.compile(
        r"(^|/)(node_modules|\.venv|venv|site-packages|\.bun|\.cargo|\.rustup"
        r"|\.npm|\.npm-global|\.dotnet|\.gem|go/pkg|dist-packages)(/|$)")),
    ("cache", re.compile(r"(^|/)(__pycache__|\.cache|\.ruff_cache|\.dspy_cache"
                         r"|\.pytest_cache|\.mypy_cache)(/|$)|\.pyc$|\.pyo$")),
    # Top-level dot-directories are tool/app state (.local, .config, .codex,
    # .codebuddy) or dotfiles. Not source. .agents is the one exception --
    # skills live there and are real work.
    ("canon", re.compile(r"^\.agents(/|$)")),
    ("app", re.compile(r"^\.[^/]+(/|$)")),
    ("intake", re.compile(r"^NAT-Recovery-Kernel/intake(/|$)")),
    ("recovery", re.compile(r"^(recovery_staged|recovery_staging|n_recovery|p_recovery"
                            r"|Anchor_from_zip|GRAVEYARD|UNPACKED|\._archive|\._incoming"
                            r"|Zip|downloads)(/|$)", re.I)),
)

_SKIP_DIRS = {".git"}

# Files worth remembering inside otherwise-noisy zones for `what` lookups.
_INDEX_EXTS = None  # None = index every file


def zone_of(rel: str) -> str:
    for name, rx in _ZONE_RULES:
        if rx.search(rel):
            return name
    return "canon"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _init_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS files (
            path  TEXT PRIMARY KEY,   -- relative to root
            name  TEXT,
            ext   TEXT,
            zone  TEXT,
            size  INTEGER,
            mtime REAL,
            digest TEXT,              -- sha256 prefix, only when hashed
            in_repo INTEGER DEFAULT 0 -- nested under a project with its own .git
        );
        CREATE INDEX IF NOT EXISTS ix_files_name  ON files(name);
        CREATE INDEX IF NOT EXISTS ix_files_zone  ON files(zone);
        CREATE INDEX IF NOT EXISTS ix_files_ext   ON files(ext);
        CREATE INDEX IF NOT EXISTS ix_files_size  ON files(size);
        CREATE INDEX IF NOT EXISTS ix_files_mtime ON files(mtime);
        CREATE TABLE IF NOT EXISTS defs (
            path TEXT, name TEXT, kind TEXT, line INTEGER
        );
        CREATE INDEX IF NOT EXISTS ix_defs_name ON defs(name);
        CREATE INDEX IF NOT EXISTS ix_defs_path ON defs(path);
        """
    )
    con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('schema',?)", (str(SCHEMA_VERSION),))
    con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('root',?)", (str(ROOT),))
    con.commit()


def _walk():
    """Yield (rel, size, mtime) for every file under ROOT, skipping .git."""
    stack = [ROOT]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name in _SKIP_DIRS:
                                continue
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            st = entry.stat(follow_symlinks=False)
                            yield str(Path(entry.path).relative_to(ROOT)), st.st_size, st.st_mtime
                    except OSError:
                        continue
        except (PermissionError, OSError):
            continue


def cmd_index(args) -> int:
    t0 = time.time()
    con = _connect()
    _init_schema(con)

    known = {r["path"]: (r["size"], r["mtime"]) for r in con.execute("SELECT path,size,mtime FROM files")}
    scanned = added = updated = unchanged = 0
    pending: list[tuple] = []

    for rel, size, mtime in _walk():
        scanned += 1
        prev = known.get(rel)
        if prev is None:
            added += 1
        elif prev == (size, mtime):
            unchanged += 1
            continue
        else:
            updated += 1
        pending.append((rel, Path(rel).name, Path(rel).suffix.lower(), zone_of(rel), size, mtime))

        if len(pending) >= 5000:
            _flush(con, pending)
            pending.clear()
            print(f"  ... {scanned:,} files scanned", file=sys.stderr)

    if pending:
        _flush(con, pending)

    removed = 0
    if not args.incremental:
        seen = {p[0] for p in pending}
        if added or updated or known:
            for path in list(known):
                if path not in seen:
                    con.execute("DELETE FROM files WHERE path=?", (path,))
                    removed += 1
        con.commit()

    elapsed = time.time() - t0
    total = con.execute("SELECT COUNT(*) c FROM files").fetchone()["c"]
    con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('last_index',?)",
                (f"{time.time()}",))
    con.commit()

    print(f"ariadne: indexed {scanned:,} files in {elapsed:.1f}s -> {DB_PATH}")
    print(f"  added={added:,}  updated={updated:,}  unchanged={unchanged:,}  removed={removed:,}")
    print(f"  index now holds {total:,} files")

    if args.deep:
        cmd_hash(con, args)
        cmd_symbols(con, args)
    con.close()
    return 0


def _flush(con: sqlite3.Connection, rows: list[tuple]) -> None:
    con.executemany(
        "INSERT INTO files(path,name,ext,zone,size,mtime) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(path) DO UPDATE SET name=excluded.name, ext=excluded.ext, "
        "zone=excluded.zone, size=excluded.size, mtime=excluded.mtime",
        rows,
    )
    con.commit()


def cmd_hash(con: sqlite3.Connection, args) -> None:
    """Hash only files that share a size with another file.

    Hashing 300k files would take longer than the walk. Grouping by size first
    means we only spend hashes on genuine duplicate candidates.
    """
    t0 = time.time()
    rows = con.execute(
        "SELECT size, COUNT(*) c FROM files WHERE size > ? GROUP BY size HAVING c > 1",
        (args.min_size,),
    ).fetchall()
    print(f"ariadne: {len(rows):,} size-groups are duplicate candidates", file=sys.stderr)
    hashed = 0
    for row in rows:
        size = row["size"]
        group = con.execute("SELECT path FROM files WHERE size=? AND size>?",
                            (size, args.min_size)).fetchall()
        buckets: dict[str, list[str]] = {}
        for g in group:
            full = ROOT / g["path"]
            try:
                h = hashlib.sha256()
                with open(full, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
                buckets.setdefault(h.hexdigest()[:32], []).append(g["path"])
                hashed += 1
            except OSError:
                continue
        for digest, paths in buckets.items():
            if len(paths) > 1:
                con.executemany("UPDATE files SET digest=? WHERE path=?", [(digest, p) for p in paths])
    con.commit()
    print(f"ariadne: hashed {hashed:,} candidate files in {time.time()-t0:.1f}s")


def cmd_symbols(con: sqlite3.Connection, args) -> None:
    """Index top-level and nested def/class names from canon-zone Python."""
    import ast
    import warnings
    warnings.filterwarnings("ignore", category=SyntaxWarning)
    t0 = time.time()
    con.execute("DELETE FROM defs")
    rows = con.execute(
        "SELECT path FROM files WHERE ext='.py' AND zone='canon' AND size < 400000"
    ).fetchall()
    count = 0
    for row in rows:
        try:
            src = (ROOT / row["path"]).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src)
        except (SyntaxError, ValueError, OSError, MemoryError):
            continue
        found = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.append((row["path"], node.name,
                              "class" if isinstance(node, ast.ClassDef) else "def",
                              node.lineno))
        if found:
            con.executemany("INSERT INTO defs(path,name,kind,line) VALUES(?,?,?,?)", found)
            count += len(found)
    con.commit()
    print(f"ariadne: indexed {count:,} symbols across {len(rows):,} canon files "
          f"in {time.time()-t0:.1f}s")


# --- queries ----------------------------------------------------------------
def cmd_zones(args) -> int:
    con = _connect()
    rows = con.execute(
        "SELECT zone, COUNT(*) files, SUM(size) bytes FROM files GROUP BY zone ORDER BY files DESC"
    ).fetchall()
    py = {r["zone"]: r["c"] for r in con.execute(
        "SELECT zone, COUNT(*) c FROM files WHERE ext='.py' GROUP BY zone")}

    print(f"{'zone':<10}{'files':>10}{'python':>10}{'size':>12}")
    print("-" * 44)
    for r in rows:
        print(f"{r['zone']:<10}{r['files']:>10,}{py.get(r['zone'],0):>10,}"
              f"{r['bytes']/1e9:>10.2f} GB")
    total = sum(r["files"] for r in rows)
    canon = next((r["files"] for r in rows if r["zone"] == "canon"), 0)
    print("-" * 44)
    print(f"{'TOTAL':<10}{total:>10,}")
    if total:
        print(f"\n{canon:,} of {total:,} files ({canon/total*100:.1f}%) are in the canon zone. "
              f"Everything else is intake, recovery, vendor, or cache —\n"
              f"reachable with --zone, but not your work.")
    con.close()
    return 0


def cmd_find(args) -> int:
    con = _connect()
    zones = args.zone or ["canon"]
    q = "SELECT path,zone,size,mtime FROM files WHERE name LIKE ?"
    params: list = [f"%{args.pattern}%"]
    if "all" not in zones:
        q += f" AND zone IN ({','.join('?' * len(zones))})"
        params += zones
    q += " ORDER BY mtime DESC LIMIT ?"
    params.append(args.limit)
    rows = con.execute(q, params).fetchall()
    if not rows:
        print(f"ariadne: no match for '{args.pattern}' in zones {zones}. "
              f"Try --zone all to include intake/recovery/vendor.")
        con.close()
        return 1
    for r in rows:
        age = _ago(r["mtime"])
        print(f"{r['size']:>10,}  {age:>12}  [{r['zone']:<8}] {r['path']}")
    print(f"\n{len(rows)} match(es).")
    con.close()
    return 0


def cmd_where(args) -> int:
    con = _connect()
    rows = con.execute(
        "SELECT path,kind,line FROM defs WHERE name=? ORDER BY path LIMIT ?",
        (args.symbol, args.limit),
    ).fetchall()
    if not rows:
        like = con.execute(
            "SELECT DISTINCT name FROM defs WHERE name LIKE ? LIMIT 15", (f"%{args.symbol}%",)
        ).fetchall()
        print(f"ariadne: no exact definition of '{args.symbol}'.")
        if like:
            print("close matches: " + ", ".join(r["name"] for r in like))
        else:
            print("The symbol index only covers the canon zone. Run: ariadne index --deep")
        con.close()
        return 1
    for r in rows:
        print(f"  {r['kind']:<6} {r['path']}:{r['line']}")
    print(f"\n{len(rows)} definition(s).")
    con.close()
    return 0


def cmd_what(args) -> int:
    con = _connect()
    target = args.path
    try:
        rel = str(Path(target).expanduser().resolve().relative_to(ROOT))
    except ValueError:
        rel = target.lstrip("./")

    row = con.execute("SELECT * FROM files WHERE path=?", (rel,)).fetchone()
    if row is None:
        rows = con.execute("SELECT * FROM files WHERE path LIKE ? ORDER BY mtime DESC LIMIT 1",
                           (f"%{rel}%",)).fetchone()
        row = rows
        if row is None:
            print(f"ariadne: '{rel}' is not in the index. Run: ariadne index")
            con.close()
            return 1
        rel = row["path"]

    print(f"path   : {rel}")
    print(f"zone   : {row['zone']}   <-- {'YOUR WORK' if row['zone'] == 'canon' else 'NOT canon (noise floor)'}")
    print(f"size   : {row['size']:,} bytes")
    print(f"touched: {_ago(row['mtime'])}")

    dupes = con.execute(
        "SELECT path FROM files WHERE digest IS NOT NULL AND digest=(SELECT digest FROM files WHERE path=?) "
        "AND path<>?", (rel, rel)).fetchall()
    if dupes:
        print(f"\nDUPLICATE: {len(dupes)} byte-identical copy/copies exist:")
        for d in dupes[:10]:
            print(f"  {d['path']}")

    parent = str(Path(rel).parent)
    if parent != ".":
        sibs = con.execute("SELECT COUNT(*) c FROM files WHERE path LIKE ?",
                           (f"{parent}/%",)).fetchone()["c"]
        print(f"\nsiblings in {parent}/: {sibs}")

    for readme in ("README.md", "readme.md", "README (1).md"):
        rp = Path(parent) / readme
        cand = con.execute("SELECT path FROM files WHERE path=?", (str(rp),)).fetchone()
        if cand:
            print(f"\n--- {rp} (first 15 lines) ---")
            try:
                for i, line in enumerate((ROOT / rp).read_text(errors="replace").splitlines()):
                    if i >= 15:
                        break
                    print("  " + line)
            except OSError:
                pass
            break
    con.close()
    return 0


def cmd_dupes(args) -> int:
    con = _connect()
    rows = con.execute(
        "SELECT digest, zone, COUNT(*) c, SUM(size) bytes FROM files "
        "WHERE digest IS NOT NULL AND size>=? GROUP BY digest ORDER BY bytes DESC LIMIT ?",
        (args.min_size, args.limit),
    ).fetchall()
    if not rows:
        print("ariadne: no hashes yet. Run: ariadne index --deep")
        con.close()
        return 1
    total_waste = 0
    for r in rows:
        paths = con.execute("SELECT path,zone FROM files WHERE digest=? ORDER BY zone", (r["digest"],)).fetchall()
        waste = r["bytes"] - (r["bytes"] // r["c"])
        total_waste += waste
        print(f"\n{r['c']} copies, {r['size'] if 'size' in r.keys() else r['bytes']//r['c']:,} bytes each "
              f"— ~{waste/1e6:.1f} MB reclaimable")
        for p in paths[:8]:
            print(f"    [{p['zone']:<8}] {p['path']}")
        if len(paths) > 8:
            print(f"    ... +{len(paths)-8} more")
    print(f"\nTop {len(rows)} duplicate groups hold ~{total_waste/1e9:.2f} GB of redundancy.")
    con.close()
    return 0


def cmd_broken(args) -> int:
    """Files that do not parse. Canon by default — this is the number that matters.

    The old triage reported 2,101 broken files because it counted intake dumps
    and 28 copies of the same server.py. This counts each canon file once.
    """
    import ast
    import warnings
    warnings.filterwarnings("ignore", category=SyntaxWarning)
    con = _connect()
    zones = args.zone or ["canon"]
    q = "SELECT path,size FROM files WHERE ext='.py' AND size < 400000"
    params: list = []
    if "all" not in zones:
        q += f" AND zone IN ({','.join('?' * len(zones))})"
        params += zones
    rows = con.execute(q, params).fetchall()

    broken = []
    for r in rows:
        try:
            ast.parse((ROOT / r["path"]).read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            broken.append((r["path"], e.lineno or 0, (e.msg or "syntax error")[:70]))
        except (ValueError, OSError, MemoryError):
            continue

    print(f"scanned {len(rows):,} .py files in zones {zones}")
    print(f"broken : {len(broken):,}  ({len(broken)/max(len(rows),1)*100:.1f}%)\n")
    for path, line, msg in broken[:args.limit]:
        print(f"  {path}:{line}\n      {msg}")
    if len(broken) > args.limit:
        print(f"  ... +{len(broken)-args.limit} more")
    con.close()
    return 0


def cmd_tour(args) -> int:
    """Guided orientation. Buckets by project so the tree stops being a wall."""
    con = _connect()
    print("=" * 68)
    print("  ARIADNE TOUR — where you actually are")
    print("=" * 68)

    z = con.execute("SELECT zone, COUNT(*) c FROM files GROUP BY zone ORDER BY c DESC").fetchall()
    print("\n1. SIGNAL VS NOISE")
    for r in z:
        print(f"   {r['zone']:<10} {r['c']:>9,} files")

    print("\n2. YOUR PROJECTS (canon zone, top 15 by file count)")
    rows = con.execute(
        "SELECT path FROM files WHERE zone='canon'").fetchall()
    proj: dict[str, int] = {}
    for r in rows:
        top = r["path"].split("/")[0]
        proj[top] = proj.get(top, 0) + 1
    for name, count in sorted(proj.items(), key=lambda kv: -kv[1])[:15]:
        print(f"   {count:>6,}  {name}")

    print("\n3. MOST RECENTLY TOUCHED (canon, last 12)")
    for r in con.execute(
        "SELECT path,mtime FROM files WHERE zone='canon' ORDER BY mtime DESC LIMIT 12"
    ):
        print(f"   {_ago(r['mtime']):>14}  {r['path']}")

    print("\n4. BIGGEST FILES (canon, last 8)")
    for r in con.execute(
        "SELECT path,size FROM files WHERE zone='canon' ORDER BY size DESC LIMIT 8"
    ):
        print(f"   {r['size']/1e6:>8.1f} MB  {r['path']}")

    print("\n5. NEXT")
    print("   ariadne zones           the counts above, in detail")
    print("   ariadne find <name>     locate anything, fast")
    print("   ariadne where <symbol>  find a definition")
    print("   ariadne broken          what actually fails to parse, canon only")
    print("   ariadne dupes           redundant copies")
    con.close()
    return 0


def _ago(ts: float) -> str:
    d = time.time() - ts
    if d < 3600:
        return f"{int(d/60)}m ago"
    if d < 86400:
        return f"{int(d/3600)}h ago"
    return f"{int(d/86400)}d ago"


# --- cli --------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ariadne",
                                description="Persistent codebase index + fast queries. Read-only.")
    p.add_argument("--version", action="version", version=f"ariadne {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    i = sub.add_parser("index", help="build or refresh the index")
    i.add_argument("--deep", action="store_true", help="also hash duplicates and index symbols")
    i.add_argument("--incremental", action="store_true", help="do not remove vanished files")
    i.add_argument("--min-size", type=int, default=4096, help="min bytes for duplicate hashing")
    i.set_defaults(func=cmd_index)

    z = sub.add_parser("zones", help="signal vs noise: file counts by zone")
    z.set_defaults(func=cmd_zones)

    f = sub.add_parser("find", help="instant path search")
    f.add_argument("pattern")
    f.add_argument("--zone", action="append", help="canon|intake|recovery|vendor|cache|all")
    f.add_argument("--limit", type=int, default=40)
    f.set_defaults(func=cmd_find)

    w = sub.add_parser("where", help="find a definition by symbol name")
    w.add_argument("symbol")
    w.add_argument("--limit", type=int, default=20)
    w.set_defaults(func=cmd_where)

    wh = sub.add_parser("what", help="explain a file: zone, age, duplicates, readme")
    wh.add_argument("path")
    wh.set_defaults(func=cmd_what)

    d = sub.add_parser("dupes", help="duplicate files by content hash")
    d.add_argument("--min-size", type=int, default=4096)
    d.add_argument("--limit", type=int, default=15)
    d.set_defaults(func=cmd_dupes)

    b = sub.add_parser("broken", help="files that do not parse (canon by default)")
    b.add_argument("--zone", action="append")
    b.add_argument("--limit", type=int, default=40)
    b.set_defaults(func=cmd_broken)

    t = sub.add_parser("tour", help="guided orientation")
    t.set_defaults(func=cmd_tour)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "index" and not DB_PATH.exists():
        print(f"ariadne: no index yet at {DB_PATH}\n  run: ariadne index --deep", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
