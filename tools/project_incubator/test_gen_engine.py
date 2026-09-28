import unittest
from pathlib import Path
from code_gen_engine import GenEngine, WhorlSkillProvider
import shutil

class TestGenEngine(unittest.TestCase):
    def setUp(self):
        self.engine = GenEngine(provider=WhorlSkillProvider())
        self.output_root = Path("./test_skills")
        self.output_root.mkdir(exist_ok=True)

    def test_generate_functional_skill(self):
        concept = "DataAnalyzer"
        skill_dir = self.engine.generate_skill(concept, self.output_root)
        
        # Verify structure
        self.assertTrue((skill_dir / "skill.yaml").exists())
        self.assertTrue((skill_dir / "main.py").exists())
        
        # Verify content
        with open(skill_dir / "skill.yaml", "r") as f:
            manifest = f.read()
            self.assertIn("version: 1.0.0", manifest)
        
        main_py = (skill_dir / "main.py").read_text()
        self.assertIn("logging.getLogger", main_py)

    def tearDown(self):
        shutil.rmtree(self.output_root)

if __name__ == "__main__":
    unittest.main()
