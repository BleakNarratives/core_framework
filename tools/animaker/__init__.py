"""Pure, offline Diff Theater animation proposal tooling."""

from .cli import main

from .compiler import (
    COMPILER_VERSION,
    ProposalError,
    SCHEMA,
    SCHEMA_HASH,
    compile_animation,
    normalize_event,
    render_css,
    render_tailwind,
    to_json,
)

__all__ = [
    "COMPILER_VERSION",
    "ProposalError",
    "SCHEMA",
    "SCHEMA_HASH",
    "compile_animation",
    "normalize_event",
    "render_css",
    "render_tailwind",
    "to_json",
    "main",
]
