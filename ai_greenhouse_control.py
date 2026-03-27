from __future__ import annotations

import copy
import pickle
from dataclasses import asdict

import pandas as pd

from greenhouse_control import Thresholds, evaluate_greenhouse
from project_paths import ACTION_MODEL_FILE


MODEL_FILE = ACTION_MODEL_FILE
FEATURE_COLUMNS = ["temperature_c", "humidity_pct", "co2_ppm"]
TARGET_TO_ACTION = {
    "heater_on": {
        "key": "heater",
        "label": "Heater",
        "active_status": "heating",
        "active_reason": "AI predicts the greenhouse should warm up.",
        "idle_reason": "AI predicts heating is not needed right now.",
        "condition": "ai_heater_on",
        "condition_label": "AI heating recommendation",
        "recommended_action": "Heating",
    },
    "cooling_fan_on": {
        "key": "cooling_fan",
        "label": "Cooling Fan",
        "active_status": "cooling",
        "active_reason": "AI predicts the greenhouse should cool down.",
        "idle_reason": "AI predicts cooling is not needed right now.",
        "condition": "ai_cooling_on",
        "condition_label": "AI cooling recommendation",
        "recommended_action": "Cooling",
    },
    "ventilation_on": {
        "key": "ventilation",
        "label": "Ventilation",
        "active_status": "ventilating",
        "active_reason": "AI predicts fresh-air exchange should be active.",
        "idle_reason": "AI predicts ventilation is not needed right now.",
        "condition": "ai_ventilation_on",
        "condition_label": "AI ventilation recommendation",
        "recommended_action": "Ventilation",
    },
    "mister_on": {
        "key": "mister",
        "label": "Misting System",
        "active_status": "misting",
        "active_reason": "AI predicts moisture should be added.",
        "idle_reason": "AI predicts misting is not needed right now.",
        "condition": "ai_mister_on",
        "condition_label": "AI misting recommendation",
        "recommended_action": "Misting",
    },
}

_MODEL_BUNDLE = None


def load_action_model() -> dict | None:
    global _MODEL_BUNDLE
    if _MODEL_BUNDLE is not None:
        return _MODEL_BUNDLE

    if not MODEL_FILE.exists():
        return None

    with MODEL_FILE.open("rb") as handle:
        _MODEL_BUNDLE = pickle.load(handle)
    return _MODEL_BUNDLE


def clear_action_model_cache() -> None:
    global _MODEL_BUNDLE
    _MODEL_BUNDLE = None


def _positive_probability(estimator, features: pd.DataFrame) -> float:
    probabilities = estimator.predict_proba(features)[0]
    classes = list(estimator.classes_)
    if 1 in classes:
        return float(probabilities[classes.index(1)])
    return float(probabilities[-1])


def evaluate_greenhouse_ai(
    temperature_c: float,
    humidity_pct: float,
    co2_ppm: float,
    thresholds: Thresholds | None = None,
) -> dict:
    thresholds = thresholds or Thresholds()
    bundle = load_action_model()

    if bundle is None:
        fallback = evaluate_greenhouse(
            temperature_c=temperature_c,
            humidity_pct=humidity_pct,
            co2_ppm=co2_ppm,
            thresholds=thresholds,
        )
        fallback["decision_engine"] = "rule_fallback"
        fallback["model_available"] = False
        fallback["summary"] = "AI action model not found. " + fallback["summary"]
        return fallback

    feature_names = bundle.get("feature_names", FEATURE_COLUMNS)
    target_names = bundle["target_names"]
    model = bundle["model"]
    metrics = bundle.get("metrics", {})

    sensors = {
        "temperature_c": round(float(temperature_c), 1),
        "humidity_pct": round(float(humidity_pct), 1),
        "co2_ppm": int(round(float(co2_ppm))),
    }
    features = pd.DataFrame(
        [{name: float(sensors[name]) for name in feature_names}],
        columns=feature_names,
    )

    predictions = model.predict(features)[0]
    positive_probabilities = {
        target_names[index]: _positive_probability(model.estimators_[index], features)
        for index in range(len(target_names))
    }

    actions = []
    triggered_conditions = []

    for index, target_name in enumerate(target_names):
        spec = TARGET_TO_ACTION[target_name]
        active = bool(int(predictions[index]))
        positive_confidence = positive_probabilities[target_name]
        confidence = positive_confidence if active else 1.0 - positive_confidence
        status = spec["active_status"] if active else "idle"
        reason_base = spec["active_reason"] if active else spec["idle_reason"]
        action = {
            "key": spec["key"],
            "label": spec["label"],
            "status": status,
            "active": active,
            "reason": f"{reason_base} Confidence: {confidence:.0%}.",
            "confidence": round(confidence, 3),
            "positive_confidence": round(positive_confidence, 3),
            "source": "AI",
        }
        actions.append(action)

        if active:
            severity = "critical" if positive_confidence >= 0.85 else "warning"
            triggered_conditions.append(
                {
                    "condition": spec["condition"],
                    "label": spec["condition_label"],
                    "severity": severity,
                    "recommended_action": spec["recommended_action"],
                    "detail": (
                        f"AI confidence {positive_confidence:.0%} based on "
                        f"{sensors['temperature_c']:.1f} C, {sensors['humidity_pct']:.1f}%, "
                        f"and {sensors['co2_ppm']} ppm."
                    ),
                }
            )

    active_actions = [action for action in actions if action["active"]]
    if not active_actions:
        overall_state = "stable"
        summary = "AI action model predicts the greenhouse can remain idle."
    else:
        max_active_confidence = max(action["positive_confidence"] for action in active_actions)
        overall_state = "critical" if len(active_actions) >= 2 or max_active_confidence >= 0.85 else "warning"
        summary = "AI recommended virtual actions: " + ", ".join(action["status"] for action in active_actions) + "."

    result = {
        "sensors": sensors,
        "thresholds": asdict(thresholds),
        "overall_state": overall_state,
        "summary": summary,
        "triggered_conditions": triggered_conditions,
        "actions": actions,
        "decision_engine": "ai_action_model",
        "model_available": True,
        "model_metrics": copy.deepcopy(metrics),
    }
    return result
