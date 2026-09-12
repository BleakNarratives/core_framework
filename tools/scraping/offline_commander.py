#!/usr/bin/env python3
"""
OFFLINE COMMANDER - Fixed version with working SmartCoder
"""
import sys
import os
from smart_coder import SmartCoder
from project_memory import memory

class OfflineCommander:
    def __init__(self):
        self.coder = SmartCoder()
        from termux_voice import tts

# Then in the commands dictionary, add:
  self.commands = {
    "#python": self.handle_python,
    "#react": self.handle_react,
    "#task": self.handle_task, 
    "#bug": self.handle_bug,
    "#feature": self.handle_feature,
    "#project": self.handle_project,
    "#tts": self.handle_tts,  # ADD THIS LINE
    "#scan": self.handle_scan,  # ADD THIS LINE
}

# Add these handler methods:
def handle_tts(self, command):
    text = command.replace("#tts", "").strip()
    print(f"🔊 TTS COMMAND: {text}")
    tts.speak(text)
    return {"status": "tts_spoken", "text": text}

def handle_scan(self, command):
    path = command.replace("#scan", "").strip() or "."
    print(f"🔍 SCAN COMMAND: {path}")
    tts.speak(f"Scanning directory {path}")
    # Add your directory scanning logic here
    return {"status": "scanning", "path": path}
            "#python": self.handle_python,
            "#react": self.handle_react,
            "#task": self.handle_task,
            "#bug": self.handle_bug,
            "#feature": self.handle_feature,
            "#project": self.handle_project
        }
    
    def process_command(self, command):
        """Process any command offline"""
        print(f"💬 OFFLINE COMMAND: {command}")
        
        for cmd_prefix, handler in self.commands.items():
            if command.startswith(cmd_prefix):
                return handler(command)
        
        return self.handle_unknown(command)
    
    def handle_python(self, command):
        description = command.replace("#python", "").strip()
        result = self.coder.generate_from_description(description, "python")
        
        # Save to memory
        memory.learn_pattern("python_generation", description, result)
        
        # Save files
        for filename, content in result["files"].items():
            with open(filename, 'w') as f:
                f.write(content)
            print(f"📄 Created: {filename}")
        
        return {"status": "python_generated", "result": result}
    
    def handle_react(self, command):
        description = command.replace("#react", "").strip()
        result = self.coder.generate_from_description(description, "react")
        
        # Save to memory
        memory.learn_pattern("react_generation", description, result)
        
        # Save files
        for filename, content in result["files"].items():
            with open(filename, 'w') as f:
                f.write(content)
            print(f"📄 Created: {filename}")
        
        return {"status": "react_generated", "result": result}
    
    def handle_task(self, command):
        task = command.replace("#task", "").strip()
        print(f"🎯 OFFLINE TASK: {task}")
        
        # Create a simple task file
        task_file = f"task_{hash(task) % 10000}.txt"
        with open(task_file, 'w') as f:
            f.write(f"Task: {task}\nCreated: Offline Commander\nStatus: Pending")
        
        return {"status": "task_created", "task": task, "file": task_file}
    
    def handle_bug(self, command):
        bug = command.replace("#bug", "").strip()
        print(f"🐛 OFFLINE BUG FIX: {bug}")
        
        # Create a bug investigation file
        bug_file = f"bug_{hash(bug) % 10000}.txt"
        with open(bug_file, 'w') as f:
            f.write(f"Bug: {bug}\nStatus: Investigating\nPriority: High")
        
        return {"status": "bug_investigating", "bug": bug, "file": bug_file}
    
    def handle_feature(self, command):
        feature = command.replace("#feature", "").strip()
        print(f"✨ OFFLINE FEATURE: {feature}")
        
        # Create a feature planning file
        feature_file = f"feature_{hash(feature) % 10000}.txt"
        with open(feature_file, 'w') as f:
            f.write(f"Feature: {feature}\nStatus: Planning\nPriority: Medium")
        
        return {"status": "feature_planned", "feature": feature, "file": feature_file}
    
    def handle_project(self, command):
        project = command.replace("#project", "").strip()
        print(f"📁 OFFLINE PROJECT: {project}")
        
        # Create project directory
        project_dir = f"project_{hash(project) % 10000}"
        os.makedirs(project_dir, exist_ok=True)
        
        # Create basic project files
        with open(os.path.join(project_dir, "README.md"), 'w') as f:
            f.write(f"# {project}\n\nAutomatically generated project.")
        
        with open(os.path.join(project_dir, "main.py"), 'w') as f:
            f.write(f'# {project}\nprint("Hello from {project}!")\n')
        
        return {"status": "project_created", "project": project, "directory": project_dir}
    
    def handle_unknown(self, command):
        print(f"❓ UNKNOWN COMMAND: {command}")
        return {"status": "unknown_command", "command": command}

def main():
    commander = OfflineCommander()
    
    if len(sys.argv) > 1:
        # Process command from args
        command = " ".join(sys.argv[1:])
        result = commander.process_command(command)
        print(f"✅ RESULT: {result['status']}")
    else:
        # Interactive mode
        print("🤖 OFFLINE COMMANDER READY!")
        print("Commands: #python, #react, #task, #bug, #feature, #project")
        print("Type 'exit' to quit")
        
        while True:
            try:
                command = input("\n💬 Command: ").strip()
                if command.lower() in ['exit', 'quit']:
                    break
                result = commander.process_command(command)
                print(f"📦 Result: {result['status']}")
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break

if __name__ == "__main__":
    main()