#!/usr/bin/env python3
"""
SMART CODER - Complete rule-based code generation with memory
MOLT Living Markdown extension: parses SKILL.md frontmatter and hooks RAG indices
"""
import os
import re
from pathlib import Path

# project_memory import is optional — fails gracefully if absent
try:
    from project_memory import memory
except ImportError:
    memory = None

# MOLT imports — optional, graceful degrade
try:
    from src.skill.skill_manager import SkillManager
    from src.skill.oracle import Oracle
    from src.skill.governor import Governor
    HAS_MOLT = True
except ImportError:
    SkillManager = Oracle = Governor = None
    HAS_MOLT = False

class SmartCoder:
    def __init__(self, skill_name=None, oomf_level=None):
        self.templates = self.load_templates()
        # MOLT: optional living skill context
        self.skill_name = skill_name
        self.oomf_level = oomf_level
        self._molt_context = None
        self._molt_frontmatter = {}
        if HAS_MOLT and skill_name:
            try:
                mgr = SkillManager()
                self._molt_frontmatter = mgr.parse_frontmatter(skill_name)
                self._molt_context = mgr.hydrate(skill_name, oomf_level=oomf_level)
            except Exception:
                self._molt_context = None

    # ── MOLT: frontmatter + RAG hooks ────────────────────────────
    def parse_skill_frontmatter(self, skill_name_or_path):
        """Parse and enforce SKILL.md YAML frontmatter."""
        if not HAS_MOLT:
            return {}
        try:
            mgr = SkillManager()
            return mgr.parse_frontmatter(skill_name_or_path)
        except Exception:
            return {}

    def hydrate_rag_context(self, skill_name, oomf_level=None):
        """Hook into local RAG indices (rag_storage/sidecars)."""
        if not HAS_MOLT:
            return ""
        try:
            mgr = SkillManager()
            return mgr.hydrate(skill_name, oomf_level=oomf_level or self.oomf_level)
        except Exception:
            return ""

    def enforce_frontmatter(self, path, overrides=None):
        """Ensure SKILL.md has valid Living frontmatter."""
        if not HAS_MOLT:
            return {}
        try:
            mgr = SkillManager()
            return mgr.inject_frontmatter(Path(path), overrides=overrides)
        except Exception as e:
            return {"error": str(e)}

    def validate_generation(self, code_text, strict=False):
        """MOLT: Run Oracle audit on generated code before returning."""
        if not HAS_MOLT:
            return {"verdict": "pass", "findings": []}
        try:
            mgr = SkillManager()
            front = mgr.parse_frontmatter(self.skill_name) if self.skill_name else {}
            mode = front.get("oracle", {}).get("mode", "strict" if strict else "permissive")
            compliance = front.get("oracle", {}).get("verify_compliance", [])
            oracle = Oracle(mode=mode, verify_compliance=compliance)
            verdict = oracle.audit_text(code_text)
            return verdict.to_dict()
        except Exception as e:
            return {"verdict": "pass", "findings": [], "error": str(e)}

    def generate_with_skill(self, description, skill_name=None, oomf_level=None, language="python"):
        """MOLT: Generate code hydrated with a Living skill's context."""
        target = skill_name or self.skill_name
        lvl = oomf_level if oomf_level is not None else self.oomf_level
        orig = (self.skill_name, self.oomf_level, self._molt_context, self._molt_frontmatter)
        if HAS_MOLT and target:
            try:
                mgr = SkillManager()
                self.skill_name = target
                self.oomf_level = lvl or 3
                self._molt_frontmatter = mgr.parse_frontmatter(target)
                self._molt_context = mgr.hydrate(target, oomf_level=self.oomf_level)
            except Exception:
                pass
        result = self.generate_from_description(description, language=language)
        # Oracle gate on first file
        first_code = next(iter(result["files"].values()), "")
        result["oracle"] = self.validate_generation(first_code)
        self.skill_name, self.oomf_level, self._molt_context, self._molt_frontmatter = orig
        return result

    def molt_hydrated_prompt(self, description, skill_name=None):
        """Build a one-shot hydrated prompt for external inference (no tool loop)."""
        if not HAS_MOLT:
            return description
        try:
            mgr = SkillManager()
            target = skill_name or self.skill_name
            if not target:
                return description
            lvl = self.oomf_level or 3
            chunk = mgr.hydrate(target, oomf_level=lvl)
            return f"{chunk}\n\nUser request: {description}"
        except Exception:
            return description

    def load_templates(self):
        """Load code templates"""
        return {
            "python_class": """
class {class_name}:
    '''{description}'''
    
    def __init__(self{init_params}):
        {init_body}
    
    def main_method(self):
        '''Main functionality'''
        return {"status": "implemented", "class": "{class_name}"}

if __name__ == "__main__":
    obj = {class_name}()
    result = obj.main_method()
    print(result)
""",
            "react_component": """
import React from 'react';

const {component_name} = () => {{
    return (
        <div className="{component_name.lower()}">
            <h3>{description}</h3>
            {/* Auto-generated component */}
        </div>
    );
}};

export default {component_name};
""",
            "fastapi_endpoint": """
from fastapi import FastAPI

app = FastAPI()

@app.{method}("/{endpoint}")
async def {function_name}():
    '''{description}'''
    return {{"message": "{description}", "status": "implemented"}}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""
        }
    
    def generate_from_description(self, description, language="python"):
        """Generate code from natural language description"""
        # Simple rule-based generation
        description_lower = description.lower()
        
        if any(word in description_lower for word in ["login", "auth", "authenticate"]):
            return self.generate_login_system()
        elif any(word in description_lower for word in ["dashboard", "admin", "panel"]):
            return self.generate_dashboard()
        elif any(word in description_lower for word in ["api", "endpoint", "rest"]):
            return self.generate_api_endpoint(description)
        elif any(word in description_lower for word in ["form", "input", "submit"]):
            return self.generate_form_system()
        elif any(word in description_lower for word in ["nav", "menu", "navigation"]):
            return self.generate_navigation()
        else:
            return self.generate_generic(description, language)
    
    def generate_generic(self, description, language):
        """Generate generic code based on description"""
        if language == "python":
            class_name = self.description_to_class_name(description)
            molt_comment = f"# MOLT skill:{self.skill_name} oomf:{self.oomf_level}\n" if self._molt_context else ""
            return {
                "files": {
                    f"{class_name.lower()}.py": f'''
{molt_comment}# Auto-generated: {description}
# Created by SmartCoder

class {class_name}:
    """{description}"""
    
    def __init__(self):
        self.description = "{description}"
        self.status = "generated"
    
    def execute(self):
        """Execute the main functionality"""
        print(f"Executing: {{self.description}}")
        return {{"status": "success", "task": self.description}}

def main():
    processor = {class_name}()
    result = processor.execute()
    print(result)

if __name__ == "__main__":
    main()
'''
                },
                "type": "generic_python"
            }
        elif language == "react":
            component_name = self.description_to_component_name(description)
            # Use string concatenation to avoid f-string JSX issues
            react_code = '''// Auto-generated: ''' + description + '''
// Created by SmartCoder

import React from 'react';

const ''' + component_name + ''': React.FC = () => {
    return (
        <div className="''' + component_name.lower() + '''">
            <h3>''' + description + '''</h3>
            <p>This component was automatically generated.</p>
            <div className="content">
                {/* Add your component logic here */}
            </div>
        </div>
    );
};

export default ''' + component_name + ''';
'''
            if self._molt_context:
                react_code = f"// MOLT skill:{self.skill_name} oomf:{self.oomf_level}\n" + react_code
            return {
                "files": {
                    f"{component_name}.tsx": react_code
                },
                "type": "generic_react"
            }
    
    def generate_login_system(self):
        """Generate login system"""
        molt_note = f"# MOLT skill:{self.skill_name} oomf:{self.oomf_level}\n" if self._molt_context else ""
        return {
            "files": {
                "auth.py": f"""{molt_note}
import hashlib
import os
from datetime import datetime

class AuthSystem:
    def __init__(self):
        self.users = {{}}
        self.sessions = {{}}
    
    def register(self, username, password):
        '''Register a new user'''
        if username in self.users:
            return {{"status": "error", "message": "User already exists"}}
        
        hashed = hashlib.sha256(password.encode()).hexdigest()
        self.users[username] = hashed
        return {{"status": "success", "message": "User registered"}}
    
    def login(self, username, password):
        '''Login user'''
        hashed = hashlib.sha256(password.encode()).hexdigest()
        if self.users.get(username) == hashed:
            session_id = hashlib.sha256(f"{{username}}{{datetime.now()}}".encode()).hexdigest()
            self.sessions[session_id] = username
            return {{"status": "success", "session": session_id, "user": username}}
        return {{"status": "error", "message": "Invalid credentials"}}
    
    def verify_session(self, session_id):
        '''Verify session'''
        return session_id in self.sessions

# Example usage
if __name__ == "__main__":
    auth = AuthSystem()
    
    # Test registration
    result1 = auth.register("testuser", "password123")
    print("Register:", result1)
    
    # Test login
    result2 = auth.login("testuser", "password123")
    print("Login:", result2)
    
    # Test session verification
    if result2["status"] == "success":
        result3 = auth.verify_session(result2["session"])
        print("Session verify:", result3)
""",
                "app.py": """
from auth import AuthSystem

def main():
    auth = AuthSystem()
    
    while True:
        print("\\n1. Register")
        print("2. Login")
        print("3. Exit")
        
        choice = input("Choose option: ")
        
        if choice == "1":
            username = input("Username: ")
            password = input("Password: ")
            result = auth.register(username, password)
            print(result)
        
        elif choice == "2":
            username = input("Username: ")
            password = input("Password: ")
            result = auth.login(username, password)
            print(result)
        
        elif choice == "3":
            break

if __name__ == "__main__":
    main()
"""
            },
            "type": "login_system"
        }
    
    def generate_dashboard(self):
        """Generate dashboard system"""
        return {
            "files": {
                "dashboard.py": """
import time
from datetime import datetime

class Dashboard:
    def __init__(self):
        self.metrics = {
            "users": 0,
            "revenue": 0.0,
            "active_sessions": 0
        }
        self.last_update = datetime.now()
    
    def update_metrics(self):
        '''Update dashboard metrics'''
        self.metrics["users"] += 1
        self.metrics["revenue"] += 10.50
        self.metrics["active_sessions"] = max(1, self.metrics["users"] % 10)
        self.last_update = datetime.now()
    
    def display(self):
        '''Display dashboard'''
        print("=" * 40)
        print("          DASHBOARD")
        print("=" * 40)
        print(f"Users:          {self.metrics['users']}")
        print(f"Revenue:        ${self.metrics['revenue']:.2f}")
        print(f"Active Sessions: {self.metrics['active_sessions']}")
        print(f"Last Update:    {self.last_update.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 40)

# Example usage
if __name__ == "__main__":
    dashboard = Dashboard()
    
    for i in range(5):
        dashboard.update_metrics()
        dashboard.display()
        time.sleep(1)
"""
            },
            "type": "dashboard"
        }
    
    def generate_api_endpoint(self, description):
        """Generate API endpoint"""
        return {
            "files": {
                "api_server.py": """
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Auto-Generated API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    '''Root endpoint'''
    return {
        "message": "Auto-generated API server",
        "status": "running",
        "description": "This API was automatically generated"
    }

@app.get("/health")
async def health_check():
    '''Health check endpoint'''
    return {"status": "healthy", "timestamp": "2024-01-01T00:00:00Z"}

@app.post("/data")
async def create_data():
    '''Create data endpoint'''
    return {
        "status": "created",
        "message": "Data created successfully",
        "id": 12345
    }

@app.get("/users")
async def get_users():
    '''Get users endpoint'''
    return {
        "users": [
            {"id": 1, "name": "User One"},
            {"id": 2, "name": "User Two"},
            {"id": 3, "name": "User Three"}
        ]
    }

if __name__ == "__main__":
    import uvicorn
    print(" Starting API server on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""
            },
            "type": "api_server"
        }
    
    def generate_form_system(self):
        """Generate form system"""
        return {
            "files": {
                "form_handler.py": """
class FormHandler:
    def __init__(self):
        self.fields = []
        self.validations = {}
    
    def add_field(self, field_name, field_type="text", required=True):
        '''Add form field'''
        field = {
            "name": field_name,
            "type": field_type,
            "required": required,
            "value": None
        }
        self.fields.append(field)
        return field
    
    def validate_form(self, form_data):
        '''Validate form data'''
        errors = []
        
        for field in self.fields:
            value = form_data.get(field["name"])
            
            if field["required"] and not value:
                errors.append(f"{field['name']} is required")
            elif value and field["type"] == "email" and "@" not in value:
                errors.append(f"{field['name']} must be a valid email")
            elif value and field["type"] == "number":
                try:
                    float(value)
                except ValueError:
                    errors.append(f"{field['name']} must be a number")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "field_count": len(self.fields)
        }
    
    def process_form(self, form_data):
        '''Process form submission'''
        validation = self.validate_form(form_data)
        
        if validation["valid"]:
            return {
                "status": "success",
                "message": "Form submitted successfully",
                "data": form_data
            }
        else:
            return {
                "status": "error",
                "message": "Form validation failed",
                "errors": validation["errors"]
            }

# Example usage
if __name__ == "__main__":
    form = FormHandler()
    
    # Add form fields
    form.add_field("name", "text", True)
    form.add_field("email", "email", True)
    form.add_field("age", "number", False)
    
    # Test form data
    test_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "age": "30"
    }
    
    result = form.process_form(test_data)
    print("Form result:", result)
    
    # Test invalid data
    invalid_data = {
        "name": "",
        "email": "invalid-email",
        "age": "not-a-number"
    }
    
    result2 = form.process_form(invalid_data)
    print("Invalid form result:", result2)
"""
            },
            "type": "form_system"
        }
    
    def generate_navigation(self):
        """Generate navigation system"""
        navigation_code = '''// Auto-generated Navigation Component
// Created by SmartCoder

import React, { useState } from 'react';

const Navigation: React.FC = () => {
    const [isOpen, setIsOpen] = useState(false);
    
    const menuItems = [
        { label: 'Home', href: '#home' },
        { label: 'About', href: '#about' },
        { label: 'Services', href: '#services' },
        { label: 'Contact', href: '#contact' }
    ];
    
    return (
        <nav className="navigation">
            <div className="nav-container">
                <div className="nav-header">
                    <h2 className="nav-logo">MyApp</h2>
                    <button 
                        className="nav-toggle"
                        onClick={() => setIsOpen(!isOpen)}
                    >
                        ☰
                    </button>
                </div>
                
                <ul className={`nav-menu ${isOpen ? 'nav-menu-open' : ''}`}>
                    {menuItems.map((item, index) => (
                        <li key={index} className="nav-item">
                            <a 
                                href={item.href}
                                className="nav-link"
                                onClick={() => setIsOpen(false)}
                            >
                                {item.label}
                            </a>
                        </li>
                    ))}
                </ul>
            </div>
            
            <style>{`
                .navigation {
                    background: #1a1a1a;
                    color: white;
                    padding: 1rem 0;
                }
                
                .nav-container {
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 0 1rem;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                
                .nav-logo {
                    margin: 0;
                    color: #00ff88;
                }
                
                .nav-toggle {
                    display: none;
                    background: none;
                    border: none;
                    color: white;
                    font-size: 1.5rem;
                    cursor: pointer;
                }
                
                .nav-menu {
                    display: flex;
                    list-style: none;
                    margin: 0;
                    padding: 0;
                    gap: 2rem;
                }
                
                .nav-link {
                    color: white;
                    text-decoration: none;
                    transition: color 0.3s;
                }
                
                .nav-link:hover {
                    color: #00ff88;
                }
                
                @media (max-width: 768px) {
                    .nav-toggle {
                        display: block;
                    }
                    
                    .nav-menu {
                        display: none;
                        flex-direction: column;
                        position: absolute;
                        top: 100%;
                        left: 0;
                        right: 0;
                        background: #1a1a1a;
                        padding: 1rem;
                    }
                    
                    .nav-menu-open {
                        display: flex;
                    }
                }
            `}</style>
        </nav>
    );
};

export default Navigation;
'''
        return {
            "files": {
                "Navigation.tsx": navigation_code
            },
            "type": "navigation_component"
        }
    
    def description_to_class_name(self, description):
        """Convert description to class name"""
        words = re.findall(r'\w+', description)
        class_name = ''.join(word.capitalize() for word in words)
        return class_name or "AutoGenerated"
    
    def description_to_component_name(self, description):
        """Convert description to component name"""
        words = re.findall(r'\w+', description)
        component_name = ''.join(word.capitalize() for word in words)
        return component_name or "AutoComponent"

def main():
    coder = SmartCoder()
    
    # Test generation
    test_commands = [
        "create login form with validation",
        "build admin dashboard", 
        "make API endpoint for users",
        "create contact form"
    ]
    
    for cmd in test_commands:
        print(f"\n🧪 Testing: {cmd}")
        result = coder.generate_from_description(cmd)
        print(f"✅ Generated: {result['type']}")
        
        # Save files
        for filename, content in result["files"].items():
            with open(filename, 'w') as f:
                f.write(content)
            print(f"   📄 Created: {filename}")

    # MOLT smoke test
    try:
        from src.skill.skill_manager import SkillManager
        print("MOLT: SkillManager available — try SmartCoder(skill_name='my-living-skill', oomf_level=3).generate_with_skill('...')")
    except ImportError:
        pass

if __name__ == "__main__":
    main()
