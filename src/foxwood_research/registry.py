"""Provenance admission gate for the Foxwood pipe.

`PROVENANCE.md` is this repository's classification registry: OWNED, FORK,
FOREIGN, UNKNOWN. Admission reads that registry instead of keeping a second list
of foreign projects, because two copies of "what is foreign" drift apart. This
repository has already paid for that lesson once, on a different question --
herald's docstring records that two copies of "what counts as contact" is how the
headline count drifted.

The parser is reused from `scripts/check_provenance.py` by path rather than
reimplemented. That module owns the registry format; a second parser here would be
the same drift in a different costume. It is loaded by path because `scripts/` is a
directory of entry points, not an importable package -- the same reason
`tools/lookingglass` loads its collaborators by path.

Fails closed. A registry that cannot be read is not an empty registry; it is a
missing gate, and the caller is refused rather than admitted.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional

from .ledger import ForeignContentError

REGISTRY_FILENAME = "PROVENANCE.md"
CHECKER_RELPATH = Path("scripts") / "check_provenance.py"

# Mirrors scripts/check_provenance.BLOCKED_CLASSIFICATIONS. OWNED and FORK are
# admissible: FORK needs attribution, not exclusion, per PROVENANCE.md's rules.
BLOCKED_CLASSIFICATIONS = frozenset({"FOREIGN", "UNKNOWN"})

_PARSER_MODULE_NAME = "foxwood_provenance_checker"


class RegistryUnavailable(RuntimeError):
    """The classification registry could not be read, so admission fails closed."""


def find_repo_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk up from `start` until a PROVENANCE.md appears, or None.

    Not a fixed parent count. This project has already been relocated once, and a
    fixed depth fails silently into "no registry found" instead of saying which
    directory was searched.
    """
    here = Path(start or __file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / REGISTRY_FILENAME).is_file():
            return candidate
    return None


def _load_parser(repo_root: Path) -> Callable[[Path], Mapping[str, Mapping[str, str]]]:
    """Load `parse_provenance` out of scripts/check_provenance.py."""
    path = repo_root / CHECKER_RELPATH
    if not path.is_file():
        raise RegistryUnavailable(f"provenance checker not found at {path}")
    spec = importlib.util.spec_from_file_location(_PARSER_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise RegistryUnavailable(f"provenance checker could not be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # a broken checker must not read as a clean registry
        raise RegistryUnavailable(f"provenance checker raised on import: {exc}") from exc
    parser = getattr(module, "parse_provenance", None)
    if not callable(parser):
        raise RegistryUnavailable(f"{path} has no callable parse_provenance()")
    return parser


def _tokens(value: str) -> set:
    """Path and URL segments that a registry key could be hiding in.

    Bare segment matching, consistent with both existing implementations in this
    repository: `scripts/check_provenance.check_path` and
    `ResearchLedger._assert_not_foreign`.

    That deliberately over-blocks on short keys such as `More/`, and the direction
    is the point: a false positive costs one source, a false negative ships
    unclassified material into a deliverable.
    """
    text = str(value or "").replace("\\", "/").strip()
    if not text:
        return set()
    if "://" in text:
        text = text.split("://", 1)[1]
    return {part for part in (segment.strip() for segment in text.split("/")) if part}


class RegistryGate:
    """Admission decisions read from PROVENANCE.md rather than from a second list.

    Usage:
        gate = RegistryGate()                      # discovers the repository root
        gate.admit("ScholarScout/src/x.py")        # raises ForeignContentError
        gate.admit("adapter:openalex", "https://api.openalex.org/works?x=1")

    `registry_path` and `parse` are injectable so a test can exercise admission
    against a temporary registry without staging a whole repository.
    """

    def __init__(
        self,
        registry_path: Optional[str | Path] = None,
        *,
        repo_root: Optional[str | Path] = None,
        parse: Optional[Callable[[Path], Mapping[str, Mapping[str, str]]]] = None,
    ) -> None:
        if registry_path is None:
            root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
            if root is None:
                raise RegistryUnavailable(
                    f"no {REGISTRY_FILENAME} found above {Path(__file__).resolve()}")
            registry_path = root / REGISTRY_FILENAME
        self.registry_path = Path(registry_path).resolve()
        parser = parse or _load_parser(self.registry_path.parent)
        try:
            entries = dict(parser(self.registry_path) or {})
        except RegistryUnavailable:
            raise
        except Exception as exc:
            raise RegistryUnavailable(
                f"{self.registry_path.name} could not be parsed: {exc}") from exc
        if not entries:
            # An empty registry means the format changed or the file was truncated.
            # Either way there is nothing to check against, so nothing is admitted.
            raise RegistryUnavailable(
                f"{self.registry_path} parsed to zero entries; refusing to admit anything")

        self.entries: Dict[str, Mapping[str, str]] = entries
        self.blocked: Dict[str, Mapping[str, str]] = {
            path: info for path, info in entries.items()
            if str((info or {}).get("classification", "")).upper() in BLOCKED_CLASSIFICATIONS
        }
        self._blocked_tokens = {
            token: (path, info)
            for path, info in self.blocked.items()
            for token in _tokens(path)
        }

    def blocked_reason(self, origin: str = "", url: str = "") -> str:
        """Why this origin/URL is not admissible, or "" when it is clean."""
        for token in _tokens(origin) | _tokens(url):
            hit = self._blocked_tokens.get(token)
            if hit:
                path, info = hit
                classification = str(info.get("classification", "UNKNOWN")).upper()
                return f"{path} is {classification} in {self.registry_path.name}"
        return ""

    def admit(self, origin: str = "", url: str = "") -> None:
        """Raise ForeignContentError when the registry blocks this origin or URL."""
        reason = self.blocked_reason(origin, url)
        if reason:
            raise ForeignContentError(f"registry rejects source: {reason}")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"RegistryGate({str(self.registry_path)!r}, "
                f"entries={len(self.entries)}, blocked={len(self.blocked)})")
