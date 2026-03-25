import array
import gc
import math

import emlearn_trees

import board_model_manifest as manifest


WINDOW_SIZE = int(manifest.WINDOW_SIZE)
NOMINAL_SAMPLE_INTERVAL_S = float(manifest.NOMINAL_SAMPLE_INTERVAL_S)
ACTION_FEATURE_COLUMNS = tuple(manifest.ACTION_FEATURE_COLUMNS)
ANOMALY_FEATURE_COLUMNS = tuple(manifest.ANOMALY_FEATURE_COLUMNS)
ANOMALY_FEATURE_SCALES = dict(manifest.ANOMALY_FEATURE_SCALES)
ACTION_MODELS = dict(manifest.ACTION_MODELS)
ANOMALY_MODEL = dict(manifest.ANOMALY_MODEL)
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
ACTION_SPECS = {
    "heater_on": {
        "key": "heater",
        "label": "Heater",
        "active_status": "heating",
        "active_reason": "On-device AI predicts the greenhouse should warm up.",
        "idle_reason": "On-device AI predicts heating is not needed right now.",
        "condition": "ai_heater_on",
        "condition_label": "AI heating recommendation",
        "recommended_action": "Heating",
    },
    "cooling_fan_on": {
        "key": "cooling_fan",
        "label": "Cooling Fan",
        "active_status": "cooling",
        "active_reason": "On-device AI predicts the greenhouse should cool down.",
        "idle_reason": "On-device AI predicts cooling is not needed right now.",
        "condition": "ai_cooling_on",
        "condition_label": "AI cooling recommendation",
        "recommended_action": "Cooling",
    },
    "ventilation_on": {
        "key": "ventilation",
        "label": "Ventilation",
        "active_status": "ventilating",
        "active_reason": "On-device AI predicts fresh-air exchange should be active.",
        "idle_reason": "On-device AI predicts ventilation is not needed right now.",
        "condition": "ai_ventilation_on",
        "condition_label": "AI ventilation recommendation",
        "recommended_action": "Ventilation",
    },
    "mister_on": {
        "key": "mister",
        "label": "Misting System",
        "active_status": "misting",
        "active_reason": "On-device AI predicts moisture should be added.",
        "idle_reason": "On-device AI predicts misting is not needed right now.",
        "condition": "ai_mister_on",
        "condition_label": "AI misting recommendation",
        "recommended_action": "Misting",
    },
}
ANOMALY_METADATA = {
    "normal": {
        "display_label": "No anomaly",
        "severity": "stable",
        "summary": "On-device AI anomaly watch sees no active anomaly in the current greenhouse window.",
        "description": "Recent readings look physically plausible and internally consistent.",
    },
    "temperature_high": {
        "display_label": "Temperature high",
        "severity": "warning",
        "summary": "On-device AI anomaly watch flags sustained high temperature.",
        "description": "Temperature is staying above the expected greenhouse comfort band.",
    },
    "temperature_low": {
        "display_label": "Temperature low",
        "severity": "warning",
        "summary": "On-device AI anomaly watch flags sustained low temperature.",
        "description": "Temperature is staying below the expected greenhouse comfort band.",
    },
    "humidity_high": {
        "display_label": "Humidity high",
        "severity": "warning",
        "summary": "On-device AI anomaly watch flags sustained high humidity.",
        "description": "Humidity is staying above the expected greenhouse comfort band.",
    },
    "humidity_low": {
        "display_label": "Humidity low",
        "severity": "warning",
        "summary": "On-device AI anomaly watch flags sustained low humidity.",
        "description": "Humidity is staying below the expected greenhouse comfort band.",
    },
    "co2_high": {
        "display_label": "CO2 high",
        "severity": "warning",
        "summary": "On-device AI anomaly watch flags sustained high CO2 concentration.",
        "description": "CO2 is remaining above the normal operating range.",
    },
    "sensor_spike": {
        "display_label": "Sensor spike",
        "severity": "critical",
        "summary": "On-device AI anomaly watch suspects a sudden sensor spike.",
        "description": "One variable changed too abruptly to look like normal greenhouse dynamics.",
    },
    "sensor_drift": {
        "display_label": "Sensor drift",
        "severity": "critical",
        "summary": "On-device AI anomaly watch suspects gradual sensor drift.",
        "description": "One variable is moving persistently away from the recent baseline.",
    },
    "sensor_stuck": {
        "display_label": "Sensor stuck",
        "severity": "critical",
        "summary": "On-device AI anomaly watch suspects a stuck sensor.",
        "description": "A sensor is repeating nearly the same value across multiple updates.",
    },
    "sensor_dropout": {
        "display_label": "Sensor dropout",
        "severity": "critical",
        "summary": "On-device AI anomaly watch suspects a telemetry or sensor dropout.",
        "description": "The update gap is much larger than the expected sampling interval.",
    },
    "cross_variable_inconsistency": {
        "display_label": "Cross-variable inconsistency",
        "severity": "critical",
        "summary": "On-device AI anomaly watch sees conflicting behaviour between greenhouse variables.",
        "description": "The joint sensor pattern does not match normal greenhouse relationships.",
    },
    "out_of_range": {
        "display_label": "Out of range",
        "severity": "critical",
        "summary": "On-device AI anomaly watch sees values outside plausible sensor bounds.",
        "description": "At least one variable is outside the physically plausible range.",
    },
}
STATE_RANK = {"stable": 0, "warning": 1, "critical": 2}


