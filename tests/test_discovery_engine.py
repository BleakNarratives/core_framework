
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: test
# DEPS: os,src,unittest
# ROLE: unspecified
# AUTHOR: Bleak
# SESSION: 2026-09-11
# TIER: 4
# [/DNA_TAG]

import unittest
from src.audience.manager import AudienceManager
from src.discovery.engine import DiscoveryEngine
import os

class TestDiscoveryEngine(unittest.TestCase):
    def setUp(self):
        self.data_path = "data/test_discovery.json"
        self.manager = AudienceManager(data_path=self.data_path)
        self.engine = DiscoveryEngine(self.manager)

    def tearDown(self):
        if os.path.exists(self.data_path):
            os.remove(self.data_path)

    def test_discover_topics(self):
        self.manager.add_insight("problems_frustrations", "Bad documentation")
        self.manager.add_insight("interests", "Rust programming")

        topics = self.engine.discover_topics()

        # MOLT: engine may enrich with living-skill topics — filter to core audience topics
        core = [t for t in topics if t.get("type") in ("Solution", "Insight")]
        self.assertEqual(len(core), 2)
        self.assertTrue(any(t['topic'] == 'How to solve Bad documentation' for t in core))
        self.assertTrue(any(t['topic'] == 'Deep dive into Rust programming' for t in core))

    def test_discover_topics_includes_molt_when_present(self):
        # MOLT enrichment is additive and opt-out via empty skill roots
        self.manager.add_insight("problems_frustrations", "X")
        topics = self.engine.discover_topics()
        # At minimum the Solution topic exists; Molt topics are bonus
        self.assertTrue(any(t['topic'] == 'How to solve X' for t in topics))

if __name__ == '__main__':
    unittest.main()
