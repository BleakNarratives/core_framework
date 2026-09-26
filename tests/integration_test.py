
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: test
# DEPS: json,os,src,unittest
# ROLE: unspecified
# AUTHOR: Bleak
# SESSION: 2026-09-11
# TIER: 4
# [/DNA_TAG]

import unittest
import os
import json
from src.audience.manager import AudienceManager
from src.discovery.engine import DiscoveryEngine
from src.creation.engine import CreationEngine
from src.evaluation.engine import Evaluator

class TestFullEnginePipeline(unittest.TestCase):
    def setUp(self):
        self.data_path = "data/integration_test.json"
        self.manager = AudienceManager(data_path=self.data_path)
        self.discovery = DiscoveryEngine(self.manager)
        self.creation = CreationEngine()
        self.evaluator = Evaluator()

    def tearDown(self):
        if os.path.exists(self.data_path):
            os.remove(self.data_path)

    def test_full_pipeline(self):
        # 1. Audience
        self.manager.set_niche("Content Strategy")
        self.manager.add_insight("problems_frustrations", "No clear content plan")
        
        # 2. Discovery
        # discover_topics() has two channels: insight-derived topics, and a MOLT
        # channel that surfaces living SKILL.md trees from the working
        # directory. The second depends on what happens to be checked out, so
        # asserting a total here made the test fail whenever a skill with
        # scout.depth >= 3 existed. Assert on the insight-derived channel --
        # that is the guarantee this pipeline is actually about.
        topics = self.discovery.discover_topics()
        solution_topics = [t for t in topics if t["type"] == "Solution"]
        self.assertEqual(len(solution_topics), 1)
        topic = solution_topics[0]['topic']
        
        # 3. Creation
        plan = self.creation.generate_content_plan(topic, "blog_post")
        self.assertEqual(plan['topic'], "How to solve No clear content plan")
        
        # 4. Evaluation
        # Simulate metrics for the plan
        metrics = {"clarity": 0.9, "engagement": 0.8}
        score = self.evaluator.evaluate(plan, metrics)
        
        self.assertGreater(score, 0.7)

if __name__ == '__main__':
    unittest.main()
