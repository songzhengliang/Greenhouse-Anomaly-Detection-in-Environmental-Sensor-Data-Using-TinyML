from __future__ import annotations

import copy
import math
import pickle
import statistics
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
MODEL_FILE = ROOT / "anomaly_model.pkl"
WINDOW_SIZE = 6
NOMINAL_SAMPLE_INTERVAL_S = 30.0
SENSOR_FIELDS = ("temperature_c", "humidity_pct", "co2_ppm")
PLAUSIBLE_BOUNDS = {
    "temperature_c": (-5.0, 55.0),
    "humidity_pct": (0.0, 100.0),
    "co2_ppm": (250.0, 5000.0),
}
UNCHANGED_TOLERANCE = {
    "temperature_c": 0.15,
    "humidity_pct": 0.5,
    "co2_ppm": 12.0,
}
ANOMALY_LABELS = [
    "normal",
    "temperature_high",
    "temperature_low",
    "humidity_high",
    "humidity_low",
    "co2_high",
    "sensor_spike",
    "sensor_drift",
    "sensor_stuck",
    "sensor_dropout",
    "cross_variable_inconsistency",
    "out_of_range",
]
ANOMALY_METADATA = {
    "normal": {
        "display_label": "No anomaly",
        "severity": "stable",
        "summary": "AI anomaly watch sees no active anomaly in the current greenhouse window.",
        "description": "Recent readings look physically plausible and internally consistent.",
    },
    "temperature_high": {
        "display_label": "Temperature high",
        "severity": "warning",
        "summary": "AI anomaly watch flags sustained high temperature.",
        "description": "Temperature is staying above the expected greenhouse comfort band.",
    },
    "temperature_low": {
        "display_label": "Temperature low",
        "severity": "warning",
        "summary": "AI anomaly watch flags sustained low temperature.",
        "description": "Temperature is staying below the expected greenhouse comfort band.",
    },
    "humidity_high": {
        "display_label": "Humidity high",
        "severity": "warning",
        "summary": "AI anomaly watch flags sustained high humidity.",
        "description": "Humidity is staying above the expected greenhouse comfort band.",
    },
    "humidity_low": {
        "display_label": "Humidity low",
        "severity": "warning",
        "summary": "AI anomaly watch flags sustained low humidity.",
        "description": "Humidity is staying below the expected greenhouse comfort band.",
    },
    "co2_high": {
        "display_label": "CO2 high",
        "severity": "warning",
        "summary": "AI anomaly watch flags sustained high CO2 concentration.",
        "description": "CO2 is remaining above the normal operating range.",
    },
    "sensor_spike": {
        "display_label": "Sensor spike",
        "severity": "critical",
        "summary": "AI anomaly watch suspects a sudden sensor spike.",
        "description": "One variable changed too abruptly to look like normal greenhouse dynamics.",
    },
    "sensor_drift": {
        "display_label": "Sensor drift",
        "severity": "critical",
        "summary": "AI anomaly watch suspects gradual sensor drift.",
        "description": "One variable is moving persistently away from the recent baseline.",
    },
    "sensor_stuck": {
        "display_label": "Sensor stuck",
        "severity": "critical",
        "summary": "AI anomaly watch suspects a stuck sensor.",
        "description": "A sensor is repeating nearly the same value across multiple updates.",
    },
    "sensor_dropout": {
        "display_label": "Sensor dropout",
        "severity": "critical",
        "summary": "AI anomaly watch suspects a telemetry or sensor dropout.",
        "description": "The update gap is much larger than the expected sampling interval.",
    },
    "cross_variable_inconsistency": {
        "display_label": "Cross-variable inconsistency",
        "severity": "critical",
        "summary": "AI anomaly watch sees conflicting behaviour between greenhouse variables.",
        "description": "The joint sensor pattern does not match normal greenhouse relationships.",
    },
    "out_of_range": {
        "display_label": "Out of range",
        "severity": "critical",
        "summary": "AI anomaly watch sees values outside plausible sensor bounds.",
        "description": "At least one variable is outside the physically plausible range.",
    },
}

