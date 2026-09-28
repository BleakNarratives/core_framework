#!/usr/bin/env python3
"""Runtime routing for explicitly recorded Bufftag code-movement routes.

This module can resolve an old Python import name to its canonical module and
run an old script address against the current file. It never guesses a route,
edits source, changes sys.path, or hides the fact that a redirect occurred.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import re
import runpy
import sys
import traceback
import warnings
from contextlib import AbstractContextManager
from pathlib import Path
from types import ModuleType, TracebackType
from typing import Any, Callable, Mapping, Sequence

try:
    from Bufftag import atlas
except ModuleNotFoundError:  # Allows `python Bufftag/route_run.py`.
    import atlas


RedirectHandler = Callable[[str, atlas.Route, str], None]


class BufftagRedirectWarning(RuntimeWarning):
    pass


def default_redirect_handler(old: str, route: atlas.Route, kind: str) -> None:
    warnings.warn(
        f"Bufftag {kind} redirect: {old} -> {route.new_path or route.new_module} "
        f"({route.reason}; route {route.record_id})",
        BufftagRedirectWarning,
        stacklevel=3,
    )


class _AliasLoader:
    def __init__(self, module: ModuleType):
        self.module = module

    def create_module(self, spec):  # noqa: D401 - importlib protocol
        return self.module

    def exec_module(self, module: ModuleType) -> None:
        return None


class AtlasImportFinder:
    """Resolve only exact old module names present in a verified atlas."""

    def __init__(
        self,
        routes: Mapping[str, atlas.Route],
        workspace: str | Path,
        on_redirect: RedirectHandler = default_redirect_handler,
    ):
        self.routes = dict(routes)
        self.workspace = Path(workspace).resolve()
        self.on_redirect = on_redirect

    def find_spec(self, fullname: str, path=None, target=None):
        route = self.routes.get(fullname)
        if route is None:
            return None
        new_path = (self.workspace / route.new_path).resolve()
        try:
            new_path.relative_to(self.workspace)
        except ValueError as exc:
            raise ModuleNotFoundError(
                f"Bufftag route {route.record_id} escapes workspace", name=fullname
            ) from exc
        if new_path.is_symlink() or not new_path.is_file():
            raise ModuleNotFoundError(
                f"Bufftag route {route.record_id} points to missing target {route.new_path}",
                name=fullname,
            )
        self.on_redirect(fullname, route, "import")
        if route.new_module and route.new_module != fullname:
            try:
                canonical = importlib.import_module(route.new_module)
            except Exception as exc:
                raise ModuleNotFoundError(
                    f"Bufftag route {fullname} -> {route.new_module} failed: {exc}",
                    name=fullname,
                ) from exc
            return importlib.util.spec_from_loader(fullname, _AliasLoader(canonical))
        search_locations = [str(new_path.parent)] if new_path.name == "__init__.py" else None
        return importlib.util.spec_from_file_location(
            fullname,
            new_path,
            submodule_search_locations=search_locations,
        )


def _relative_frame_path(filename: str, workspace: Path) -> str | None:
    try:
        path = Path(filename).resolve()
        return path.relative_to(workspace.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def annotate_traceback_text(
    text: str, workspace: str | Path, by_path: Mapping[str, atlas.Route]
) -> str:
    """Rewrite displayed File addresses while preserving traceback line numbers.

    This is diagnostic only: it does not alter the traceback object, exception,
    source, or stack. The original path remains before the arrow for auditability.
    """
    root = Path(workspace).resolve()
    pattern = re.compile(r'^(?P<indent>\s*)File "(?P<path>[^"]+)"', re.MULTILINE)

    def replace(match: re.Match[str]) -> str:
        relative = _relative_frame_path(match.group("path"), root)
        route = by_path.get(relative) if relative else None
        if route is None:
            return match.group(0)
        return f'{match.group("indent")}File "{match.group("path")}" → "{route.new_path}"'

    return pattern.sub(replace, text)


def _annotated_excepthook(
    previous_hook,
    workspace: Path,
    by_path: Mapping[str, atlas.Route],
):
    def hook(exc_type, exc_value, exc_traceback):
        if previous_hook is sys.__excepthook__:
            text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            sys.stderr.write(annotate_traceback_text(text, workspace, by_path))
        else:
            previous_hook(exc_type, exc_value, exc_traceback)
            frames = traceback.extract_tb(exc_traceback)
            routes = {
                route.old_path: route
                for frame in frames
                if (relative := _relative_frame_path(frame.filename, workspace)) in by_path
            }
            if routes:
                sys.stderr.write(annotate_traceback_text("".join(traceback.format_exception_only(exc_type, exc_value)), workspace, routes))

    return hook


class RoutingSession(AbstractContextManager["RoutingSession"]):
    """Install import and top-level traceback routing for a bounded scope."""

    def __init__(
        self,
        *,
        atlas_path: str | Path,
        workspace: str | Path,
        secret: bytes | None = None,
        anchor_path: str | Path | None = None,
        on_redirect: RedirectHandler = default_redirect_handler,
    ):
        self.workspace = Path(workspace).resolve()
        if anchor_path is not None:
            records, findings = atlas._read_records(
                Path(atlas_path), secret, allow_unsigned_existing=True
            )
            if findings:
                raise atlas.AtlasError("movement atlas failed integrity verification")
            atlas.assert_anchor_current(
                atlas_path=atlas_path, anchor_path=anchor_path, secret=secret
            )
        self.by_path, by_module = atlas.active_routes(
            atlas_path,
            secret,
            allow_unsigned_existing=anchor_path is not None,
        )
        self.finder = AtlasImportFinder(by_module, self.workspace, on_redirect)
        self.previous_excepthook = sys.excepthook

    def __enter__(self) -> "RoutingSession":
        if self.finder not in sys.meta_path:
            sys.meta_path.insert(0, self.finder)
        sys.excepthook = _annotated_excepthook(
            self.previous_excepthook, self.workspace, self.by_path
        )
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> bool:
        sys.excepthook = self.previous_excepthook
        if self.finder in sys.meta_path:
            sys.meta_path.remove(self.finder)
        return False


def route_run(
    *,
    atlas_path: str | Path,
    workspace: str | Path,
    old_script: str,
    arguments: Sequence[str],
    secret: bytes | None = None,
    anchor_path: str | Path | None = None,
    on_redirect: RedirectHandler = default_redirect_handler,
) -> Any:
    root = Path(workspace).resolve()
    if anchor_path is not None:
        records, findings = atlas._read_records(
            Path(atlas_path), secret, allow_unsigned_existing=True
        )
        if findings:
            raise atlas.AtlasError("movement atlas failed integrity verification")
        atlas.assert_anchor_current(
            atlas_path=atlas_path, anchor_path=anchor_path, secret=secret
        )
    by_path, _ = atlas.active_routes(
        atlas_path,
        secret,
        allow_unsigned_existing=anchor_path is not None,
    )
    route = atlas.resolve_path(old_script, root, by_path)
    if route is None:
        raise FileNotFoundError(f"no explicit Bufftag route for old script: {old_script}")
    target = atlas._safe_workspace_path(root, route.new_path, require_file=True)
    on_redirect(route.old_path, route, "script")
    previous_argv = sys.argv
    sys.argv = [str(target), *arguments]
    try:
        with RoutingSession(
            atlas_path=atlas_path,
            workspace=root,
            secret=secret,
            on_redirect=on_redirect,
        ):
            try:
                return runpy.run_path(str(target), run_name="__main__")
            except Exception:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                sys.excepthook(exc_type, exc_value, exc_traceback)
                raise
    finally:
        sys.argv = previous_argv


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace")
    parser.add_argument("old_script", help="old path, FKA, or AKA recorded in the atlas")
    parser.add_argument("script_args", nargs=argparse.REMAINDER)
    parser.add_argument("--atlas")
    parser.add_argument("--anchor", help="require a separately controlled signed movement head")
    parser.add_argument("--signing-key-env", default="BUFFTAG_KEY")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    workspace = Path(args.workspace).resolve()
    atlas_path = (workspace / (args.atlas or atlas.DEFAULT_ATLAS)).resolve()
    configured_anchor = Path(args.anchor).expanduser() if args.anchor else None
    anchor_path = None
    if configured_anchor is not None:
        anchor_path = configured_anchor if configured_anchor.is_absolute() else (workspace / configured_anchor)
    try:
        from Bufftag import bufftag
    except ModuleNotFoundError:
        import bufftag
    try:
        secret = bufftag._secret_from_env(args.signing_key_env)
        # Verify the complete chain before installing any runtime redirect.
        records, findings = atlas._read_records(atlas_path, secret)
        if findings:
            raise atlas.AtlasError("movement atlas failed integrity verification")
        route_run(
            atlas_path=atlas_path,
            workspace=workspace,
            old_script=args.old_script,
            arguments=args.script_args,
            secret=secret,
            anchor_path=anchor_path,
        )
        return 0
    except (atlas.AtlasError, bufftag.BufftagError, FileNotFoundError) as exc:
        print(f"bufftag route-run: {exc}", file=sys.stderr)
        return 2
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
