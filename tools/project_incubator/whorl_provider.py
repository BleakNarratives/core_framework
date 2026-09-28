"""
Whorl Skill Prompt Provider
Maps high-level concepts into Whorl-compliant manifest and entrypoint stubs.
"""

from typing import Dict, Any

class WhorlSkillPromptProvider:
    """Generates Whorl-compliant skill manifests and code skeletons."""
    
    def get_stub_prompt(self, concept: str) -> Dict[str, Any]:
        safe_name = concept.lower().replace(" ", "_")
        
        # Manifest: skill.yaml structure
        manifest = {
            "name": safe_name,
            "version": "0.1.0",
            "description": f"Auto-generated skill for {concept}",
            "runtime": "python3",
            "entrypoint": f"skills/{safe_name}/main.py",
            "dependencies": [],
            "policy": {
                "allow_mutations": False,
                "max_runtime_seconds": 30,
                "allowed_filesystem_paths": [f"data/{safe_name}/"]
            }
        }
        
        # Entrypoint structure
        code = f"""
def run(args: dict):
    \"\"\"Entry point for {safe_name}\"\"\"
    print(f"Executing {safe_name}...")
    return {{"status": "success"}}
"""
        return {
            "name": safe_name,
            "manifest": manifest,
            "entrypoint_code": code
        }