FEATURE_COLUMNS = [
    "temperature_c",
    "prev_temperature_c",
    "delta_1_temperature_c",
    "delta_3_temperature_c",
    "mean_6_temperature_c",
    "std_6_temperature_c",
    "range_6_temperature_c",
    "unchanged_run_temperature_c",
    "humidity_pct",
    "prev_humidity_pct",
    "delta_1_humidity_pct",
    "delta_3_humidity_pct",
    "mean_6_humidity_pct",
    "std_6_humidity_pct",
    "range_6_humidity_pct",
    "unchanged_run_humidity_pct",
    "co2_ppm",
    "prev_co2_ppm",
    "delta_1_co2_ppm",
    "delta_3_co2_ppm",
    "mean_6_co2_ppm",
    "std_6_co2_ppm",
    "range_6_co2_ppm",
    "unchanged_run_co2_ppm",
    "gap_seconds",
    "gap_ratio",
    "out_of_range_count",
    "current_out_of_range",
    "oscillation_score",
    "multi_sensor_shift_score",
    "dominant_sensor_shift_ratio",
    "temperature_band_gap",
    "humidity_band_gap",
    "co2_band_gap",
]

_MODEL_BUNDLE = None


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalized_sample(sample: dict) -> dict:
    timestamp = _safe_float(sample.get("timestamp"), 0.0)
    gap_seconds = _safe_float(sample.get("gap_seconds"), NOMINAL_SAMPLE_INTERVAL_S)
    return {
        "temperature_c": round(_safe_float(sample.get("temperature_c"), 24.0), 4),
        "humidity_pct": round(_safe_float(sample.get("humidity_pct"), 60.0), 4),
        "co2_ppm": round(_safe_float(sample.get("co2_ppm"), 900.0), 4),
        "timestamp": timestamp,
        "gap_seconds": max(1.0, gap_seconds),
    }


def _padded_window(samples: list[dict], window_size: int = WINDOW_SIZE) -> list[dict]:
    if not samples:
        samples = [
            {
                "temperature_c": 24.0,
                "humidity_pct": 60.0,
                "co2_ppm": 900.0,
                "timestamp": 0.0,
                "gap_seconds": NOMINAL_SAMPLE_INTERVAL_S,
            }
        ]

    window = [_normalized_sample(sample) for sample in samples][-window_size:]
    while len(window) < window_size:
        window.insert(0, copy.deepcopy(window[0]))
    return window


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _sign_changes(values: list[float], tolerance: float) -> int:
    changes = 0
    previous_sign = 0
    for left, right in zip(values[:-1], values[1:]):
        delta = right - left
        sign = 0 if abs(delta) <= tolerance else _sign(delta)
        if sign != 0 and previous_sign != 0 and sign != previous_sign:
            changes += 1
        if sign != 0:
            previous_sign = sign
    return changes


def _unchanged_run(values: list[float], tolerance: float) -> int:
    run = 1
    last_value = values[-1]
    for value in reversed(values[:-1]):
        if abs(value - last_value) <= tolerance:
            run += 1
        else:
            break
    return run


def _out_of_range(value: float, field: str) -> bool:
    low, high = PLAUSIBLE_BOUNDS[field]
    return value < low or value > high


def extract_anomaly_features(
    samples: list[dict],
    current_gap_seconds: float | None = None,
) -> dict[str, float]:
    window = _padded_window(samples)
    features: dict[str, float] = {}
    oscillation_score = 0
    multi_sensor_shift_score = 0.0
    normalized_shifts = []

    scale = {
        "temperature_c": 5.0,
        "humidity_pct": 18.0,
        "co2_ppm": 650.0,
    }

    for field in SENSOR_FIELDS:
        values = [sample[field] for sample in window]
        previous = values[-2]
        earlier = values[-4]
        current = values[-1]

        features[field] = round(current, 4)
        features[f"prev_{field}"] = round(previous, 4)
        features[f"delta_1_{field}"] = round(current - previous, 4)
        features[f"delta_3_{field}"] = round(current - earlier, 4)
        features[f"mean_6_{field}"] = round(statistics.fmean(values), 4)
        features[f"std_6_{field}"] = round(statistics.pstdev(values), 4)
        features[f"range_6_{field}"] = round(max(values) - min(values), 4)
        features[f"unchanged_run_{field}"] = float(
            _unchanged_run(values, UNCHANGED_TOLERANCE[field])
        )
        oscillation_score += _sign_changes(values, UNCHANGED_TOLERANCE[field])
        normalized_shift = abs(current - earlier) / scale[field]
        normalized_shifts.append(normalized_shift)
        multi_sensor_shift_score += normalized_shift

    gap_seconds = current_gap_seconds
    if gap_seconds is None:
        gap_seconds = window[-1]["gap_seconds"]

    out_of_range_count = sum(
        1
        for sample in window
        for field in SENSOR_FIELDS
        if _out_of_range(sample[field], field)
    )
    current_out_of_range = sum(
        1 for field in SENSOR_FIELDS if _out_of_range(window[-1][field], field)
    )

    features["gap_seconds"] = round(float(max(1.0, gap_seconds)), 4)
    features["gap_ratio"] = round(features["gap_seconds"] / NOMINAL_SAMPLE_INTERVAL_S, 4)
    features["out_of_range_count"] = float(out_of_range_count)
    features["current_out_of_range"] = float(current_out_of_range)
    features["oscillation_score"] = float(oscillation_score)
    features["multi_sensor_shift_score"] = round(multi_sensor_shift_score, 4)
    features["dominant_sensor_shift_ratio"] = round(
        max(normalized_shifts) / max(0.001, sum(normalized_shifts)),
        4,
    )
    features["temperature_band_gap"] = round(
        max(18.0 - features["temperature_c"], features["temperature_c"] - 30.0, 0.0),
        4,
    )
    features["humidity_band_gap"] = round(
        max(45.0 - features["humidity_pct"], features["humidity_pct"] - 75.0, 0.0),
        4,
    )
    features["co2_band_gap"] = round(max(features["co2_ppm"] - 1200.0, 0.0), 4)
    return features


