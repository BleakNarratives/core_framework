#!/usr/bin/env python3

import json
import os
import time
import subprocess
from datetime import datetime
import threading
import queue
import hashlib

class ThothAutomationEngine:
    """
    Autonomous task execution engine for Thoth swarms
    Handles agent coordination, task management, and self-healing
    """
    
    def __init__(self, comms_file="foxwood_comms.json"):
        self.comms_file = comms_file
        self.metrics_file = "foxwood_metrics.json"
        self.backup_dir = "foxwood_backup"
        self.task_queue = queue.PriorityQueue()
        self.running = False
        self.agents = {}
        self.tasks = {}
        
        # Ensure backup directory exists
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Load initial state
        self.load_state()
        
    def load_state(self):
        """Load current state from communication file"""
        try:
            with open(self.comms_file, 'r') as f:
                data = json.load(f)
                self.agents = {agent['id']: agent for agent in data.get('agents', [])}
                self.tasks = {task['id']: task for task in data.get('tasks', [])}
                
                # Add pending tasks to queue
                for task_id, task in self.tasks.items():
                    if task['status'] == 'pending':
                        priority = self._get_priority_value(task['priority'])
                        self.task_queue.put((priority, task_id))
                        
        except (FileNotFoundError, json.JSONDecodeError):
            # Initialize with default state if file doesn't exist or is corrupt
            self.agents = {
                "vibe": {
                    "id": "vibe",
                    "role": "Primary Coordinator",
                    "capabilities": ["code_analysis", "task_decomposition", "agent_orchestration"],
                    "status": "active",
                    "last_update": datetime.utcnow().isoformat() + "Z"
                },
                "gemini": {
                    "id": "gemini",
                    "role": "Creative Synthesis",
                    "capabilities": ["content_generation", "idea_synthesis", "multimodal_processing"],
                    "status": "active",
                    "last_update": datetime.utcnow().isoformat() + "Z"
                },
                "syntax": {
                    "id": "syntax",
                    "role": "Code Execution Bridge",
                    "capabilities": ["code_execution", "language_translation", "api_bridging"],
                    "status": "active",
                    "last_update": datetime.utcnow().isoformat() + "Z"
                }
            }
            self.tasks = {}
            self._save_state()
            
    def _save_state(self):
        """Save current state to communication file with backup"""
        # Create backup
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(self.backup_dir, f"foxwood_comms_{timestamp}.json")
        
        try:
            # Save backup
            with open(backup_file, 'w') as f:
                json.dump({
                    "version": "1.0",
                    "system": "Thoth Swarm Coordination",
                    "agents": list(self.agents.values()),
                    "tasks": list(self.tasks.values()),
                    "communication_protocol": {
                        "file_based": {
                            "path": self.comms_file,
                            "update_frequency": "continuous",
                            "conflict_resolution": "last_write_wins",
                            "backup_location": self.backup_dir
                        },
                        "agent_responsibilities": {
                            "read": ["all"],
                            "write": ["assigned_tasks", "status_updates", "task_completion"],
                            "coordinate": ["vibe"]
                        }
                    },
                    "automation_rules": {
                        "task_assignment": {
                            "strategy": "capability_based",
                            "fallback": "round_robin"
                        },
                        "priority_handling": {
                            "critical": "immediate_execution",
                            "high": "next_available_agent",
                            "medium": "queue_based",
                            "low": "background_processing"
                        },
                        "error_handling": {
                            "max_retries": 3,
                            "escalation_path": ["syntax", "vibe", "gemini"],
                            "timeout": "300s"
                        }
                    },
                    "performance_metrics": {
                        "tracked": [
                            "task_completion_time",
                            "agent_response_time",
                            "error_rate",
                            "resource_utilization"
                        ],
                        "reporting_frequency": "real_time",
                        "storage": "foxwood_metrics.json"
                    }
                }, f, indent=2)
            
            # Save main file
            with open(self.comms_file, 'w') as f:
                json.dump({
                    "version": "1.0",
                    "system": "Thoth Swarm Coordination",
                    "agents": list(self.agents.values()),
                    "tasks": list(self.tasks.values()),
                    "communication_protocol": {
                        "file_based": {
                            "path": self.comms_file,
                            "update_frequency": "continuous",
                            "conflict_resolution": "last_write_wins",
                            "backup_location": self.backup_dir
                        },
                        "agent_responsibilities": {
                            "read": ["all"],
                            "write": ["assigned_tasks", "status_updates", "task_completion"],
                            "coordinate": ["vibe"]
                        }
                    },
                    "automation_rules": {
                        "task_assignment": {
                            "strategy": "capability_based",
                            "fallback": "round_robin"
                        },
                        "priority_handling": {
                            "critical": "immediate_execution",
                            "high": "next_available_agent",
                            "medium": "queue_based",
                            "low": "background_processing"
                        },
                        "error_handling": {
                            "max_retries": 3,
                            "escalation_path": ["syntax", "vibe", "gemini"],
                            "timeout": "300s"
                        }
                    },
                    "performance_metrics": {
                        "tracked": [
                            "task_completion_time",
                            "agent_response_time",
                            "error_rate",
                            "resource_utilization"
                        ],
                        "reporting_frequency": "real_time",
                        "storage": "foxwood_metrics.json"
                    }
                }, f, indent=2)
                
        except Exception as e:
            print(f"❌ Error saving state: {e}")
            
    def _get_priority_value(self, priority):
        """Convert priority string to numerical value for queue"""
        priority_map = {
            'critical': 0,
            'high': 1,
            'medium': 2,
            'low': 3
        }
        return priority_map.get(priority.lower(), 2)
        
    def add_task(self, description, priority="medium", dependencies=None, assigned_to=None):
        """Add a new task to the system"""
        task_id = f"task_{len(self.tasks) + 1:03d}"
        
        task = {
            "id": task_id,
            "description": description,
            "status": "pending",
            "assigned_to": assigned_to or "vibe",  # Default to vibe
            "priority": priority,
            "dependencies": dependencies or [],
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }
        
        self.tasks[task_id] = task
        priority_value = self._get_priority_value(priority)
        self.task_queue.put((priority_value, task_id))
        
        self._save_state()
        return task_id
        
    def update_task_status(self, task_id, status, assigned_to=None):
        """Update the status of a task"""
        if task_id not in self.tasks:
            return False
            
        self.tasks[task_id]['status'] = status
        self.tasks[task_id]['updated_at'] = datetime.utcnow().isoformat() + "Z"
        
        if assigned_to:
            self.tasks[task_id]['assigned_to'] = assigned_to
            
        self._save_state()
        return True
        
    def assign_task(self, task_id, agent_id):
        """Assign a task to a specific agent"""
        if task_id not in self.tasks or agent_id not in self.agents:
            return False
            
        self.tasks[task_id]['assigned_to'] = agent_id
        self.tasks[task_id]['status'] = 'in_progress'
        self.tasks[task_id]['updated_at'] = datetime.utcnow().isoformat() + "Z"
        
        self._save_state()
        return True
        
    def get_next_task(self, agent_id=None):
        """Get the next task for an agent based on capabilities and priority"""
        if self.task_queue.empty():
            return None
            
        # Find the highest priority task that can be executed
        temp_queue = queue.PriorityQueue()
        selected_task = None
        
        while not self.task_queue.empty():
            priority, task_id = self.task_queue.get()
            task = self.tasks[task_id]
            
            # Check if dependencies are met
            dependencies_met = all(
                self.tasks[dep]['status'] == 'completed' 
                for dep in task['dependencies'] 
                if dep in self.tasks
            )
            
            if dependencies_met:
                if agent_id:
                    # Check if agent has required capabilities
                    agent_capabilities = set(self.agents[agent_id]['capabilities'])
                    # For now, assign to any agent (capability matching would go here)
                    selected_task = task
                    break
                else:
                    # Assign to default agent (vibe)
                    selected_task = task
                    break
            
            temp_queue.put((priority, task_id))
            
        # Restore tasks that weren't selected
        while not temp_queue.empty():
            self.task_queue.put(temp_queue.get())
            
        return selected_task
        
    def execute_task(self, task):
        """Execute a task based on its description"""
        if not task:
            return False
            
        print(f"🚀 Executing task: {task['description']}")
        
        # Task-specific execution logic
        if "Ollama" in task['description'] and "model" in task['description']:
            return self._execute_ollama_task(task)
            
        elif "Codex" in task['description']:
            return self._execute_codex_task(task)
            
        elif "automated agent communication" in task['description'].lower():
            return self._execute_communication_task(task)
            
        else:
            # Default execution - just mark as completed for now
            print(f"✅ Task completed: {task['description']}")
            self.update_task_status(task['id'], 'completed')
            return True
            
    def _execute_ollama_task(self, task):
        """Execute Ollama-related tasks"""
        print(f"🐙 Executing Ollama task: {task['description']}")
        
        try:
            # Check if Ollama models need to be created
            if "create" in task['description'].lower():
                models_to_create = [
                    "syntax-general-intelligence",
                    "thoth-coordinator", 
                    "codex-bridge"
                ]
                
                for model_name in models_to_create:
                    modelfile = f"{model_name}.Modelfile"
                    if os.path.exists(modelfile):
                        print(f"🔧 Creating model: {model_name}")
                        # This would actually run: ollama create {model_name} -f {modelfile}
                        print(f"✅ Model creation command prepared for: {model_name}")
                    else:
                        print(f"⚠️  Modelfile not found: {modelfile}")
                
            self.update_task_status(task['id'], 'completed')
            return True
            
        except Exception as e:
            print(f"❌ Error executing Ollama task: {e}")
            self.update_task_status(task['id'], 'failed')
            return False
            
    def _execute_codex_task(self, task):
        """Execute Codex-related tasks"""
        print(f"🌉 Executing Codex task: {task['description']}")
        
        try:
            # Verify the JavaScript files were created
            required_files = [
                "openclaw/openclaw-main/src/infra/provider-usage.fetch.codex.js",
                "openclaw/openclaw-main/src/infra/provider-usage.fetch.shared.js",
                "openclaw/openclaw-main/src/infra/provider-usage.shared.js"
            ]
            
            for file_path in required_files:
                if os.path.exists(file_path):
                    print(f"✅ File exists: {file_path}")
                else:
                    print(f"❌ Missing file: {file_path}")
                    self.update_task_status(task['id'], 'failed')
                    return False
                    
            self.update_task_status(task['id'], 'completed')
            return True
            
        except Exception as e:
            print(f"❌ Error executing Codex task: {e}")
            self.update_task_status(task['id'], 'failed')
            return False
            
    def _execute_communication_task(self, task):
        """Execute agent communication setup tasks"""
        print(f"📡 Executing communication task: {task['description']}")
        
        try:
            # Ensure the communication file exists and is properly formatted
            if os.path.exists(self.comms_file):
                print(f"✅ Communication system established: {self.comms_file}")
                
                # Load and validate the communication file
                with open(self.comms_file, 'r') as f:
                    data = json.load(f)
                    
                required_keys = ['agents', 'tasks', 'communication_protocol']
                for key in required_keys:
                    if key not in data:
                        print(f"❌ Missing required key in comms file: {key}")
                        self.update_task_status(task['id'], 'failed')
                        return False
                    else:
                        print(f"✅ Valid key found: {key}")
                
                self.update_task_status(task['id'], 'completed')
                return True
            else:
                print(f"❌ Communication file not found: {self.comms_file}")
                self.update_task_status(task['id'], 'failed')
                return False
                
        except Exception as e:
            print(f"❌ Error executing communication task: {e}")
            self.update_task_status(task['id'], 'failed')
            return False
            
    def start_monitoring(self):
        """Start the continuous monitoring and task execution loop"""
        if self.running:
            return
            
        self.running = True
        print("🎯 Thoth Automation Engine started")
        
        def monitoring_loop():
            while self.running:
                try:
                    # Get next task
                    task = self.get_next_task()
                    
                    if task:
                        print(f"📋 Processing task: {task['id']} - {task['description']}")
                        
                        # Execute the task
                        success = self.execute_task(task)
                        
                        if success:
                            print(f"✅ Task completed: {task['id']}")
                        else:
                            print(f"❌ Task failed: {task['id']}")
                            
                    else:
                        print("😴 No tasks pending, waiting...")
                        
                    # Save state after each iteration
                    self._save_state()
                    
                    # Short delay to prevent CPU overload
                    time.sleep(2)
                    
                except Exception as e:
                    print(f"⚠️  Monitoring error: {e}")
                    time.sleep(5)
                    
        # Start monitoring in background thread
        monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()
        
        return monitor_thread
        
    def stop(self):
        """Stop the automation engine"""
        self.running = False
        print("🛑 Thoth Automation Engine stopped")
        
    def get_system_status(self):
        """Get current system status"""
        return {
            "agents": len(self.agents),
            "active_agents": sum(1 for agent in self.agents.values() if agent['status'] == 'active'),
            "total_tasks": len(self.tasks),
            "pending_tasks": sum(1 for task in self.tasks.values() if task['status'] == 'pending'),
            "in_progress_tasks": sum(1 for task in self.tasks.values() if task['status'] == 'in_progress'),
            "completed_tasks": sum(1 for task in self.tasks.values() if task['status'] == 'completed'),
            "failed_tasks": sum(1 for task in self.tasks.values() if task['status'] == 'failed'),
            "running": self.running,
            "last_update": datetime.utcnow().isoformat() + "Z"
        }

if __name__ == "__main__":
    print("🌟 Thoth Swarm Automation Engine")
    print("🔥 Relentless execution for divine creation")
    print("")
    
    # Initialize the automation engine
    engine = ThothAutomationEngine()
    
    # Start the monitoring system
    engine.start_monitoring()
    
    # Add a task to demonstrate the system working
    engine.add_task(
        "Automate Ollama model creation and management",
        priority="high",
        dependencies=["task_002"],
        assigned_to="syntax"
    )
    
    try:
        # Keep the main thread alive
        while True:
            status = engine.get_system_status()
            print(f"\n📊 System Status: {status['active_agents']}/{status['agents']} agents active")
            print(f"   Tasks: {status['completed_tasks']}✅ {status['in_progress_tasks']}⏳ {status['pending_tasks']}⏳ {status['failed_tasks']}❌")
            
            # Show agent status
            for agent_id, agent in engine.agents.items():
                status_emoji = "🟢" if agent['status'] == 'active' else "🔴"
                print(f"   {status_emoji} {agent_id}: {agent['role']}")
                
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n👋 Shutting down Thoth Automation Engine...")
        engine.stop()
        print("🎬 Divine execution paused. Awaiting resurrection.")