def _promote_state(current, incoming):
    if STATE_RANK.get(incoming, 0) > STATE_RANK.get(current, 0):
        return incoming
    return current


def _max_index(values):
    best_index = 0
    best_value = values[0]
    for index in range(1, len(values)):
        if values[index] > best_value:
            best_index = index
            best_value = values[index]
    return best_index


def _predict_scores(model, inputs):
    input_data = array.array("h", [int(value) for value in inputs])
    output = array.array("f", [0.0] * model.outputs())
    model.predict(input_data, output)
    return [float(value) for value in output]


def _mean(values):
    return sum(values) / len(values)


def _pstdev(values):
    avg = _mean(values)
    variance = 0.0
    for value in values:
        variance += (value - avg) * (value - avg)
    variance /= len(values)
    return math.sqrt(variance)


def _sign(value):
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _sign_changes(values, tolerance):
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


def _unchanged_run(values, tolerance):
    run = 1
    last_value = values[-1]
    for value in reversed(values[:-1]):
        if abs(value - last_value) <= tolerance:
            run += 1
        else:
            break
    return run


def _out_of_range(value, field):
    low, high = PLAUSIBLE_BOUNDS[field]
    return value < low or value > high


def _normalized_sample(sample):
    return {
        "temperature_c": float(sample["temperature_c"]),
        "humidity_pct": float(sample["humidity_pct"]),
        "co2_ppm": float(sample["co2_ppm"]),
        "gap_seconds": max(1.0, float(sample.get("gap_seconds", NOMINAL_SAMPLE_INTERVAL_S))),
    }


def extract_anomaly_features(samples, current_gap_seconds=None):
    window = [_normalized_sample(sample) for sample in samples[-WINDOW_SIZE:]]
    while len(window) < WINDOW_SIZE:
        window.insert(0, dict(window[0]))

    features = {}
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

        features[field] = current
        features["prev_" + field] = previous
        features["delta_1_" + field] = current - previous
        features["delta_3_" + field] = current - earlier
        features["mean_6_" + field] = _mean(values)
        features["std_6_" + field] = _pstdev(values)
        features["range_6_" + field] = max(values) - min(values)
        features["unchanged_run_" + field] = float(
            _unchanged_run(values, UNCHANGED_TOLERANCE[field])
        )
        oscillation_score += _sign_changes(values, UNCHANGED_TOLERANCE[field])
        normalized_shift = abs(current - earlier) / scale[field]
        normalized_shifts.append(normalized_shift)
        multi_sensor_shift_score += normalized_shift

    gap_seconds = current_gap_seconds
    if gap_seconds is None:
        gap_seconds = window[-1]["gap_seconds"]

    out_of_range_count = 0
    current_out_of_range = 0
    for sample in window:
        for field in SENSOR_FIELDS:
            if _out_of_range(sample[field], field):
                out_of_range_count += 1
    for field in SENSOR_FIELDS:
        if _out_of_range(window[-1][field], field):
            current_out_of_range += 1

    features["gap_seconds"] = max(1.0, float(gap_seconds))
    features["gap_ratio"] = features["gap_seconds"] / NOMINAL_SAMPLE_INTERVAL_S
    features["out_of_range_count"] = float(out_of_range_count)
    features["current_out_of_range"] = float(current_out_of_range)
    features["oscillation_score"] = float(oscillation_score)
    features["multi_sensor_shift_score"] = multi_sensor_shift_score
    features["dominant_sensor_shift_ratio"] = max(normalized_shifts) / max(0.001, sum(normalized_shifts))
    features["temperature_band_gap"] = max(18.0 - features["temperature_c"], features["temperature_c"] - 30.0, 0.0)
    features["humidity_band_gap"] = max(45.0 - features["humidity_pct"], features["humidity_pct"] - 75.0, 0.0)
    features["co2_band_gap"] = max(features["co2_ppm"] - 1200.0, 0.0)
    return features


