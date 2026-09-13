# MVP Data Contract: Diff Theater & SAM-Loop Integration

## Overview

This document defines the data contract for the Minimum Viable Product (MVP) integration between **Diff Theater** (visual diff analyzer) and **SAM-Loop** (Self-Adaptive Multi-Agent Loop). The contract specifies the exact JSON schema for session events, ensuring interoperability and atomic provenance tracking across the system.

## Core Principles

1. **Atomic Provenance**: Every event MUST include `task_id`, `bid_score`, `session_id`, and `timestamp` fields.
2. **Event Typing**: Five event types are supported: `heartbeat`, `scope_warning`, `checkpoint_created`, `diff_scene`, `rollback_receipt`.
3. **Payload Specialization**: Each event type has a dedicated payload structure.
4. **Validation**: All events must validate against the schema defined in `schemas/diff_theater_event.json`.

---

## Event Types

### 1. Heartbeat Event

**Purpose**: Regular health status updates from agents.

**Required Fields**:
- `event_type`: `"heartbeat"`
- `task_id`: UUID of the current task
- `bid_score`: Agent's confidence score (0.0-1.0)
- `session_id`: UUID of the current session
- `timestamp`: ISO 8601 datetime
- `payload`: Heartbeat-specific data

**Payload Structure**:
```json
{
  "status": "healthy" | "degraded" | "critical",
  "interval_seconds": <integer>,
  "memory_usage_mb": <number>,
  "cpu_usage_percent": <number>
}
```

### 2. Scope Warning Event

**Purpose**: Alerts about potential scope issues or resource constraints.

**Required Fields**: Same atomic provenance fields as above.

**Payload Structure**:
```json
{
  "warning_type": "scope_creep" | "resource_exhaustion" | "timeout_imminent" | "conflict_detected",
  "message": "<string>",
  "severity": "low" | "medium" | "high" | "critical",
  "affected_resources": ["<string>", ...],
  "recommended_action": "<string>"
}
```

### 3. Checkpoint Created Event

**Purpose**: Marks the creation of a state checkpoint for potential rollback.

**Required Fields**: Same atomic provenance fields as above.

**Payload Structure**:
```json
{
  "checkpoint_id": "<uuid>",
  "state_hash": "<sha256>",
  "sequence_number": <integer>,
  "snapshot_size_bytes": <integer>,
  "metadata": { ... }
}
```

### 4. Diff Scene Event

**Purpose**: Provides the detailed diff information needed by Diff Theater visualizer.

**Required Fields**: Same atomic provenance fields as above.

**Payload Structure**:
```json
{
  "affected_files": [
    {
      "file_path": "<string>",
      "change_type": "added" | "deleted" | "modified" | "renamed",
      "lines_added": <integer>,
      "lines_deleted": <integer>,
      "language": "<string>",
      "importance": "low" | "medium" | "high" | "critical"
    }, ...
  ],
  "line_changes": {
    "added": <integer>,
    "deleted": <integer>,
    "modified": <integer>,
    "total_changes": <integer>
  },
  "risk_level": "low" | "medium" | "high" | "critical",
  "dependency_order": ["<string>", ...],
  "agent_narration": {
    "summary": "<string>",
    "intent": "<string>",
    "detailed_explanation": "<string>",
    "confidence": <number>
  },
  "diff_hash": "<sha256>",
  "base_commit": "<string>",
  "target_commit": "<string>"
}
```

#### Diff Scene Payload Details

- **affected_files**: Array of file objects, each describing the path, change type, and metrics for a single file.
- **line_changes**: Aggregate statistics for all line-level changes across all files.
- **risk_level**: Assessed risk of this diff (low, medium, high, critical).
- **dependency_order**: Ordered list of dependency identifiers that must be processed before this diff.
- **agent_narration**: The agent's explanation of the diff, including:
  - `summary`: Brief description of changes
  - `intent`: The agent's purpose behind the changes
  - `detailed_explanation`: Long-form rationale
  - `confidence`: Agent's confidence in the changes (0.0-1.0)

### 5. Rollback Receipt Event

**Purpose**: Confirms the execution of a rollback operation.

**Required Fields**: Same atomic provenance fields as above.