def default_anomaly_payload() -> dict:
    meta = ANOMALY_METADATA["normal"]
    return {
        "label": "normal",
        "display_label": meta["display_label"],
        "severity": meta["severity"],
        "summary": meta["summary"],
        "detail": meta["description"],
        "confidence": 1.0,
        "anomaly_score": 0.0,
        "decision_engine": "ai_anomaly_model",
        "model_available": False,
        "history_ready": False,
        "window_size": WINDOW_SIZE,
        "top_predictions": [
            {
                "label": "normal",
                "display_label": meta["display_label"],
                "confidence": 1.0,
            }
        ],
    }


def load_anomaly_model() -> dict | None:
    global _MODEL_BUNDLE
    if _MODEL_BUNDLE is not None:
        return _MODEL_BUNDLE
    if not MODEL_FILE.exists():
        return None

    with MODEL_FILE.open("rb") as handle:
        _MODEL_BUNDLE = pickle.load(handle)
    return _MODEL_BUNDLE


def clear_anomaly_model_cache() -> None:
    global _MODEL_BUNDLE
    _MODEL_BUNDLE = None


def _fallback_anomaly_from_features(
    features: dict[str, float],
    history_ready: bool,
) -> dict:
    label = "normal"

    if features["current_out_of_range"] > 0:
        label = "out_of_range"
    elif features["gap_seconds"] >= 90.0:
        label = "sensor_dropout"
    elif (
        features["unchanged_run_temperature_c"] >= 4
        or features["unchanged_run_humidity_pct"] >= 4
        or features["unchanged_run_co2_ppm"] >= 4
    ):
        label = "sensor_stuck"
    elif (
        abs(features["delta_1_temperature_c"]) >= 6.0
        or abs(features["delta_1_humidity_pct"]) >= 18.0
        or abs(features["delta_1_co2_ppm"]) >= 700.0
    ):
        label = "sensor_spike"
    elif features["temperature_c"] > 30.0:
        label = "temperature_high"
    elif features["temperature_c"] < 18.0:
        label = "temperature_low"
    elif features["humidity_pct"] > 75.0:
        label = "humidity_high"
    elif features["humidity_pct"] < 45.0:
        label = "humidity_low"
    elif features["co2_ppm"] > 1200.0:
        label = "co2_high"

    meta = ANOMALY_METADATA[label]
    anomaly_score = 0.0 if label == "normal" else 0.82
    return {
        "label": label,
        "display_label": meta["display_label"],
        "severity": meta["severity"],
        "summary": meta["summary"],
        "detail": meta["description"],
        "confidence": 1.0 - anomaly_score if label == "normal" else anomaly_score,
        "anomaly_score": anomaly_score,
        "decision_engine": "rule_fallback",
        "model_available": False,
        "history_ready": history_ready,
        "window_size": WINDOW_SIZE,
        "top_predictions": [
            {
                "label": label,
                "display_label": meta["display_label"],
                "confidence": 1.0 - anomaly_score if label == "normal" else anomaly_score,
            }
        ],
    }


