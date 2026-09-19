"""Blue Sky Meeting local-first room engine and CLI."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters import AdapterRequest, default_registry


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_id(value: str) -> str:
    value = value.strip()
    if not _ID_RE.fullmatch(value):
        raise ValueError("IDs may contain only letters, numbers, '.', '_' and '-'")
    return value


class RoomStore:
    def __init__(self, state_dir: str | Path = ".blue-sky") -> None:
        self.root = Path(state_dir).expanduser()
        self.rooms = self.root / "rooms"
        self.rooms.mkdir(parents=True, exist_ok=True)

    def path(self, room_id: str) -> Path:
        return self.rooms / f"{safe_id(room_id)}.json"

    def load(self, room_id: str) -> dict[str, Any]:
        path = self.path(room_id)
        if not path.is_file():
            raise FileNotFoundError(f"room not found: {room_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, room: dict[str, Any]) -> Path:
        path = self.path(room["room_id"])
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(room, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return path

    def create(self, room_id: str, label: str) -> dict[str, Any]:
        room_id = safe_id(room_id)
        path = self.path(room_id)
        if path.exists():
            raise FileExistsError(f"room already exists: {room_id}")
        room = {
            "schema_version": 1,
            "room_id": room_id,
            "label": label,
            "created_at": now(),
            "updated_at": now(),
            "brief": "",
            "agents": [],
            "events": [],
            "artifacts": [],
        }
        append_event(room, "system", "room.created", {"label": label})
        self.save(room)
        return room


def append_event(room: dict[str, Any], actor: str, action: str, data: dict[str, Any]) -> None:
    room["events"].append({"timestamp": now(), "actor": actor, "action": action, "data": data})
    room["updated_at"] = now()


def find_agent(room: dict[str, Any], agent_id: str) -> dict[str, Any]:
    for agent in room["agents"]:
        if agent["agent_id"] == agent_id:
            return agent
    raise ValueError(f"agent not found: {agent_id}")


def add_agent(room: dict[str, Any], agent_id: str, role: str, adapter: str) -> None:
    safe_id(agent_id)
    if any(item["agent_id"] == agent_id for item in room["agents"]):
        raise ValueError(f"agent already exists: {agent_id}")
    room["agents"].append({"agent_id": agent_id, "role": role, "adapter": adapter, "enabled": True})
    append_event(room, agent_id, "agent.added", {"role": role, "adapter": adapter})


def set_brief(room: dict[str, Any], brief: str) -> None:
    brief = brief.strip()
    if not brief:
        raise ValueError("brief cannot be empty")
    room["brief"] = brief
    append_event(room, "human", "brief.set", {"characters": len(brief)})


def run_rounds(room: dict[str, Any], rounds: int) -> list[dict[str, Any]]:
    if not room["brief"]:
        raise ValueError("set a brief before running a room")
    if not room["agents"]:
        raise ValueError("add at least one agent before running a room")
    if rounds < 1 or rounds > 20:
        raise ValueError("rounds must be between 1 and 20")
    outputs = []
    registry = default_registry()
    for number in range(1, rounds + 1):
        contributions = []
        for agent in room["agents"]:
            if not agent.get("enabled", True):
                continue
            adapter = registry.get(agent["adapter"])
            response = adapter.contribute(
                AdapterRequest(
                    room_id=room["room_id"],
                    brief=room["brief"],
                    role=agent["role"],
                    round_number=number,
                    prior_contributions=tuple(item["text"] for item in contributions),
                )
            )
            contribution = {
                "agent_id": agent["agent_id"],
                "role": agent["role"],
                "adapter": response.adapter,
                "text": response.text,
                "provenance": response.provenance,
                "requires_approval": response.requires_approval,
            }
            contributions.append(contribution)
        round_data = {"round": number, "brief": room["brief"], "contributions": contributions}
        outputs.append(round_data)
        append_event(room, "builtin", "round.completed", round_data)
    artifact = {
        "artifact_id": f"roadmap-round-{len(room['artifacts']) + 1}",
        "kind": "meeting-notes",
        "title": f"{room['label']} meeting notes",
        "requires_human_approval": True,
        "content": outputs,
    }
    room["artifacts"].append(artifact)
    append_event(room, "builtin", "artifact.created", {"artifact_id": artifact["artifact_id"], "kind": artifact["kind"]})
    return outputs


def export_markdown(room: dict[str, Any]) -> str:
    lines = [f"# {room['label']}", "", f"Room ID: `{room['room_id']}`", "", "## Brief", "", room["brief"] or "_(not set)_", "", "## Participants", ""]
    for agent in room["agents"]:
        lines.append(f"- **{agent['agent_id']}** — {agent['role']} (`{agent['adapter']}`)")
    lines += ["", "## Artifacts", ""]
    for artifact in room["artifacts"]:
        lines += [f"### {artifact['title']}", "", f"Approval required: `{artifact['requires_human_approval']}`", ""]
        for round_data in artifact["content"]:
            lines.append(f"#### Round {round_data['round']}")
            for contribution in round_data["contributions"]:
                lines.append(f"- **{contribution['agent_id']}**: {contribution['text']}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Blue Sky Meeting local room console")
    p.add_argument("--state-dir", default=".blue-sky")
    sub = p.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-room")
    create.add_argument("room_id")
    create.add_argument("--label", required=True)
    agent = sub.add_parser("add-agent")
    agent.add_argument("room_id")
    agent.add_argument("agent_id")
    agent.add_argument("--role", required=True)
    agent.add_argument("--adapter", default="builtin")
    brief = sub.add_parser("set-brief")
    brief.add_argument("room_id")
    source = brief.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--file")
    run = sub.add_parser("run")
    run.add_argument("room_id")
    run.add_argument("--rounds", type=int, default=1)
    export = sub.add_parser("export")
    export.add_argument("room_id")
    export.add_argument("--format", choices=("json", "markdown"), default="markdown")
    export.add_argument("--out", required=True)
    sub.add_parser("list-rooms")
    sub.add_parser("list-adapters")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    store = RoomStore(args.state_dir)
    if args.command == "create-room":
        room = store.create(args.room_id, args.label)
        print(f"created {room['room_id']}")
    elif args.command == "add-agent":
        room = store.load(args.room_id)
        add_agent(room, args.agent_id, args.role, args.adapter)
        store.save(room)
        print(f"added {args.agent_id}")
    elif args.command == "set-brief":
        room = store.load(args.room_id)
        brief = args.text if args.text is not None else Path(args.file).read_text(encoding="utf-8")
        set_brief(room, brief)
        store.save(room)
        print(f"brief set for {args.room_id}")
    elif args.command == "run":
        room = store.load(args.room_id)
        rounds = run_rounds(room, args.rounds)
        store.save(room)
        print(f"completed {len(rounds)} round(s) in {args.room_id}")
    elif args.command == "export":
        room = store.load(args.room_id)
        output = Path(args.out).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        content = export_markdown(room) if args.format == "markdown" else json.dumps(room, indent=2) + "\n"
        output.write_text(content, encoding="utf-8")
        print(f"exported {output}")
    elif args.command == "list-rooms":
        for path in sorted(store.rooms.glob("*.json")):
            print(path.stem)
    elif args.command == "list-adapters":
        for name in default_registry().names():
            print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
