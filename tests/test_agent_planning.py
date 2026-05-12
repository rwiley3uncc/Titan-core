from __future__ import annotations

import unittest

from titan_core.agent import plan_agent_action


class AgentPlanningTests(unittest.TestCase):
    def test_read_sitrep_takes_precedence_over_weak_refresh_match(self) -> None:
        action = plan_agent_action("read sitrep")
        self.assertIsNotNone(action)
        self.assertEqual(action.name, "read_sitrep")

    def test_refresh_sitrep_still_maps_to_refresh_action(self) -> None:
        action = plan_agent_action("refresh sitrep")
        self.assertIsNotNone(action)
        self.assertEqual(action.name, "refresh_sitrep")


if __name__ == "__main__":
    unittest.main()
