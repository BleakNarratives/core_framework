# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: agents
# FKA: ~/kilo_bridge.py
# ROLE: kilo_bridge.py — see canonical at ~/projects/agents/bridges/kilo_bridge.py
# SESSION: 2026-09-08
# TIER: 3
# [/DNA_TAG]

#!/usr/bin/env python3
"""
Kilo Bridge - Event Handling Loop for Integration with thoth_orchestrator.agent_bus

This module implements a comprehensive event handling system that connects directly
to the thoth_orchestrator.agent_bus to process and coordinate events across
the agentic ecosystem.

Key Features:
- Continuous event polling from agent_bus
- Event filtering and routing based on tags and project targets
- Automatic forwarding of state events to stdout
- Response event emission for acknowledgment
- Comprehensive logging with timestamps and execution status
- Non-blocking operations with proper error handling
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

# Add thoth_orchestrator to path
sys.path.insert(0, str(Path.home() / "thoth_orchestrator"))

from thoth_orchestrator.agent_bus import emit_event, read_events

# Configure logging
LOG_DIR = Path.home() / ".config" / "kilo" / "bridge_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "kilo_bridge.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("kilo_bridge")
@dataclass
class EventFilter:
    """Event filtering configuration"""
    include_tags: List[str] = field(default_factory=lambda: ['security_gate'])
    exclude_tags: List[str] = field(default_factory=list)
    project_targets: List[str] = field(default_factory=lambda: ['payment_system', 'nostr_dvm'])
    min_timestamp: Optional[datetime] = None
    max_timestamp: Optional[datetime] = None
    exclude_processed: bool = True
    max_events_per_batch: int = 100
@dataclass
class ProcessingStats:
    """Statistics tracking for event processing"""
    events_processed: int = 0
    events_forwarded: int = 0
    events_filtered: int = 0
    events_failed: int = 0
    last_processed: Optional[datetime] = None
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
@dataclass
class EventLogEntry:
    """Structured log entry for events"""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = ""
    source_agent: str = ""
    event_type: str = ""
    project: str = ""
    tags: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    processed: bool = False
    processing_duration_ms: Optional[float] = None
    status: str = "pending"
    error_message: Optional[str] = None
class KiloBridge:
    """
    Kilo Bridge - Event handling and coordination system for agentic ecosystem.
    
    This class provides a comprehensive event handling loop that connects to
    thoth_orchestrator.agent_bus, filters and processes events, logs all operations,
    and emits acknowledgments for processed events.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize Kilo Bridge with configuration"""
        self.config = self._load_config(config_path)
        self.event_filter = EventFilter(
            include_tags=self.config.get('event_filter', {}).get('include_tags', ['security_gate']),
            exclude_tags=self.config.get('event_filter', {}).get('exclude_tags', []),
            project_targets=self.config.get('event_filter', {}).get('project_targets', ['payment_system']),
        )
        self.processing_stats = ProcessingStats()
        self.event_log_file = LOG_DIR / "event_processing.log"
        self.state_file = LOG_DIR / "bridge_state.json"
        
        # Load previous state if exists
        self._load_state()
        
        # Setup logging
        self.setup_logging()
        
        logger.info("Kilo Bridge initialized successfully")
    
    def _load_config(self, config_path: Optional[Path]) -> Dict[str, Any]:
        """Load configuration from file or defaults"""
        default_config = {
            "event_filter": {
                "include_tags": ['security_gate'],
                "exclude_tags": [],
                "project_targets": ['payment_system', 'nostr_dvm'],
            },
            "processing": {
                "polling_interval_seconds": 1,
                "batch_size": 50,
                "timeout_seconds": 30,
                "retry_attempts": 3,
            },
            "logging": {
                "level": "INFO",
                "file_rotation": True,
                "max_file_size_mb": 100,
            },
            "forwarding": {
                "stdout_enabled": True,
                "stdout_level": "INFO",
                "emit_responses": True,
            },
            "responses": {
                "emit_ack": True,
                "response_channel": "system",
                "response_timeout": 10,
            },
        }
        
        if config_path and config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
                logger.info(f"Configuration loaded from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load configuration from {config_path}: {e}")
        
        return default_config
    
    def _load_state(self):
        """Load previous processing state"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                self.processing_stats.events_processed = state.get('events_processed', 0)
                self.processing_stats.events_forwarded = state.get('events_forwarded', 0)
                self.processing_stats.events_filtered = state.get('events_filtered', 0)
                self.processing_stats.events_failed = state.get('events_failed', 0)
                
                if state.get('last_processed'):
                    self.processing_stats.last_processed = datetime.fromisoformat(state['last_processed'])
                
                logger.info(f"State loaded: {self.processing_stats.events_processed} events processed")
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Save current processing state"""
        try:
            state = {
                'events_processed': self.processing_stats.events_processed,
                'events_forwarded': self.processing_stats.events_forwarded,
                'events_filtered': self.processing_stats.events_filtered,
                'events_failed': self.processing_stats.events_failed,
                'last_processed': self.processing_stats.last_processed.isoformat() if self.processing_stats.last_processed else None,
                'start_time': self.processing_stats.start_time.isoformat(),
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
            logger.debug("State saved successfully")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def setup_logging(self):
        """Setup comprehensive logging for the bridge"""
        # Create a detailed logger for event processing
        event_logger = logging.getLogger("kilo_bridge.events")
        event_logger.setLevel(getattr(logging, self.config['logging']['level']))
        
        # File handler for event logs
        event_log_handler = logging.FileHandler(self.event_log_file)
        event_log_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - EventID: %(event_id)s - Source: %(source_agent)s - Project: %(project)s - Tags: %(tags)s'
        ))
        event_logger.addHandler(event_log_handler)
        
        # Store for later use
        self.event_logger = event_logger
    
    def log_event_processing(self, event: Dict[str, Any], status: str, error: Optional[str] = None):
        """Log event processing with full details"""
        try:
            event_id = event.get('event_id', 'unknown')
            source_agent = event.get('source', 'unknown')
            event_type = event.get('event_type', 'unknown')
            project = event.get('project', 'unknown')
            tags = event.get('tags', [])
            
            log_entry = EventLogEntry(
                timestamp=datetime.now(timezone.utc),
                event_id=event_id,
                source_agent=source_agent,
                event_type=event_type,
                project=project,
                tags=tags,
                payload=event.get('payload', {}),
                processed=True,
                status=status,
                error_message=error
            )
            
            # Log to file
            log_data = {
                'timestamp': log_entry.timestamp.isoformat(),
                'event_id': log_entry.event_id,
                'source_agent': log_entry.source_agent,
                'event_type': log_entry.event_type,
                'project': log_entry.project,
                'tags': log_entry.tags,
                'payload': log_entry.payload,
                'processed': log_entry.processed,
                'status': log_entry.status,
                'error_message': log_entry.error_message,
            }
            
            with open(self.event_log_file, 'a') as f:
                f.write(json.dumps(log_data) + "\n")
            
            # Also log to structured logger
            self.event_logger.info(
                f"Event processed - EventID: {event_id} - Source: {source_agent} - Project: {project} - Tags: {tags} - Status: {status}",
                extra={
                    'event_id': event_id,
                    'source_agent': source_agent,
                    'project': project,
                    'tags': tags,
                }
            )
            
            logger.debug(f"Event logged: {event_id} - {status}")
            
        except Exception as e:
            logger.error(f"Failed to log event: {e}")
    
    def _should_process_event(self, event: Dict[str, Any]) -> tuple[bool, str]:
        """Check if an event should be processed based on filters"""
        event_tags = event.get('tags', [])
        project = event.get('project', '')
        
        # Check include tags
        include_tags = set(self.event_filter.include_tags)
        event_tag_set = set(event_tags)
        
        if not include_tags.intersection(event_tag_set):
            return False, f"No matching include tags: required {include_tags}, got {event_tag_set}"
        
        # Check exclude tags
        exclude_tags = set(self.event_filter.exclude_tags)
        if exclude_tags.intersection(event_tag_set):
            return False, f"Excluded tags present: {exclude_tags.intersection(event_tag_set)}"
        
        # Check project targets
        project_targets = set(self.event_filter.project_targets)
        if project and project not in project_targets:
            return False, f"Project '{project}' not in target projects: {project_targets}"
        
        return True, "Event passes all filters"
    
    def _forward_to_stdout(self, event: Dict[str, Any], processing_info: Dict[str, Any]):
        """Forward event to stdout if enabled"""
        if not self.config['forwarding']['stdout_enabled']:
            return
        
        stdout_level = self.config['forwarding']['stdout_level']
        event_type = event.get('event_type', 'unknown')
        
        # Determine if event should be printed based on level
        level_map = {
            'DEBUG': 10,
            'INFO': 20,
            'WARNING': 30,
            'ERROR': 40,
            'CRITICAL': 50,
        }
        
        event_level = level_map.get(event.get('level', 'INFO'), 20)
        min_level = level_map.get(stdout_level, 20)
        
        if event_level < min_level:
            return
        
        # Format output
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        event_id = event.get('event_id', 'unknown')
        source_agent = event.get('source', 'unknown')
        project = event.get('project', 'unknown')
        
        output = f"[{timestamp}] [{event_type}] EventID: {event_id} | Source: {source_agent} | Project: {project} | Tags: {event.get('tags', [])}"
        
        if 'payload' in event and event['payload']:
            output += f"\nPayload: {json.dumps(event['payload'], indent=2)}"
        
        if 'status' in processing_info:
            output += f"\nProcessing Status: {processing_info['status']}"
        
        print(output)
        logger.debug(f"Forwarded to stdout: {event_id}")
    
    def _emit_response_event(self, original_event: Dict[str, Any], processing_info: Dict[str, Any]):
        """Emit a response event for processed events"""
        if not self.config['responses']['emit_ack']:
            return
        
        response_event = {
            'event_id': f"KIL_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{original_event.get('event_id', 'unknown')}",
            'created_at': datetime.now(timezone.utc).isoformat(),
            'event_type': 'KILO_EVENT_PROCESSED',
            'source': 'kilo_bridge',
            'target': original_event.get('source', 'unknown'),
            'project': original_event.get('project', 'system'),
            'tags': ['ack', 'processed', 'kilo_bridge'],
            'payload': {
                'original_event_id': original_event.get('event_id'),
                'status': 'ack',
                'processing_duration_ms': processing_info.get('duration_ms'),
                'processed_at': datetime.now(timezone.utc).isoformat(),
                'filter_match': processing_info.get('filter_match', 'unknown'),
            },
            'priority': 'normal',
            'requires_response': False,
        }
        
        try:
            # Emit the response event
            emit_event(
                event_type=response_event['event_type'],
                payload=response_event['payload'],
                source='kilo_bridge',
                origin=original_event.get('source', 'unknown'),
                channel='system',
                tags=response_event['tags']
            )
            
            logger.debug(f"Response event emitted: {response_event['event_id']}")
        
        except Exception as e:
            logger.error(f"Failed to emit response event: {e}")
    
    def _process_event_batch(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process a batch of events"""
        processed_events = []
        failed_events = []
        
        for event in events:
            event_start = datetime.now(timezone.utc)
            event_id = event.get('event_id', 'unknown')
            
            try:
                # Check if event should be processed
                should_process, filter_reason = self._should_process_event(event)
                
                if not should_process:
                    self.processing_stats.events_filtered += 1
                    self.log_event_processing(event, 'filtered', filter_reason)
                    logger.debug(f"Event filtered out: {event_id} - {filter_reason}")
                    continue
                
                # Process the event
                self.processing_stats.events_processed += 1
                
                # Forward to stdout if applicable
                processing_info = {
                    'status': 'processing',
                    'filter_match': filter_reason,
                    'start_time': event_start.isoformat(),
                }
                
                self._forward_to_stdout(event, processing_info)
                
                # Emit response event
                if self.config['forwarding']['emit_responses']:
                    self._emit_response_event(event, processing_info)
                
                # Log successful processing
                processing_duration = (datetime.now(timezone.utc) - event_start).total_seconds() * 1000
                self.log_event_processing(event, 'processed')
                
                processing_info.update({
                    'status': 'success',
                    'duration_ms': processing_duration,
                    'processed_at': datetime.now(timezone.utc).isoformat(),
                })
                
                processed_events.append({
                    **event,
                    'processing_info': processing_info,
                    'processed_at': datetime.now(timezone.utc).isoformat(),
                })
                
                logger.info(f"Event processed successfully: {event_id}")
                
            except Exception as e:
                self.processing_stats.events_failed += 1
                error_message = str(e)
                
                # Log processing error
                self.log_event_processing(event, 'error', error_message)
                
                # Add to failed events list
                failed_events.append({
                    **event,
                    'processing_info': {
                        'status': 'error',
                        'error': error_message,
                        'error_time': datetime.now(timezone.utc).isoformat(),
                    },
                })
                
                logger.error(f"Failed to process event {event_id}: {error_message}")
        
        return processed_events
    
    async def listen_for_kilo_events(self):
        """
        Continuous event handling loop that polls agent_bus for events and processes them.
        
        This method runs indefinitely, continuously polling the event bus for new events,
        filtering them based on configuration, processing them, and forwarding results.
        """
        logger.info("Starting Kilo Bridge event handling loop")
        
        polling_interval = self.config['processing']['polling_interval_seconds']
        batch_size = self.config['processing']['batch_size']
        
        try:
            while True:
                loop_start = datetime.now(timezone.utc)
                
                try:
                    # Poll for events with batch size limit
                    events, next_offset = read_events(limit=batch_size)
                    
                    if events:
                        logger.info(f"Received {len(events)} events from agent_bus")
                        
                        # Process events in batch
                        processed_events = self._process_event_batch(events)
                        
                        # Log batch statistics
                        batch_duration = (datetime.now(timezone.utc) - loop_start).total_seconds()
                        logger.info(
                            f"Batch processed: {len(events)} total, "
                            f"{len(processed_events)} successful, "
                            f"{self.processing_stats.events_filtered} filtered, "
                            f"{self.processing_stats.events_failed} failed, "
                            f"duration: {batch_duration:.2f}s"
                        )
                        
                        # Update last processed time
                        self.processing_stats.last_processed = datetime.now(timezone.utc)
                    
                    else:
                        logger.debug(f"No events found, polling in {polling_interval}s")
                    
                    # Save state periodically
                    if len(events) > 0:
                        self._save_state()
                
                except Exception as e:
                    logger.error(f"Error in event processing loop: {e}")
                    self.processing_stats.events_failed += 1
                
                # Sleep until next polling interval
                await asyncio.sleep(polling_interval)
                
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down gracefully")
        except Exception as e:
            logger.error(f"Fatal error in event processing loop: {e}")
        
        finally:
            # Save final state before shutdown
            self._save_state()
            logger.info("Kilo Bridge shutdown complete")
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get current processing statistics"""
        stats = {
            'events_processed': self.processing_stats.events_processed,
            'events_forwarded': self.processing_stats.events_forwarded,
            'events_filtered': self.processing_stats.events_filtered,
            'events_failed': self.processing_stats.events_failed,
            'last_processed': self.processing_stats.last_processed.isoformat() if self.processing_stats.last_processed else None,
            'start_time': self.processing_stats.start_time.isoformat(),
            'uptime_seconds': (datetime.now(timezone.utc) - self.processing_stats.start_time).total_seconds(),
        }
        
        # Calculate success rate
        total_processed = self.processing_stats.events_processed + self.processing_stats.events_failed
        if total_processed > 0:
            stats['success_rate'] = (self.processing_stats.events_processed / total_processed) * 100
        else:
            stats['success_rate'] = 0.0
        
        return stats
    
    def update_filters(self, **kwargs):
        """Update event filtering configuration"""
        for key, value in kwargs.items():
            if hasattr(self.event_filter, key):
                setattr(self.event_filter, key, value)
                logger.info(f"Updated filter '{key}' to: {value}")
            else:
                logger.warning(f"Unknown filter key: {key}")
    
    def add_project_target(self, project: str):
        """Add a project to the target projects list"""
        if project not in self.event_filter.project_targets:
            self.event_filter.project_targets.append(project)
            logger.info(f"Added project target: {project}")
    
    def remove_project_target(self, project: str):
        """Remove a project from the target projects list"""
        if project in self.event_filter.project_targets:
            self.event_filter.project_targets.remove(project)
            logger.info(f"Removed project target: {project}")


def main():
    """Main entry point for the Kilo Bridge"""
    # Initialize the bridge
    bridge = KiloBridge()
    
    # Display configuration
    logger.info("Kilo Bridge Configuration:")
    logger.info(f"  Event Filters - Include: {bridge.event_filter.include_tags}")
    logger.info(f"  Event Filters - Exclude: {bridge.event_filter.exclude_tags}")
    logger.info(f"  Event Filters - Project Targets: {bridge.event_filter.project_targets}")
    logger.info(f"  Polling Interval: {bridge.config['processing']['polling_interval_seconds']}s")
    logger.info(f"  Batch Size: {bridge.config['processing']['batch_size']}")
    logger.info(f"  Forwarding to stdout: {bridge.config['forwarding']['stdout_enabled']}")
    logger.info(f"  Emit response events: {bridge.config['responses']['emit_ack']}")
    
    print("\n" + "="*60)
    print("KILO BRIDGE - Event Handling Loop")
    print("="*60)
    print(f"Monitoring agent_bus for events with filters:")
    print(f"  - Include tags: {bridge.event_filter.include_tags}")
    print(f"  - Exclude tags: {bridge.event_filter.exclude_tags}")
    print(f"  - Project targets: {bridge.event_filter.project_targets}")
    print(f"  - Polling interval: {bridge.config['processing']['polling_interval_seconds']}s")
    print(f"  - Response events: {'Enabled' if bridge.config['responses']['emit_ack'] else 'Disabled'}")
    print("\nPress Ctrl+C to stop the bridge")
    print("="*60 + "\n")
    
    # Run the event handling loop
    try:
        asyncio.run(bridge.listen_for_kilo_events())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        raise
    
    # Display final statistics
    stats = bridge.get_processing_stats()
    logger.info("\nFinal Processing Statistics:")
    logger.info(f"  Events processed: {stats['events_processed']}")
    logger.info(f"  Events forwarded: {stats['events_forwarded']}")
    logger.info(f"  Events filtered: {stats['events_filtered']}")
    logger.info(f"  Events failed: {stats['events_failed']}")
    logger.info(f"  Success rate: {stats['success_rate']:.2f}%")
    logger.info(f"  Uptime: {stats['uptime_seconds']:.2f} seconds")
    
    print("\nProcessing Statistics:")
    print(f"  Events processed: {stats['events_processed']}")
    print(f"  Events forwarded: {stats['events_forwarded']}")
    print(f"  Events filtered: {stats['events_filtered']}")
    print(f"  Events failed: {stats['events_failed']}")
    print(f"  Success rate: {stats['success_rate']:.2f}%")
    print(f"  Uptime: {stats['uptime_seconds']:.2f} seconds")


if __name__ == "__main__":
    main()