def _warmup_anomaly_from_features(features: dict[str, float], sample_count: int) -> dict:
    label = "normal"
    if features["current_out_of_range"] > 0:
        label = "out_of_range"
    elif features["gap_seconds"] >= 90.0:
        label = "sensor_dropout"
    elif features["temperature_c"] > 30.0:
        label = "temperature_high"
    elif features["temperature_c"] < 18.0:
        label = "temperature_low"
    elif features["humidity_pct"] > 75.0:
        label = "humidity_high"
    elif features["humidity_pct"] < 45.0:
        label = "humidity_low"
    elif features["co2_ppm"] > 1200.0:
        label = "co2_high"

    meta = ANOMALY_METADATA[label]
    if label == "normal":
        summary = "AI anomaly watch is collecting more history before checking time-based faults."
        detail = (
            "Only snapshot-safe anomaly checks are active until the rolling window fills with "
            f"real samples ({sample_count}/{WINDOW_SIZE})."
        )
        confidence = 1.0
        anomaly_score = 0.0
    else:
        summary = meta["summary"]
        detail = (
            f"Early window mode ({sample_count}/{WINDOW_SIZE} samples). "
            + meta["description"]
        )
        confidence = 0.82
        anomaly_score = 0.82

    return {
        "label": label,
        "display_label": meta["display_label"],
        "severity": meta["severity"],
        "summary": summary,
        "detail": detail,
        "confidence": confidence,
        "anomaly_score": anomaly_score,
        "decision_engine": "ai_anomaly_warmup",
        "model_available": True,
        "history_ready": False,
        "window_size": WINDOW_SIZE,
        "top_predictions": [
            {
                "label": label,
                "display_label": meta["display_label"],
                "confidence": confidence,
            }
        ],
    }


def _environmental_label_from_features(features: dict[str, float]) -> str | None:
    if features["current_out_of_range"] > 0:
        return "out_of_range"
    if features["temperature_c"] > 30.0:
        return "temperature_high"
    if features["temperature_c"] < 18.0:
        return "temperature_low"
    if features["humidity_pct"] > 75.0:
        return "humidity_high"
    if features["humidity_pct"] < 45.0:
        return "humidity_low"
    if features["co2_ppm"] > 1200.0:
        return "co2_high"
    return None


def evaluate_greenhouse_anomaly_ai(
    samples: list[dict],
    current_gap_seconds: float | None = None,
) -> dict:
    sample_count = len(samples)
    history_ready = sample_count >= WINDOW_SIZE
    features = extract_anomaly_features(samples, current_gap_seconds=current_gap_seconds)
    if not history_ready:
        return _warmup_anomaly_from_features(features, sample_count)

    bundle = load_anomaly_model()
    if bundle is None:
        return _fallback_anomaly_from_features(features, history_ready)

    feature_names = bundle.get("feature_names", FEATURE_COLUMNS)
    model = bundle["model"]
    class_names = list(bundle.get("class_names", ANOMALY_LABELS))
    frame = pd.DataFrame([features], columns=feature_names)
    predicted_label = str(model.predict(frame)[0])
    probabilities = model.predict_proba(frame)[0]
    probability_by_label = {
        str(label): float(probability)
        for label, probability in zip(class_names, probabilities)
    }
    normal_probability = probability_by_label.get("normal", 0.0)
    selected_confidence = probability_by_label.get(predicted_label, 0.0)

    fallback_label = _environmental_label_from_features(features)
    if (
        fallback_label is not None
        and predicted_label in {"sensor_spike", "sensor_drift", "sensor_stuck", "cross_variable_inconsistency"}
        and selected_confidence < 0.6
    ):
        predicted_label = fallback_label
        selected_confidence = max(probability_by_label.get(fallback_label, 0.0), 0.72)

    meta = ANOMALY_METADATA.get(predicted_label, ANOMALY_METADATA["normal"])
    top_predictions = sorted(
        probability_by_label.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:3]
    if predicted_label not in [label for label, _ in top_predictions]:
        top_predictions.insert(0, (predicted_label, selected_confidence))
        top_predictions = top_predictions[:3]
    top_payload = [
        {
            "label": label,
            "display_label": ANOMALY_METADATA.get(label, ANOMALY_METADATA["normal"])["display_label"],
            "confidence": round(
                selected_confidence if label == predicted_label else probability,
                3,
            ),
        }
        for label, probability in top_predictions
    ]

    current = _padded_window(samples)[-1]
    detail = (
        f"Window end: {current['temperature_c']:.1f} C, {current['humidity_pct']:.1f}%, "
        f"{int(round(current['co2_ppm']))} ppm. Gap {features['gap_seconds']:.0f} s."
    )
    if not history_ready:
        detail += " History is still warming up, so the model is working with padded context."

    return {
        "label": predicted_label,
        "display_label": meta["display_label"],
        "severity": meta["severity"],
        "summary": meta["summary"],
        "detail": detail + " " + meta["description"],
        "confidence": round(selected_confidence, 3),
        "anomaly_score": round(max(0.0, 1.0 - normal_probability), 3),
        "decision_engine": "ai_anomaly_model",
        "model_available": True,
        "history_ready": history_ready,
        "window_size": WINDOW_SIZE,
        "top_predictions": top_payload,
    }
