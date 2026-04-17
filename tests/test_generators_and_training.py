from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sklearn.ensemble import RandomForestClassifier

import generate_greenhouse_action_dataset
import generate_greenhouse_anomaly_dataset
import project_paths
import train_anomaly_model
import train_board_models
import train_model


class GeneratorAndTrainingTests(unittest.TestCase):
    def test_ensure_parent_dir_creates_nested_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "nested" / "file.json"
            returned = project_paths.ensure_parent_dir(target)
            self.assertEqual(returned, target)
            self.assertTrue(target.parent.exists())

    def test_action_generator_produces_expected_columns(self) -> None:
        rows = generate_greenhouse_action_dataset.generate_rows(rows_per_scenario=2, seed=42)
        self.assertGreater(len(rows), 0)
        first = rows[0]
        self.assertIn("temperature_c", first)
        self.assertIn("heater_on", first)
        self.assertIn("scenario", first)

    def test_anomaly_generator_covers_declared_labels(self) -> None:
        rows = generate_greenhouse_anomaly_dataset.generate_rows(rows_per_scenario=1, seed=42)
        labels = {row["anomaly_label"] for row in rows}
        self.assertEqual(
            labels,
            set(generate_greenhouse_anomaly_dataset.BUILDERS.keys()),
        )

    def test_train_model_main_writes_outputs(self) -> None:
        rows = generate_greenhouse_action_dataset.generate_rows(rows_per_scenario=4, seed=42)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            dataset_file = temp_dir_path / "action.csv"
            model_file = temp_dir_path / "action.pkl"
            metrics_file = temp_dir_path / "action_metrics.json"
            generate_greenhouse_action_dataset.write_dataset(rows, dataset_file)

            original_rf = train_model.RandomForestClassifier
            with mock.patch.object(train_model, "DATASET_FILE", dataset_file), \
                mock.patch.object(train_model, "MODEL_FILE", model_file), \
                mock.patch.object(train_model, "METRICS_FILE", metrics_file), \
                mock.patch.object(
                    train_model,
                    "RandomForestClassifier",
                    side_effect=lambda **kwargs: original_rf(
                        n_estimators=20,
                        max_depth=5,
                        min_samples_leaf=1,
                        random_state=42,
                        n_jobs=1,
                    ),
                ):
                with contextlib.redirect_stdout(io.StringIO()):
                    train_model.main()

            self.assertTrue(model_file.exists())
            metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
            self.assertIn("exact_match_accuracy", metrics)

    def test_train_anomaly_model_main_writes_outputs(self) -> None:
        rows = generate_greenhouse_anomaly_dataset.generate_rows(rows_per_scenario=5, seed=42)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            dataset_file = temp_dir_path / "anomaly.csv"
            model_file = temp_dir_path / "anomaly.pkl"
            metrics_file = temp_dir_path / "anomaly_metrics.json"
            generate_greenhouse_anomaly_dataset.write_dataset(rows, dataset_file)

            original_rf = train_anomaly_model.RandomForestClassifier
            with mock.patch.object(train_anomaly_model, "DATASET_FILE", dataset_file), \
                mock.patch.object(train_anomaly_model, "MODEL_FILE", model_file), \
                mock.patch.object(train_anomaly_model, "METRICS_FILE", metrics_file), \
                mock.patch.object(
                    train_anomaly_model,
                    "RandomForestClassifier",
                    side_effect=lambda **kwargs: original_rf(
                        n_estimators=30,
                        max_depth=8,
                        min_samples_leaf=1,
                        random_state=42,
                        class_weight="balanced_subsample",
                        n_jobs=1,
                    ),
                ):
                with contextlib.redirect_stdout(io.StringIO()):
                    train_anomaly_model.main()

            self.assertTrue(model_file.exists())
            metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
            self.assertIn("accuracy", metrics)

    def test_train_board_models_main_writes_manifest_and_metrics(self) -> None:
        action_rows = generate_greenhouse_action_dataset.generate_rows(rows_per_scenario=4, seed=42)
        anomaly_rows = generate_greenhouse_anomaly_dataset.generate_rows(rows_per_scenario=5, seed=42)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            action_dataset = temp_dir_path / "action.csv"
            anomaly_dataset = temp_dir_path / "anomaly.csv"
            manifest_file = temp_dir_path / "board_model_manifest.py"
            metrics_file = temp_dir_path / "board_metrics.json"

            generate_greenhouse_action_dataset.write_dataset(action_rows, action_dataset)
            generate_greenhouse_anomaly_dataset.write_dataset(anomaly_rows, anomaly_dataset)

            original_rf = train_board_models.RandomForestClassifier

            def fake_export_csv_model(model, path: Path) -> dict[str, int]:
                path.write_text("stub-model", encoding="utf-8")
                return {
                    "filename": path.name,
                    "max_trees": 1,
                    "max_nodes": 1,
                    "max_leaves": 1,
                }

            with mock.patch.object(train_board_models, "ROOT", temp_dir_path), \
                mock.patch.object(train_board_models, "ACTION_DATASET_FILE", action_dataset), \
                mock.patch.object(train_board_models, "ANOMALY_DATASET_FILE", anomaly_dataset), \
                mock.patch.object(train_board_models, "MANIFEST_FILE", manifest_file), \
                mock.patch.object(train_board_models, "METRICS_FILE", metrics_file), \
                mock.patch.object(train_board_models, "export_csv_model", side_effect=fake_export_csv_model), \
                mock.patch.object(
                    train_board_models,
                    "RandomForestClassifier",
                    side_effect=lambda **kwargs: original_rf(
                        n_estimators=10,
                        max_depth=5,
                        min_samples_leaf=1,
                        random_state=42,
                        class_weight=kwargs.get("class_weight"),
                        n_jobs=1,
                    ),
                ):
                with contextlib.redirect_stdout(io.StringIO()):
                    train_board_models.main()

            self.assertTrue(manifest_file.exists())
            self.assertTrue(metrics_file.exists())
            self.assertIn("ACTION_MODELS", manifest_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
