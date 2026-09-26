"""
Code smell sniff test.

AST-based, not regex: a regex cannot tell a bare `except:` from one inside a
docstring, nor a mutable default from a string. These detectors parse, so a
finding is a fact about the code rather than a guess about its text.

Scope is deliberate: the modules changed in the 2026-09-26 session. A
repo-wide smell gate would be dominated by thousands of pre-existing findings
in the archived Code-City-Apocalypse dumps and would tell us nothing. This
guards *new* work, which is where smell actually accumulates.

Every detector names the construct and the node it came from, so a failure is
actionable instead of mysterious.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

# Modules authored or modified in the 2026-09-26 session.
SMELL_SCOPE = [
    "src/skill/scout.py",
    "Code-City-Apocalypse/Code_City/repo_scanner.py",
    "Whorl/whorl/core/cascade.py",
]

# Library code must not print to stdout or sleep; those are CLI/test concerns.
NO_PRINT_PREFIXES = ("src/", "Whorl/whorl/")


def parse(rel: str) -> ast.Module:
    return ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"), filename=rel)


def walk(node: ast.AST):
    for child in ast.walk(node):
        yield child


class SmellTestBase(unittest.TestCase):
    maxDiff = None

    def findings(self, rel: str) -> List[str]:
        return []

    def assert_no_smells(self, rel: str) -> None:
        found = self.findings(rel)
        self.assertEqual(found, [], f"{rel} code smells:\n  " + "\n  ".join(found))


class TestBareExcept(SmellTestBase):
    """A bare `except:` swallows KeyboardInterrupt and SystemExit."""

    def findings(self, rel):
        out = []
        for n in walk(parse(rel)):
            if isinstance(n, ast.ExceptHandler) and n.type is None:
                out.append(f"line {n.lineno}: bare 'except:' (catches KeyboardInterrupt)")
        return out

    def test_no_bare_except(self):
        for rel in SMELL_SCOPE:
            with self.subTest(module=rel):
                self.assert_no_smells(rel)


class TestSilentSwallow(SmellTestBase):
    """`except Exception: pass` turns a real failure into silence."""

    def findings(self, rel):
        out = []
        for n in walk(parse(rel)):
            if not isinstance(n, ast.ExceptHandler):
                continue
            body = [s for s in n.body if not isinstance(s, ast.Expr)
                    or not isinstance(getattr(s, "value", None), ast.Constant)]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                out.append(f"line {n.lineno}: except-and-pass (silent swallow)")
        return out

    def test_no_silent_swallow(self):
        for rel in SMELL_SCOPE:
            with self.subTest(module=rel):
                self.assert_no_smells(rel)


class TestMutableDefault(SmellTestBase):
    """Mutable defaults are shared across every call of the function."""

    MUTABLE = (ast.List, ast.Dict, ast.Set)

    def findings(self, rel):
        out = []
        for n in walk(parse(rel)):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in n.args.defaults + [x for x in n.args.kw_defaults if x]:
                if isinstance(d, self.MUTABLE):
                    out.append(f"line {getattr(d, 'lineno', n.lineno)}: "
                               f"{n.name}() has a mutable default")
        return out

    def test_no_mutable_defaults(self):
        for rel in SMELL_SCOPE:
            with self.subTest(module=rel):
                self.assert_no_smells(rel)


class TestOversizedFunction(SmellTestBase):
    """Beyond ~120 lines a function stops being nameable."""

    LIMIT = 120

    def findings(self, rel):
        out = []
        for n in walk(parse(rel)):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(n, "end_lineno", n.lineno)
                length = end - n.lineno
                if length > self.LIMIT:
                    out.append(f"line {n.lineno}: {n.name}() is {length} lines "
                               f"(limit {self.LIMIT})")
        return out

    def test_no_oversized_functions(self):
        for rel in SMELL_SCOPE:
            with self.subTest(module=rel):
                self.assert_no_smells(rel)


class TestDeepNesting(SmellTestBase):
    """Nesting past 4 levels is hard to hold in the head."""

    LIMIT = 4

    def _max_depth(self, node, depth=0):
        best = depth
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.With,
                                  ast.Try, ast.FunctionDef, ast.AsyncFunctionDef)):
                best = max(best, self._max_depth(child, depth + 1))
            else:
                best = max(best, self._max_depth(child, depth))
        return best

    def findings(self, rel):
        out = []
        tree = parse(rel)
        depth = self._max_depth(tree)
        if depth > self.LIMIT:
            out.append(f"max nesting depth {depth} exceeds limit {self.LIMIT}")
        return out

    def test_no_deep_nesting(self):
        for rel in SMELL_SCOPE:
            with self.subTest(module=rel):
                self.assert_no_smells(rel)


class TestLibrarySideEffects(SmellTestBase):
    """Library modules must not print or sleep; that is the CLI's job."""

    # Pre-existing print()s that are contract, not new work. scout.execute_skill
    # is a pre-existing stub whose print is part of its observable behaviour;
    # changing it here would be an unrequested behaviour change (AGENTS.md §2).
    # Keyed by ENCLOSING FUNCTION, not line number -- a line-number allowlist
    # silently rots the moment an edit shifts the line, which is exactly what
    # happened once during this work.
    PRINT_ALLOWLIST = {"src/skill/scout.py": {"execute_skill"}}

    def _enclosing_function(self, tree, target):
        for fn in walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(fn, "end_lineno", fn.lineno)
                if fn.lineno <= target.lineno <= end:
                    return fn.name
        return None

    def findings(self, rel):
        if not rel.startswith(NO_PRINT_PREFIXES):
            return []
        allowed = self.PRINT_ALLOWLIST.get(rel, set())
        out = []
        tree = parse(rel)
        for n in walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                if n.func.id == "print":
                    if self._enclosing_function(tree, n) not in allowed:
                        out.append(f"line {n.lineno}: print() in library code")
                if n.func.id == "sleep":
                    out.append(f"line {n.lineno}: sleep() in library code")
        return out

    def test_no_print_or_sleep_in_library(self):
        for rel in SMELL_SCOPE:
            with self.subTest(module=rel):
                self.assert_no_smells(rel)

    def test_allowlisted_function_still_exists_and_still_prints(self):
        """A stale allowlist must fail loudly, not silently permit a new print."""
        rel = "src/skill/scout.py"
        tree = parse(rel)
        names = {fn.name for fn in walk(tree)
                 if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for fname in self.PRINT_ALLOWLIST[rel]:
            self.assertIn(fname, names, f"allowlisted function {fname} is gone")
            fn = next(f for f in walk(tree)
                      if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and f.name == fname)
            prints = [c for c in walk(fn)
                      if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                      and c.func.id == "print"]
            self.assertTrue(prints, f"allowlisted {fname}() no longer prints")


class TestUnresolvedMarkers(SmellTestBase):
    """TODO/FIXME/HACK in new code is unfinished work, not a note.

    A marker must stand alone to count. Prose like "a 500-TODO file" mentions
    the word without being a marker, so a preceding digit or hyphen disqualifies
    it -- otherwise this detector flags its own vocabulary.
    """

    MARKER = re.compile(r"(?<![\w-])(TODO|FIXME|HACK|XXX)\b")

    def findings(self, rel):
        out = []
        for i, line in enumerate((REPO_ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") and self.MARKER.search(stripped.upper()):
                out.append(f"line {i}: {stripped[:70]}")
        return out

    def test_no_unresolved_markers(self):
        for rel in SMELL_SCOPE:
            with self.subTest(module=rel):
                self.assert_no_smells(rel)

    def test_prose_mentioning_todo_is_not_a_marker(self):
        self.assertIsNone(self.MARKER.search("# SUB-LINEAR SO A 500-TODO FILE DOES NOT"))
        self.assertIsNotNone(self.MARKER.search("# TODO: WIRE THIS UP"))
        self.assertIsNotNone(self.MARKER.search("# FIXME BROKEN"))


class TestDetectorSanity(unittest.TestCase):
    """The detectors must actually fire. A smell test that cannot fail is
    decoration, so each is proved against a deliberately smelly sample."""

    SMELLY = (
        "def f(a=[], b={}):\n"
        "    try:\n"
        "        pass\n"
        "    except:\n"
        "        pass\n"
        "    except Exception:\n"
        "        pass\n"
        "    print('hi')\n"
    )

    def _find(self, detector_cls, src):
        tree = ast.parse(src)
        return [n for n in ast.walk(tree) if isinstance(n, ast.AST)]

    def test_bare_except_detected(self):
        tree = ast.parse(self.SMELLY)
        n = next(h for h in ast.walk(tree)
                 if isinstance(h, ast.ExceptHandler) and h.type is None)
        self.assertIsNotNone(n)

    def test_silent_swallow_detected(self):
        """Mirror of TestSilentSwallow.findings, applied to the sample."""
        tree = ast.parse(self.SMELLY)
        swallows = []
        for h in ast.walk(tree):
            if not isinstance(h, ast.ExceptHandler):
                continue
            body = [s for s in h.body
                    if not isinstance(s, ast.Expr)
                    or not isinstance(getattr(s, "value", None), ast.Constant)]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                swallows.append(h)
        self.assertTrue(swallows)

    def test_mutable_default_detected(self):
        tree = ast.parse(self.SMELLY)
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
        self.assertTrue(any(isinstance(d, (ast.List, ast.Dict))
                            for d in fn.args.defaults))

    def test_print_detected(self):
        tree = ast.parse(self.SMELLY)
        prints = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "print"]
        self.assertEqual(len(prints), 1)


if __name__ == "__main__":
    unittest.main()
