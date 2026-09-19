#!/usr/bin/env python3

# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: workspace-hygiene
# DEPS: datetime,json,os,sys,uuid
# ROLE: Schema Validation Test Script for Diff Theater & SAM-Loop Integration
# AUTHOR: Bleak
# SESSION: 2026-09-11
# TIER: 4
# [/DNA_TAG]

"""
Schema Validation Test Script for Diff Theater & SAM-Loop Integration

This script validates that:
1. The schema file parses cleanly as valid JSON
2. All required event types are defined
3. Example events validate against the schema
4. Basic validation logic works using only Python standard library

Usage:
    python scripts/test_schema_validation.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4


# Paths relative to repo root
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), '..', 'schemas', 'diff_theater_event.json')


def load_schema():
    """Load and parse the schema file."""
    try:
        with open(SCHEMA_PATH, 'r') as f:
            schema = json.load(f)
        print("[PASS] Schema file loaded successfully")
        return schema
    except FileNotFoundError:
        print(f"[FAIL] Schema file not found at {SCHEMA_PATH}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[FAIL] Schema file contains invalid JSON: {e}")
        sys.exit(1)


def validate_schema_structure(schema):
    """Validate that the schema has the expected structure."""
    errors = []
    
    # Check top-level structure
    if schema.get('type') != 'object':
        errors.append("Schema type should be 'object'")
    
    if schema.get('$schema') != 'http://json-schema.org/draft-07/schema#':
        errors.append("Schema should reference draft-07")
    
    # Check required fields
    required = schema.get('required', [])
    expected_required = ['event_type', 'task_id', 'bid_score', 'session_id', 'timestamp']
    for field in expected_required:
        if field not in required:
            errors.append(f"Missing required field in schema: {field}")
    
    # Check event_type enum
    event_type_prop = schema.get('properties', {}).get('event_type', {})
    event_enum = event_type_prop.get('enum', [])
    expected_events = ['heartbeat', 'scope_warning', 'checkpoint_created', 'diff_scene', 'rollback_receipt']
    for event in expected_events:
        if event not in event_enum:
            errors.append(f"Missing event type in enum: {event}")
    
    # Check definitions exist
    definitions = schema.get('definitions', {})
    expected_definitions = [
        'heartbeat_payload',
        'scope_warning_payload', 
        'checkpoint_payload',
        'diff_scene_payload',
        'rollback_receipt_payload',
        'file_change'
    ]
    for defn in expected_definitions:
        if defn not in definitions:
            errors.append(f"Missing definition: {defn}")
    
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        sys.exit(1)
    else:
        print("[PASS] Schema structure is valid")


def validate_diff_scene_payload_structure(schema):
    """Validate that diff_scene_payload has all required fields."""
    definitions = schema.get('definitions', {})
    diff_scene = definitions.get('diff_scene_payload', {})
    
    required = diff_scene.get('required', [])
    expected_required = ['affected_files', 'line_changes', 'risk_level', 'dependency_order', 'agent_narration']
    
    for field in expected_required:
        if field not in required:
            print(f"[FAIL] diff_scene_payload missing required field: {field}")
            sys.exit(1)
    
    # Check agent_narration structure
    agent_narration = diff_scene.get('properties', {}).get('agent_narration', {})
    narration_required = agent_narration.get('required', [])
    expected_narration = ['summary', 'intent']
    
    for field in expected_narration:
        if field not in narration_required:
            print(f"[FAIL] agent_narration missing required field: {field}")
            sys.exit(1)
    
    print("[PASS] diff_scene_payload structure is valid")


def validate_atomic_provenance(schema):
    """Validate that atomic provenance fields are properly defined."""
    properties = schema.get('properties', {})
    
    # Check task_id
    task_id = properties.get('task_id', {})
    if task_id.get('type') != 'string' or task_id.get('format') != 'uuid':
        print("[FAIL] task_id should be string with uuid format")
        sys.exit(1)
    
    # Check bid_score
    bid_score = properties.get('bid_score', {})
    if bid_score.get('type') != 'number':
        print("[FAIL] bid_score should be number type")
        sys.exit(1)
    if bid_score.get('minimum') != 0 or bid_score.get('maximum') != 1:
        print("[FAIL] bid_score should have range 0-1")
        sys.exit(1)
    
    # Check session_id
    session_id = properties.get('session_id', {})
    if session_id.get('type') != 'string' or session_id.get('format') != 'uuid':
        print("[FAIL] session_id should be string with uuid format")
        sys.exit(1)
    
    # Check timestamp
    timestamp = properties.get('timestamp', {})
    if timestamp.get('type') != 'string' or timestamp.get('format') != 'date-time':
        print("[FAIL] timestamp should be string with date-time format")
        sys.exit(1)
    
    print("[PASS] Atomic provenance fields are properly defined")


def create_test_events():
    """Create sample events for validation."""
    now = datetime.now(timezone.utc).isoformat()
    
    events = []
    
    # Heartbeat event
    heartbeat = {
        "event_type": "heartbeat",
        "task_id": str(uuid4()),
        "bid_score": 0.95,
        "session_id": str(uuid4()),
        "timestamp": now,
        "agent_id": "agent-001",
        "agent_name": "TestAgent",
        "payload": {
            "status": "healthy",
            "interval_seconds": 30,
            "memory_usage_mb": 256.5,
            "cpu_usage_percent": 45.2
        }
    }
    events.append(("heartbeat", heartbeat))
    
    # Scope warning event
    scope_warning = {
        "event_type": "scope_warning",
        "task_id": str(uuid4()),
        "bid_score": 0.8,
        "session_id": str(uuid4()),
        "timestamp": now,
        "payload": {
            "warning_type": "scope_creep",
            "message": "Task is expanding beyond original scope",
            "severity": "medium",
            "affected_resources": ["memory", "cpu"],
            "recommended_action": "Review task boundaries"
        }
    }
    events.append(("scope_warning", scope_warning))
    
    # Checkpoint event
    checkpoint = {
        "event_type": "checkpoint_created",
        "task_id": str(uuid4()),
        "bid_score": 0.9,
        "session_id": str(uuid4()),
        "timestamp": now,
        "payload": {
            "checkpoint_id": str(uuid4()),
            "state_hash": "a1b2c3d4e5f67890123456789012345678901234567890123456789012345678",
            "sequence_number": 1,
            "snapshot_size_bytes": 1024,
            "metadata": {}
        }
    }
    events.append(("checkpoint_created", checkpoint))
    
    # Diff scene event
    diff_scene = {
        "event_type": "diff_scene",
        "task_id": str(uuid4()),
        "bid_score": 0.85,
        "session_id": str(uuid4()),
        "timestamp": now,
        "agent_id": "agent-002",
        "agent_name": "DiffMaster",
        "payload": {
            "affected_files": [
                {
                    "file_path": "/test/file.py",
                    "change_type": "modified",
                    "lines_added": 10,
                    "lines_deleted": 2,
                    "language": "python",
                    "importance": "high"
                }
            ],
            "line_changes": {
                "added": 10,
                "deleted": 2,
                "modified": 0,
                "total_changes": 12
            },
            "risk_level": "medium",
            "dependency_order": ["dep1", "dep2"],
            "agent_narration": {
                "summary": "Modified test file",
                "intent": "Add new functionality",
                "detailed_explanation": "Added new features to the test file",
                "confidence": 0.9
            },
            "diff_hash": "a1b2c3d4e5f67890123456789012345678901234567890123456789012345678",
            "base_commit": "abc123",
            "target_commit": "def456"
        }
    }
    events.append(("diff_scene", diff_scene))
    
    # Rollback receipt event
    rollback = {
        "event_type": "rollback_receipt",
        "task_id": str(uuid4()),
        "bid_score": 0.7,
        "session_id": str(uuid4()),
        "timestamp": now,
        "payload": {
            "rollback_id": str(uuid4()),
            "original_checkpoint_id": str(uuid4()),
            "status": "completed",
            "reason": "Test rollback",
            "files_reverted": ["/test/file.py"],
            "rollback_duration_ms": 500,
            "error_message": ""
        }
    }
    events.append(("rollback_receipt", rollback))
    
    return events


def validate_event_against_schema(event, schema):
    """Validate a single event against the schema using raw dict validation."""
    errors = []
    
    # Check required fields
    required = schema.get('required', [])
    for field in required:
        if field not in event:
            errors.append(f"Missing required field: {field}")
    
    # Check event_type is valid
    event_type = event.get('event_type')
    event_type_prop = schema.get('properties', {}).get('event_type', {})
    valid_types = event_type_prop.get('enum', [])
    if event_type not in valid_types:
        errors.append(f"Invalid event_type: {event_type}")
    
    # Check field types
    properties = schema.get('properties', {})
    
    # task_id
    if 'task_id' in event:
        if not isinstance(event['task_id'], str):
            errors.append("task_id must be a string")
    
    # bid_score
    if 'bid_score' in event:
        if not isinstance(event['bid_score'], (int, float)):
            errors.append("bid_score must be a number")
        elif not (0 <= event['bid_score'] <= 1):
            errors.append("bid_score must be between 0 and 1")
    
    # session_id
    if 'session_id' in event:
        if not isinstance(event['session_id'], str):
            errors.append("session_id must be a string")
    
    # timestamp
    if 'timestamp' in event:
        if not isinstance(event['timestamp'], str):
            errors.append("timestamp must be a string")
    
    # Validate payload based on event type
    if 'payload' in event and event_type:
        payload = event['payload']
        definitions = schema.get('definitions', {})
        
        if event_type == 'heartbeat':
            payload_def = definitions.get('heartbeat_payload', {})
            required_payload = payload_def.get('required', [])
            for field in required_payload:
                if field not in payload:
                    errors.append(f"heartbeat payload missing required field: {field}")
        
        elif event_type == 'scope_warning':
            payload_def = definitions.get('scope_warning_payload', {})
            required_payload = payload_def.get('required', [])
            for field in required_payload:
                if field not in payload:
                    errors.append(f"scope_warning payload missing required field: {field}")
        
        elif event_type == 'checkpoint_created':
            payload_def = definitions.get('checkpoint_payload', {})
            required_payload = payload_def.get('required', [])
            for field in required_payload:
                if field not in payload:
                    errors.append(f"checkpoint_created payload missing required field: {field}")
        
        elif event_type == 'diff_scene':
            payload_def = definitions.get('diff_scene_payload', {})
            required_payload = payload_def.get('required', [])
            for field in required_payload:
                if field not in payload:
                    errors.append(f"diff_scene payload missing required field: {field}")
            
            # Validate agent_narration if present
            if 'agent_narration' in payload:
                narration = payload['agent_narration']
                narration_def = payload_def.get('properties', {}).get('agent_narration', {})
                narration_required = narration_def.get('required', [])
                for field in narration_required:
                    if field not in narration:
                        errors.append(f"agent_narration missing required field: {field}")
        
        elif event_type == 'rollback_receipt':
            payload_def = definitions.get('rollback_receipt_payload', {})
            required_payload = payload_def.get('required', [])
            for field in required_payload:
                if field not in payload:
                    errors.append(f"rollback_receipt payload missing required field: {field}")
    
    return errors


def run_validation_tests(schema):
    """Run validation tests on all event types."""
    events = create_test_events()
    all_passed = True
    
    for event_name, event in events:
        errors = validate_event_against_schema(event, schema)
        if errors:
            print(f"[FAIL] {event_name} validation failed:")
            for error in errors:
                print(f"  - {error}")
            all_passed = False
        else:
            print(f"[PASS] {event_name} event validated successfully")
    
    return all_passed


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Diff Theater & SAM-Loop Schema Validation Test")
    print("=" * 60)
    print()
    
    # Load schema
    schema = load_schema()
    
    # Validate schema structure
    validate_schema_structure(schema)
    
    # Validate diff_scene_payload structure
    validate_diff_scene_payload_structure(schema)
    
    # Validate atomic provenance
    validate_atomic_provenance(schema)
    
    # Run event validation tests
    print()
    print("Testing event validation:")
    print("-" * 40)
    all_passed = run_validation_tests(schema)
    
    print()
    print("=" * 60)
    if all_passed:
        print("[SUCCESS] All validation tests passed!")
        print("Schema is valid and all example events conform to it.")
    else:
        print("[FAILURE] Some validation tests failed!")
        sys.exit(1)
    print("=" * 60)


if __name__ == '__main__':
    main()
