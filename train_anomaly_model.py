from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

from greenhouse_anomaly_detection import ANOMALY_LABELS, FEATURE_COLUMNS


DATASET_FILE = Path("greenhouse_anomaly_dataset.csv")
MODEL_FILE = Path("anomaly_model.pkl")
METRICS_FILE = Path("anomaly_model_metrics.json")


def main() -> None:
    df = pd.read_csv(DATASET_FILE)
    X = df[FEATURE_COLUMNS]
    y = df["anomaly_label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        shuffle=True,
        stratify=y,
    )

    model = RandomForestClassifier(
        n_estimators=220,
        max_depth=14,
        min_samples_leaf=2,
        random_state=42,
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

    metrics = {
        "dataset": str(DATASET_FILE),
        "rows": int(len(df)),
        "feature_columns": FEATURE_COLUMNS,
        "class_labels": ANOMALY_LABELS,
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

    bundle = {
        "model": model,
        "feature_names": FEATURE_COLUMNS,
        "class_names": list(model.classes_),
        "metrics": metrics,
    }

    with MODEL_FILE.open("wb") as handle:
        pickle.dump(bundle, handle)

    with METRICS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)

    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
