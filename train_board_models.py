from __future__ import annotations

import json
from pathlib import Path

import emlearn
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

from greenhouse_anomaly_detection import ANOMALY_LABELS, FEATURE_COLUMNS
from project_paths import (
    ACTION_DATASET_FILE,
    ANOMALY_DATASET_FILE,
    BOARD_MODEL_METRICS_FILE,
    ROOT,
    ensure_parent_dir,
)


MANIFEST_FILE = ROOT / "board_model_manifest.py"
METRICS_FILE = BOARD_MODEL_METRICS_FILE

ACTION_TARGETS = [
    "heater_on",
    "cooling_fan_on",
    "ventilation_on",
    "mister_on",
]
ACTION_FEATURE_COLUMNS = [
    "temperature_x10",
    "humidity_x10",
    "co2_ppm",
]
ANOMALY_FEATURE_SCALES = {
    "temperature_c": 10,
    "prev_temperature_c": 10,
    "delta_1_temperature_c": 10,
    "delta_3_temperature_c": 10,
    "mean_6_temperature_c": 10,
    "std_6_temperature_c": 10,
    "range_6_temperature_c": 10,
    "unchanged_run_temperature_c": 1,
    "humidity_pct": 10,
    "prev_humidity_pct": 10,
    "delta_1_humidity_pct": 10,
    "delta_3_humidity_pct": 10,
    "mean_6_humidity_pct": 10,
    "std_6_humidity_pct": 10,
    "range_6_humidity_pct": 10,
    "unchanged_run_humidity_pct": 1,
    "co2_ppm": 1,
    "prev_co2_ppm": 1,
    "delta_1_co2_ppm": 1,
    "delta_3_co2_ppm": 1,
    "mean_6_co2_ppm": 1,
    "std_6_co2_ppm": 1,
    "range_6_co2_ppm": 1,
    "unchanged_run_co2_ppm": 1,
    "gap_seconds": 1,
    "gap_ratio": 100,
    "out_of_range_count": 1,
    "current_out_of_range": 1,
    "oscillation_score": 1,
    "multi_sensor_shift_score": 100,
    "dominant_sensor_shift_ratio": 100,
    "temperature_band_gap": 10,
    "humidity_band_gap": 10,
    "co2_band_gap": 1,
}


def scaled_action_frame(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "temperature_x10": (df["temperature_c"] * 10).round().astype(int),
            "humidity_x10": (df["humidity_pct"] * 10).round().astype(int),
            "co2_ppm": df["co2_ppm"].round().astype(int),
        }
    )


def scaled_anomaly_frame(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            column: (df[column] * ANOMALY_FEATURE_SCALES[column]).round().astype(int)
            for column in FEATURE_COLUMNS
        }
    )


def export_csv_model(model, path: Path) -> dict[str, int]:
    converted = emlearn.convert(model, method="loadable")
    converted.save(file=str(path), format="csv")
    nodes, roots, leaves = converted.forest_
    return {
        "filename": path.name,
        "max_trees": len(roots),
        "max_nodes": len(nodes),
        "max_leaves": len(leaves),
    }


def train_action_models() -> tuple[dict, dict]:
    df = pd.read_csv(ACTION_DATASET_FILE)
    X = scaled_action_frame(df)
    manifest_models = {}
    metrics = {}

    for target in ACTION_TARGETS:
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            df[target],
            test_size=0.2,
            random_state=50,
            shuffle=True,
            stratify=df[target],
        )
        model = RandomForestClassifier(
            n_estimators=16,
            max_depth=5,
            min_samples_leaf=2,
            random_state=50,
        )
        model.fit(X_train, y_train)
        predictions = model.predict(X_test)
        accuracy = accuracy_score(y_test, predictions)

        csv_path = ROOT / f"board_action_{target.replace('_on', '')}.csv"
        model_info = export_csv_model(model, csv_path)
        manifest_models[target] = {
            **model_info,
            "classes": [int(value) for value in model.classes_],
        }
        metrics[target] = {
            "accuracy": round(float(accuracy), 4),
        }

    return manifest_models, metrics


def train_anomaly_model() -> tuple[dict, dict]:
    df = pd.read_csv(ANOMALY_DATASET_FILE)
    X = scaled_anomaly_frame(df)
    y = df["anomaly_label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=50,
        shuffle=True,
        stratify=y,
    )
    model = RandomForestClassifier(
        n_estimators=40,
        max_depth=8,
        min_samples_leaf=3,
        random_state=50,
        class_weight="balanced_subsample",
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    report = classification_report(
        y_test,
        predictions,
        labels=ANOMALY_LABELS,
        output_dict=True,
        zero_division=0,
    )

    csv_path = ROOT / "board_anomaly_model.csv"
    model_info = export_csv_model(model, csv_path)
    manifest_model = {
        **model_info,
        "classes": [str(value) for value in model.classes_],
    }
    metrics = {
        "accuracy": round(float(accuracy), 4),
        "per_class": {
            label: {
                "precision": round(float(report.get(label, {}).get("precision", 0.0)), 4),
                "recall": round(float(report.get(label, {}).get("recall", 0.0)), 4),
                "f1_score": round(float(report.get(label, {}).get("f1-score", 0.0)), 4),
            }
            for label in ANOMALY_LABELS
        },
    }
    return manifest_model, metrics


def write_manifest(action_models: dict, anomaly_model: dict) -> None:
    lines = [
        "# Auto-generated by train_board_models.py",
        "WINDOW_SIZE = 6",
        "NOMINAL_SAMPLE_INTERVAL_S = 30",
        "",
        f"ACTION_FEATURE_COLUMNS = {ACTION_FEATURE_COLUMNS!r}",
        f"ANOMALY_FEATURE_COLUMNS = {FEATURE_COLUMNS!r}",
        f"ANOMALY_FEATURE_SCALES = {ANOMALY_FEATURE_SCALES!r}",
        f"ACTION_MODELS = {action_models!r}",
        f"ANOMALY_MODEL = {anomaly_model!r}",
        "",
    ]
    MANIFEST_FILE.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    action_models, action_metrics = train_action_models()
    anomaly_model, anomaly_metrics = train_anomaly_model()
    write_manifest(action_models, anomaly_model)

    metrics = {
        "action_models": action_metrics,
        "anomaly_model": anomaly_metrics,
    }
    ensure_parent_dir(METRICS_FILE)
    METRICS_FILE.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
