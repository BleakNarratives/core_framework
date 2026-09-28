"""
Test Pipeline (test_pipeline.py)
--------------------------------
Verifies the end-to-end flow:
1. Concept -> GenEngine -> Whorl Skill Skeleton (YAML + Code)
2. Whorl Skill Skeleton -> ScoutLoader -> Loaded Skill
"""

import os
import shutil
import yaml
from pathlib import Path
from code_gen_engine import GenEngine
from whorl_provider import WhorlSkillPromptProvider
# Add src/ to path to allow importing ScoutLoader
import sys
sys.path.append(str(Path.cwd().parent.parent / "src"))
from skill.scout import ScoutLoader

def run_test():
    concept = "TestPipelineAnalyzer"
    safe_name = concept.lower().replace(" ", "_")
    skill_dir = Path("./skills") / safe_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Generate Skill Skeleton
    print(f"Generating skill for {concept}...")
    engine = GenEngine(prompt_provider=WhorlSkillPromptProvider())
    stub = engine.conceptualize_to_stub(concept)
    
    # Write manifest
    with open(skill_dir / "skill.yaml", "w") as f:
        yaml.dump(stub['manifest'], f)
    # Write entrypoint
    entrypoint_path = Path(stub['manifest']['entrypoint'])
    entrypoint_path.parent.mkdir(parents=True, exist_ok=True)
    with open(entrypoint_path, "w") as f:
        f.write(stub['entrypoint_code'])
    
    # 2. Load via ScoutLoader
    print(f"Loading skill {safe_name} via ScoutLoader...")
    loader = ScoutLoader(skill_root=Path("./skills"))
    manifest = loader.load_manifest(safe_name)
    
    print("✓ Successfully discovered and loaded manifest.")
    print(f"  Name: {manifest['name']}, Version: {manifest['version']}")
    
    # Cleanup
    shutil.rmtree("./skills")
    print("✓ Cleanup complete.")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"Pipeline test failed: {e}")
        sys.exit(1)
