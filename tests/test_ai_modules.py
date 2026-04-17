from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ai_greenhouse_control
import greenhouse_anomaly_detection
from ai_greenhouse_control import clear_action_model_cache, evaluate_greenhouse_ai
from greenhouse_anomaly_detection import (
    clear_anomaly_model_cache,
    evaluate_greenhouse_anomaly_ai,
    extract_anomaly_features,
)
from presentation_presets import get_presentation_preset


class AiModuleTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_action_model_cache()
        clear_anomaly_model_cache()

    def test_action_ai_uses_trained_model_bundle(self) -> None:
        result = evaluate_greenhouse_ai(24.0, 35.0, 900)
        self.assertEqual(result["decision_engine"], "ai_action_model")
        self.assertTrue(result["model_available"])
        self.assertTrue(any(action["active"] for action in result["actions"]))

    def test_action_ai_falls_back_to_rules_when_model_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_model = Path(temp_dir) / "missing.pkl"
            with mock.patch.object(ai_greenhouse_control, "MODEL_FILE", missing_model):
                clear_action_model_cache()
                result = evaluate_greenhouse_ai(16.0, 60.0, 900)
        self.assertEqual(result["decision_engine"], "rule_fallback")
        self.assertFalse(result["model_available"])

    def test_extract_anomaly_features_detects_out_of_range_values(self) -> None:
        samples = [
            {"temperature_c": 24.0, "humidity_pct": 60.0, "co2_ppm": 900, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 60.0, "co2_ppm": 900, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 60.0, "co2_ppm": 900, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 60.0, "co2_ppm": 900, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 60.0, "co2_ppm": 900, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 105.0, "co2_ppm": 900, "gap_seconds": 30},
        ]
        features = extract_anomaly_features(samples)
        self.assertGreater(features["out_of_range_count"], 0)
        self.assertGreater(features["current_out_of_range"], 0)

    def test_anomaly_ai_uses_warmup_logic_for_short_history(self) -> None:
        result = evaluate_greenhouse_anomaly_ai(
            [
                {"temperature_c": 24.0, "humidity_pct": 40.0, "co2_ppm": 900, "gap_seconds": 30},
                {"temperature_c": 24.2, "humidity_pct": 39.5, "co2_ppm": 905, "gap_seconds": 30},
            ]
        )
        self.assertEqual(result["decision_engine"], "ai_anomaly_warmup")
        self.assertFalse(result["history_ready"])

    def test_anomaly_ai_uses_trained_model_for_full_window(self) -> None:
        samples = get_presentation_preset("normal_baseline")["samples"]
        result = evaluate_greenhouse_anomaly_ai(samples)
        self.assertEqual(result["decision_engine"], "ai_anomaly_model")
        self.assertTrue(result["model_available"])
        self.assertTrue(result["history_ready"])


if __name__ == "__main__":
    unittest.main()
