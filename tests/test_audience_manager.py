
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

class TestAudienceManager(unittest.TestCase):
    def setUp(self):
        self.data_path = "data/test_audience.json"
        self.manager = AudienceManager(data_path=self.data_path)

    def tearDown(self):
        if os.path.exists(self.data_path):
            os.remove(self.data_path)

    def test_set_niche(self):
        self.manager.set_niche("Software Development")
        self.assertEqual(self.manager.audience_data["niche"], "Software Development")

    def test_add_insight(self):
        self.manager.add_insight("problems_frustrations", "Long build times")
        self.assertIn("Long build times", self.manager.audience_data["audience"]["problems_frustrations"])

if __name__ == '__main__':
    unittest.main()
