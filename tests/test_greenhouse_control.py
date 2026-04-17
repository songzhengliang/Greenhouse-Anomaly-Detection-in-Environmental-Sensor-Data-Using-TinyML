from __future__ import annotations

import unittest

from greenhouse_control import Thresholds, evaluate_greenhouse


class GreenhouseControlTests(unittest.TestCase):
    def test_thresholds_from_mapping_fills_defaults(self) -> None:
        thresholds = Thresholds.from_mapping({"temperature_low": 16, "co2_high": 1500})
        self.assertEqual(thresholds.temperature_low, 16.0)
        self.assertEqual(thresholds.temperature_high, 30.0)
        self.assertEqual(thresholds.co2_high, 1500)

    def test_evaluate_greenhouse_stable_band_keeps_all_actions_idle(self) -> None:
        result = evaluate_greenhouse(24.0, 60.0, 900)
        self.assertEqual(result["overall_state"], "stable")
        self.assertIn("remain idle", result["summary"])
        self.assertFalse(any(action["active"] for action in result["actions"]))

    def test_evaluate_greenhouse_cold_and_dry_enables_heater_and_mister(self) -> None:
        result = evaluate_greenhouse(14.0, 30.0, 850)
        statuses = {action["key"]: action["status"] for action in result["actions"]}
        self.assertEqual(result["overall_state"], "critical")
        self.assertEqual(statuses["heater"], "heating")
        self.assertEqual(statuses["mister"], "misting")
        triggered = {item["condition"] for item in result["triggered_conditions"]}
        self.assertIn("temperature_low", triggered)
        self.assertIn("humidity_low", triggered)

    def test_evaluate_greenhouse_hot_and_high_co2_drives_ventilation(self) -> None:
        result = evaluate_greenhouse(34.5, 58.0, 1800)
        statuses = {action["key"]: action["status"] for action in result["actions"]}
        self.assertEqual(statuses["cooling_fan"], "cooling")
        self.assertEqual(statuses["ventilation"], "ventilating")
        self.assertIn("Recommended virtual actions", result["summary"])


if __name__ == "__main__":
    unittest.main()
