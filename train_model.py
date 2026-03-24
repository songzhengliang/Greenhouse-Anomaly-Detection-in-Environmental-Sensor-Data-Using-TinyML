from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.multioutput import MultiOutputClassifier


DATASET_FILE = Path("greenhouse_action_control_dataset.csv")
MODEL_FILE = Path("action_model.pkl")
METRICS_FILE = Path("action_model_metrics.json")
FEATURE_COLUMNS = ["temperature_c", "humidity_pct", "co2_ppm"]
TARGET_COLUMNS = ["heater_on", "cooling_fan_on", "ventilation_on", "mister_on"]


def main() -> None:
    df = pd.read_csv(DATASET_FILE)
    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMNS]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        shuffle=True,
    )

    base_estimator = RandomForestClassifier(
        n_estimators=140,
        max_depth=8,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    model = MultiOutputClassifier(base_estimator)
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    exact_match_accuracy = accuracy_score(y_test, predictions)
    per_action_accuracy = {
        target_name: accuracy_score(y_test[target_name], predictions[:, index])
        for index, target_name in enumerate(TARGET_COLUMNS)
    }

    metrics = {
        "dataset": str(DATASET_FILE),
        "rows": int(len(df)),
        "feature_columns": FEATURE_COLUMNS,
        "target_columns": TARGET_COLUMNS,
        "exact_match_accuracy": round(float(exact_match_accuracy), 4),
        "per_action_accuracy": {
            key: round(float(value), 4)
            for key, value in per_action_accuracy.items()
        },
    }

    bundle = {
        "model": model,
        "feature_names": FEATURE_COLUMNS,
        "target_names": TARGET_COLUMNS,
        "metrics": metrics,
    }

    with MODEL_FILE.open("wb") as handle:
        pickle.dump(bundle, handle)

    with METRICS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)

    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
