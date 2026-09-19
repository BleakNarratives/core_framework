"""Participant adapter contracts for Blue Sky Meeting.

Only ``builtin`` is enabled in v0.1. External adapters must be explicitly
implemented and registered later; room data never executes adapter names.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AdapterRequest:
    room_id: str
    brief: str
    role: str
    round_number: int
    prior_contributions: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdapterResponse:
    adapter: str
    text: str
    provenance: dict[str, Any]
    requires_approval: bool = True


class ParticipantAdapter(Protocol):
    name: str

    def contribute(self, request: AdapterRequest) -> AdapterResponse:
        """Return a reviewable contribution without mutating the room."""


class BuiltinAdapter:
    name = "builtin"

    def contribute(self, request: AdapterRequest) -> AdapterResponse:
        text = (
            f"{request.role} proposal for round {request.round_number}: "
            f"focus on a testable next step for {request.brief}"
        )
        return AdapterResponse(
            adapter=self.name,
            text=text,
            provenance={"mode": "deterministic", "external_execution": False},
        )


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ParticipantAdapter] = {}

    def register(self, adapter: ParticipantAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> ParticipantAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise ValueError(f"adapter is not enabled: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._adapters)


def default_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(BuiltinAdapter())
    return registry