**Payload Structure**:
```json
{
  "rollback_id": "<uuid>",
  "original_checkpoint_id": "<uuid>",
  "status": "initiated" | "in_progress" | "completed" | "failed",
  "reason": "<string>",
  "files_reverted": ["<string>", ...],
  "rollback_duration_ms": <integer>,
  "error_message": "<string>"
}
```

---

## Atomic Provenance Fields

Every event MUST include these four fields to ensure traceability:

| Field | Type | Format | Description |
|-------|------|--------|-------------|
| `task_id` | string | UUID | Unique identifier for the associated task |
| `bid_score` | number | 0.0-1.0 | Agent's confidence score for the task bid |
| `session_id` | string | UUID | Unique identifier for the current session |
| `timestamp` | string | ISO 8601 | When the event was generated |

Optional provenance fields:
- `agent_id`: Identifier for the agent generating the event
- `agent_name`: Human-readable name of the agent

---

## Schema Validation

The canonical schema is defined in `schemas/diff_theater_event.json`. This schema:

1. Enforces all required fields
2. Validates enum values for event types and statuses
3. Ensures proper data types and formats
4. Prevents additional properties (strict mode)

### Validation Example (Python)

```python
import json
from jsonschema import validate, ValidationError

# Load schema
with open('schemas/diff_theater_event.json', 'r') as f:
    schema = json.load(f)

# Validate an event
def validate_event(event):
    try:
        validate(instance=event, schema=schema)
        return True, None
    except ValidationError as e:
        return False, str(e)
```

---

## Example Events

### Heartbeat Example

```json
{
  "event_type": "heartbeat",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "bid_score": 0.95,
  "session_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "timestamp": "2026-09-03T14:30:00.000Z",
  "agent_id": "agent-001",
  "agent_name": "CodeAnalyst",
  "payload": {
    "status": "healthy",
    "interval_seconds": 30,
    "memory_usage_mb": 256.5,
    "cpu_usage_percent": 45.2
  }
}
```

### Diff Scene Example

```json
{
  "event_type": "diff_scene",
  "task_id": "550e8400-e29b-41d4-a716-446655440001",
  "bid_score": 0.88,
  "session_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "timestamp": "2026-09-03T14:35:00.000Z",
  "agent_id": "agent-002",
  "agent_name": "DiffMaster",
  "payload": {
    "affected_files": [
      {
        "file_path": "/home/user/project/src/main.py",
        "change_type": "modified",
        "lines_added": 15,
        "lines_deleted": 5,
        "language": "python",
        "importance": "high"
      },
      {
        "file_path": "/home/user/project/src/utils.py",
        "change_type": "modified",
        "lines_added": 8,
        "lines_deleted": 2,
        "language": "python",
        "importance": "medium"
      }
    ],
    "line_changes": {
      "added": 23,
      "deleted": 7,
      "modified": 0,
      "total_changes": 30
    },
    "risk_level": "medium",
    "dependency_order": ["config-loader", "logger-init"],
    "agent_narration": {
      "summary": "Added new feature X with supporting utilities",
      "intent": "Implement feature X as specified in requirements",
      "detailed_explanation": "Added the core implementation in main.py and supporting helper functions in utils.py. The changes follow the existing code style and include proper error handling.",
      "confidence": 0.92
    },
    "diff_hash": "a1b2c3d4e5f6...",
    "base_commit": "abc123def456",
    "target_commit": "def456ghi789"
  }
}
```

---

## Data Flow

```
SAM-Loop Agent → Event Generation → Schema Validation → Diff Theater → Visualization
                              ↓
                       (Optional: Persistence Layer)
```

1. **Generation**: SAM-Loop agents generate events during task execution
2. **Validation**: Events are validated against the schema before processing
3. **Consumption**: Diff Theater consumes validated events for visualization
4. **Persistence**: Optionally, events can be stored for audit/analysis

---

## Versioning

- **Schema Version**: 1.0.0 (MVP)
- **Last Updated**: 2026-09-03
- **Compatibility**: Backward-compatible changes only within MVP lifecycle

---

## Testing

A validation script is provided at `scripts/test_schema_validation.py` to verify schema parsing and basic validation logic using only Python standard library modules.

---

## References

- Schema File: `schemas/diff_theater_event.json`
- Test Script: `scripts/test_schema_validation.py`
- JSON Schema Draft: http://json-schema.org/draft-07/schema#