def _scale_feature(name, value):
    multiplier = ANOMALY_FEATURE_SCALES.get(name, 1)
    scaled = int(round(float(value) * multiplier))
    if scaled > 32767:
        return 32767
    if scaled < -32768:
        return -32768
    return scaled


def _environmental_label_from_features(features):
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


def _warmup_anomaly(features, sample_count):
    label = _environmental_label_from_features(features) or "normal"
    meta = ANOMALY_METADATA[label]

    if label == "normal":
        summary = "On-device AI anomaly watch is collecting more history before checking time-based faults."
        detail = (
            "Only snapshot-safe anomaly checks are active until the rolling window fills with real samples (%d/%d)."
            % (sample_count, WINDOW_SIZE)
        )
        confidence = 1.0
        anomaly_score = 0.0
    else:
        summary = meta["summary"]
        detail = (
            "Early window mode (%d/%d samples). %s"
            % (sample_count, WINDOW_SIZE, meta["description"])
        )
        confidence = 0.82
        anomaly_score = 0.82

    return {
        "label": label,
        "display_label": meta["display_label"],
        "severity": meta["severity"],
        "summary": summary,
        "detail": detail,
        "confidence": round(confidence, 3),
        "anomaly_score": round(anomaly_score, 3),
        "decision_engine": "board_anomaly_warmup",
        "model_available": True,
        "history_ready": False,
        "window_size": WINDOW_SIZE,
        "top_predictions": [
            {
                "label": label,
                "display_label": meta["display_label"],
                "confidence": round(confidence, 3),
            }
        ],
    }


