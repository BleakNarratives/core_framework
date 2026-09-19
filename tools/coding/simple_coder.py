#!/usr/bin/env python3
"""
SIMPLE CODER - No f-strings, just works
MOLT Living Markdown extension: parses SKILL.md frontmatter and hooks RAG indices
"""
import re
import json
from pathlib import Path

# Optional MOLT imports — graceful degrade if MOLT not installed
try:
    from src.skill.skill_manager import SkillManager
    HAS_MOLT = True
except ImportError:
    SkillManager = None
    HAS_MOLT = False

try:
    from src.skill.governor import Governor
    HAS_GOVERNOR = True
except ImportError:
    Governor = None
    HAS_GOVERNOR = False


class SimpleCoder:
    def __init__(self, skill_name=None, oomf_level=None):
        # MOLT: optional living skill context
        self.skill_name = skill_name
        self.oomf_level = oomf_level
        self._molt_context = None
        if HAS_MOLT and skill_name:
            try:
                mgr = SkillManager()
                self._molt_context = mgr.hydrate(skill_name, oomf_level=oomf_level)
            except Exception:
                self._molt_context = None

    def parse_skill_frontmatter(self, skill_name_or_path):
        """MOLT: Parse and enforce SKILL.md YAML frontmatter. Returns dict with defaults."""
        if not HAS_MOLT:
            return {}
        try:
            mgr = SkillManager()
            return mgr.parse_frontmatter(skill_name_or_path)
        except Exception:
            return {}

    def hydrate_rag_context(self, skill_name, oomf_level=None):
        """MOLT: Hook into local RAG indices (rag_storage/sidecars). Returns hydrated prompt chunk."""
        if not HAS_MOLT:
            return ""
        try:
            mgr = SkillManager()
            return mgr.hydrate(skill_name, oomf_level=oomf_level or self.oomf_level)
        except Exception:
            return ""

    def enforce_frontmatter(self, path, overrides=None):
        """MOLT: Ensure SKILL.md at path has valid Living frontmatter. Returns final frontmatter."""
        if not HAS_MOLT:
            return {}
        try:
            mgr = SkillManager()
            return mgr.inject_frontmatter(Path(path), overrides=overrides)
        except Exception as e:
            return {"error": str(e)}

    def _molt_prefix(self):
        """Internal: prefix for generated code that includes MOLT context as comment."""
        if self._molt_context:
            snippet = self._molt_context[:1200].replace("*/", "* /")
            return f"/* MOLT skill:{self.skill_name} oomf:{self.oomf_level} hydrated */\n/* {snippet[:500]} */\n"
        return ""

    def generate_python(self, description):
        """Generate Python code safely"""
        class_name = self.to_class_name(description)

        molt_note = ""
        if self._molt_context:
            molt_note = f"# MOLT hydrated: {self.skill_name} (oomf {self.oomf_level})\n"

        code = molt_note + '''# Auto-generated: ''' + description + '''
# Created by SimpleCoder

class ''' + class_name + ''':
    """''' + description + '''"""
    
    def __init__(self):
        self.description = "''' + description + '''"
        self.status = "generated"
    
    def execute(self):
        """Execute the main functionality"""
        print("Executing:", self.description)
        return {"status": "success", "task": self.description}

def main():
    processor = ''' + class_name + '''()
    result = processor.execute()
    print(result)

if __name__ == "__main__":
    main()
'''
        return {
            "files": {
                f"{class_name.lower()}.py": code
            },
            "type": "python_class",
            "molt": {
                "skill": self.skill_name,
                "oomf": self.oomf_level,
                "hydrated": bool(self._molt_context),
            } if self.skill_name else None
        }
    
    def generate_login_system(self):
        """Generate login system"""
        code = '''import hashlib

class AuthSystem:
    def __init__(self):
        self.users = {}
    
    def register(self, username, password):
        hashed = hashlib.sha256(password.encode()).hexdigest()
        self.users[username] = hashed
        return {"status": "registered", "user": username}
    
    def login(self, username, password):
        hashed = hashlib.sha256(password.encode()).hexdigest()
        if self.users.get(username) == hashed:
            return {"status": "authenticated", "user": username}
        return {"status": "failed"}

# Test the system
if __name__ == "__main__":
    auth = AuthSystem()
    auth.register("test", "pass")
    result = auth.login("test", "pass")
    print("Login result:", result)
'''
        # MOLT: prepend context if available
        if self._molt_context:
            code = f"# MOLT skill:{self.skill_name} oomf:{self.oomf_level}\n" + code
        return {
            "files": {
                "auth_system.py": code
            },
            "type": "login_system",
            "molt": {
                "skill": self.skill_name,
                "oomf": self.oomf_level,
            } if self.skill_name else None
        }

    def generate_with_skill(self, description, skill_name=None, oomf_level=None):
        """MOLT: Generate code hydrated with a Living skill's RAG context."""
        # Temporarily switch skill context
        orig_skill, orig_oomf, orig_ctx = self.skill_name, self.oomf_level, self._molt_context
        target = skill_name or self.skill_name
        lvl = oomf_level if oomf_level is not None else self.oomf_level
        if HAS_MOLT and target:
            try:
                mgr = SkillManager()
                self.skill_name = target
                self.oomf_level = lvl or 3
                self._molt_context = mgr.hydrate(target, oomf_level=self.oomf_level)
            except Exception:
                pass
        result = self.generate_python(description)
        # Restore
        self.skill_name, self.oomf_level, self._molt_context = orig_skill, orig_oomf, orig_ctx
        return result
    
    def to_class_name(self, description):
        """Convert description to class name"""
        words = description.split()
        class_name = ''.join(word.capitalize() for word in words)
        return class_name or "AutoGenerated"

def main():
    coder = SimpleCoder()
    
    # Test generation
    result = coder.generate_python("user authentication system")
    print(" Generated Python class")
    
    # Save the file
    for filename, content in result["files"].items():
        with open(filename, 'w') as f:
            f.write(content)
        print(f" Saved: {filename}")

    # MOLT smoke test (no-op if no skill)
    if HAS_MOLT:
        print("MOLT: SkillManager available — try SimpleCoder(skill_name='my-living-skill', oomf_level=3)")

if __name__ == "__main__":
    main()