class BoardAiRuntime:
    def __init__(self):
        self.action_models = {}
        self.anomaly_model = None
        self.history = []
        self._load_models()

    def _load_model(self, info):
        model = emlearn_trees.new(
            int(info["max_trees"]),
            int(info["max_nodes"]),
            int(info["max_leaves"]),
        )
        with open(info["filename"], "r") as handle:
            emlearn_trees.load_model(model, handle)
        gc.collect()
        return model

    def _load_models(self):
        for target_name in ACTION_MODELS:
            self.action_models[target_name] = self._load_model(ACTION_MODELS[target_name])
        self.anomaly_model = self._load_model(ANOMALY_MODEL)

    def _predict_actions(self, sensors):
        inputs = [
            int(round(sensors["temperature_c"] * 10)),
            int(round(sensors["humidity_pct"] * 10)),
            int(round(sensors["co2_ppm"])),
        ]
        actions = []
        triggered_conditions = []
        overall_state = "stable"

        for target_name in ACTION_MODELS:
            model = self.action_models[target_name]
            info = ACTION_MODELS[target_name]
            spec = ACTION_SPECS[target_name]
            scores = _predict_scores(model, inputs)
            classes = list(info["classes"])
            predicted_index = _max_index(scores)
            predicted_class = classes[predicted_index]
            positive_index = classes.index(1) if 1 in classes else predicted_index
            positive_confidence = float(scores[positive_index])
            active = int(predicted_class) == 1
            confidence = positive_confidence if active else (1.0 - positive_confidence)
            status = spec["active_status"] if active else "idle"
            reason = spec["active_reason"] if active else spec["idle_reason"]

            action = {
                "key": spec["key"],
                "label": spec["label"],
                "status": status,
                "active": active,
                "reason": "%s Confidence: %d%%." % (reason, int(round(confidence * 100))),
                "confidence": round(confidence, 3),
                "positive_confidence": round(positive_confidence, 3),
                "source": "AI",
            }
            actions.append(action)

            if active:
                severity = "critical" if positive_confidence >= 0.85 else "warning"
                overall_state = _promote_state(overall_state, severity)
                triggered_conditions.append(
                    {
                        "condition": spec["condition"],
                        "label": spec["condition_label"],
                        "severity": severity,
                        "recommended_action": spec["recommended_action"],
                        "detail": (
                            "On-device AI confidence %d%% based on %.1f C, %.1f%%, and %d ppm."
                            % (
                                int(round(positive_confidence * 100)),
                                sensors["temperature_c"],
                                sensors["humidity_pct"],
                                int(round(sensors["co2_ppm"])),
                            )
                        ),
                    }
                )

        active_actions = [action["status"] for action in actions if action["active"]]
        if active_actions:
            summary = "On-device AI recommended virtual actions: " + ", ".join(active_actions) + "."
        else:
            summary = "On-device AI predicts all virtual machines can remain idle."

        return {
            "actions": actions,
            "triggered_conditions": triggered_conditions,
            "overall_state": overall_state,
            "summary": summary,
            "decision_engine": "board_action_ai",
            "model_available": True,
            "on_device": True,
        }

    def _predict_anomaly(self, sensors, gap_seconds):
        samples = list(self.history)
        sample_count = len(samples)
        features = extract_anomaly_features(samples, current_gap_seconds=gap_seconds)
        if sample_count < WINDOW_SIZE:
            return _warmup_anomaly(features, sample_count)

        inputs = [_scale_feature(name, features[name]) for name in ANOMALY_FEATURE_COLUMNS]
        scores = _predict_scores(self.anomaly_model, inputs)
        classes = list(ANOMALY_MODEL["classes"])
        predicted_index = _max_index(scores)
        predicted_label = classes[predicted_index]
        selected_confidence = float(scores[predicted_index])
        normal_probability = 0.0
        if "normal" in classes:
            normal_probability = float(scores[classes.index("normal")])

        fallback_label = _environmental_label_from_features(features)
        if predicted_label == "out_of_range" and features["current_out_of_range"] <= 0:
            replacement_label = fallback_label or "normal"
            predicted_label = replacement_label
            if replacement_label in classes:
                selected_confidence = max(
                    float(scores[classes.index(replacement_label)]),
                    0.55 if replacement_label != "normal" else 0.6,
                )
            else:
                selected_confidence = 0.6 if replacement_label == "normal" else 0.55
        if (
            fallback_label is not None
            and predicted_label in (
                "sensor_spike",
                "sensor_drift",
                "sensor_stuck",
                "cross_variable_inconsistency",
            )
            and selected_confidence < 0.6
        ):
            predicted_label = fallback_label
            selected_confidence = max(
                float(scores[classes.index(fallback_label)]) if fallback_label in classes else 0.0,
                0.72,
            )

        ranked = []
        for index, label in enumerate(classes):
            confidence = float(scores[index])
            ranked.append((label, confidence))
        ranked.sort(key=lambda item: item[1], reverse=True)
        top_predictions = []
        added = {}
        top_predictions.append(
            {
                "label": predicted_label,
                "display_label": ANOMALY_METADATA[predicted_label]["display_label"],
                "confidence": round(selected_confidence, 3),
            }
        )
        added[predicted_label] = True
        for label, confidence in ranked:
            if label in added:
                continue
            top_predictions.append(
                {
                    "label": label,
                    "display_label": ANOMALY_METADATA[label]["display_label"],
                    "confidence": round(confidence, 3),
                }
            )
            added[label] = True
            if len(top_predictions) >= 3:
                break

        meta = ANOMALY_METADATA[predicted_label]
        return {
            "label": predicted_label,
            "display_label": meta["display_label"],
            "severity": meta["severity"],
            "summary": meta["summary"],
            "detail": (
                "Window end: %.1f C, %.1f%%, %d ppm. Gap %d s. %s"
                % (
                    sensors["temperature_c"],
                    sensors["humidity_pct"],
                    int(round(sensors["co2_ppm"])),
                    int(round(gap_seconds)),
                    meta["description"],
                )
            ),
            "confidence": round(selected_confidence, 3),
            "anomaly_score": round(max(0.0, 1.0 - normal_probability), 3),
            "decision_engine": "board_anomaly_ai",
            "model_available": True,
            "history_ready": True,
            "window_size": WINDOW_SIZE,
            "top_predictions": top_predictions,
        }

    def update(self, temperature_c, humidity_pct, co2_ppm, gap_seconds):
        sensors = {
            "temperature_c": round(float(temperature_c), 1),
            "humidity_pct": round(float(humidity_pct), 1),
            "co2_ppm": int(round(float(co2_ppm))),
        }
        self.history.append(
            {
                "temperature_c": sensors["temperature_c"],
                "humidity_pct": sensors["humidity_pct"],
                "co2_ppm": float(sensors["co2_ppm"]),
                "gap_seconds": max(1.0, float(gap_seconds)),
            }
        )
        del self.history[:-WINDOW_SIZE]

        action_result = self._predict_actions(sensors)
        anomaly = self._predict_anomaly(sensors, gap_seconds)
        summary = action_result["summary"]
        if anomaly["label"] != "normal":
            summary = summary + " " + anomaly["summary"]

        return {
            "sensors": sensors,
            "actions": action_result["actions"],
            "triggered_conditions": action_result["triggered_conditions"],
            "anomaly": anomaly,
            "summary": summary,
            "overall_state": _promote_state(action_result["overall_state"], anomaly["severity"]),
            "decision_engine": "board_on_device_ai",
            "model_available": True,
            "on_device": True,
        }
