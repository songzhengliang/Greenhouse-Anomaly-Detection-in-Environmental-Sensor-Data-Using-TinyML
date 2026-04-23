import copy

from greenhouse_anomaly_detection import DROPOUT_THRESHOLD_S, NOMINAL_SAMPLE_INTERVAL_S


DEFAULT_GAP_SECONDS = int(NOMINAL_SAMPLE_INTERVAL_S)
DROPOUT_GAP_SECONDS = int(max(DROPOUT_THRESHOLD_S * 1.25, DEFAULT_GAP_SECONDS + 5))


def sample(temperature_c, humidity_pct, co2_ppm, gap_seconds=DEFAULT_GAP_SECONDS):
    return {
        "temperature_c": temperature_c,
        "humidity_pct": humidity_pct,
        "co2_ppm": co2_ppm,
        "gap_seconds": gap_seconds,
    }


PRESET_DEFINITIONS = [
    {
        "id": "normal_baseline",
        "label": "Nominal Greenhouse",
        "category": "Baseline",
        "target_anomaly": "normal",
        "description": "Healthy rolling window with natural greenhouse variation and no active anomaly.",
        "samples": [
            sample(24.0, 60.0, 900),
            sample(24.2, 60.8, 916),
            sample(23.9, 59.7, 895),
            sample(24.3, 60.5, 912),
            sample(24.0, 59.8, 898),
            sample(24.2, 60.6, 914),
        ],
    },
    {
        "id": "temperature_high",
        "label": "Heat Stress",
        "category": "Environmental",
        "target_anomaly": "temperature_high",
        "description": "Sustained hot greenhouse window that should trigger high-temperature detection.",
        "samples": [
            sample(24.6, 57.8, 924),
            sample(27.0, 57.4, 932),
            sample(29.4, 57.0, 938),
            sample(32.0, 56.7, 944),
            sample(34.6, 56.5, 951),
            sample(37.2, 56.2, 958),
        ],
    },
    {
        "id": "temperature_low",
        "label": "Cold Snap",
        "category": "Environmental",
        "target_anomaly": "temperature_low",
        "description": "Sustained cold window for demonstrating low-temperature greenhouse alerts.",
        "samples": [
            sample(24.3, 61.1, 896),
            sample(22.0, 61.2, 900),
            sample(19.5, 61.3, 903),
            sample(17.2, 61.5, 907),
            sample(15.2, 61.7, 910),
            sample(13.8, 61.8, 914),
        ],
    },
    {
        "id": "humidity_high",
        "label": "Humidity Surge",
        "category": "Environmental",
        "target_anomaly": "humidity_high",
        "description": "Very damp greenhouse window for showing persistent high-humidity behaviour.",
        "samples": [
            sample(24.2, 60.0, 900),
            sample(24.1, 65.0, 905),
            sample(24.0, 70.5, 908),
            sample(23.9, 76.8, 912),
            sample(23.8, 83.2, 916),
            sample(23.8, 89.0, 920),
        ],
    },
    {
        "id": "humidity_low",
        "label": "Dry Air Pocket",
        "category": "Environmental",
        "target_anomaly": "humidity_low",
        "description": "Dry-air scenario that should push the anomaly model into low-humidity mode.",
        "samples": [
            sample(24.1, 59.5, 910),
            sample(24.0, 54.0, 912),
            sample(23.9, 48.2, 915),
            sample(23.9, 42.0, 917),
            sample(23.8, 36.5, 920),
            sample(23.7, 31.8, 922),
        ],
    },
    {
        "id": "co2_high",
        "label": "CO2 Buildup",
        "category": "Environmental",
        "target_anomaly": "co2_high",
        "description": "Closed-vent scenario with rising CO2 concentration across the recent window.",
        "samples": [
            sample(24.2, 59.4, 910),
            sample(24.1, 59.2, 1100),
            sample(24.1, 59.0, 1280),
            sample(24.0, 58.8, 1490),
            sample(23.9, 58.5, 1700),
            sample(23.8, 58.2, 1920),
        ],
    },
    {
        "id": "sensor_spike",
        "label": "Sensor Spike",
        "category": "Sensor Fault",
        "target_anomaly": "sensor_spike",
        "description": "Mostly stable conditions with one sudden jump that looks like a spike fault.",
        "samples": [
            sample(24.0, 60.0, 900),
            sample(24.1, 60.2, 905),
            sample(24.0, 60.1, 902),
            sample(24.2, 60.3, 908),
            sample(24.1, 60.2, 906),
            sample(37.6, 60.4, 910),
        ],
    },
    {
        "id": "sensor_drift",
        "label": "Sensor Drift",
        "category": "Sensor Fault",
        "target_anomaly": "sensor_drift",
        "description": "Gradual sensor bias building across the last few samples instead of a hard threshold breach.",
        "samples": [
            sample(23.8, 59.0, 890),
            sample(24.6, 59.1, 892),
            sample(25.5, 59.2, 894),
            sample(26.5, 59.3, 896),
            sample(27.6, 59.4, 898),
            sample(28.8, 59.5, 900),
        ],
    },
    {
        "id": "sensor_stuck",
        "label": "Sensor Stuck",
        "category": "Sensor Fault",
        "target_anomaly": "sensor_stuck",
        "description": "One reading channel stays frozen while the other variables continue to move.",
        "samples": [
            sample(24.0, 58.2, 905),
            sample(24.0, 58.8, 918),
            sample(24.0, 59.6, 929),
            sample(24.0, 60.4, 941),
            sample(24.0, 61.1, 952),
            sample(24.0, 61.9, 964),
        ],
    },
    {
        "id": "sensor_dropout",
        "label": "Telemetry Dropout",
        "category": "Telemetry",
        "target_anomaly": "sensor_dropout",
        "description": "A delayed update gap that mimics a missed sample or transport outage.",
        "samples": [
            sample(24.2, 59.4, 905),
            sample(24.1, 59.6, 910),
            sample(24.0, 59.7, 914),
            sample(24.1, 59.8, 918),
            sample(24.0, 60.0, 922),
            sample(24.1, 60.1, 926, gap_seconds=DROPOUT_GAP_SECONDS),
        ],
    },
    {
        "id": "cross_variable_inconsistency",
        "label": "Cross-Signal Conflict",
        "category": "Consistency",
        "target_anomaly": "cross_variable_inconsistency",
        "description": "Sensor pattern that does not match believable greenhouse relationships.",
        "samples": [
            sample(24.0, 60.0, 900),
            sample(24.2, 60.2, 910),
            sample(24.4, 60.4, 920),
            sample(30.0, 88.0, 470),
            sample(31.5, 92.0, 420),
            sample(33.0, 95.0, 390),
        ],
    },
    {
        "id": "out_of_range",
        "label": "Out-of-Range Fault",
        "category": "Extreme",
        "target_anomaly": "out_of_range",
        "description": "Physically implausible sensor value for demonstrating a hard fault condition.",
        "samples": [
            sample(24.0, 60.0, 900),
            sample(24.1, 60.2, 905),
            sample(24.0, 60.1, 902),
            sample(24.2, 60.3, 908),
            sample(24.1, 60.2, 906),
            sample(-12.0, 60.1, 910),
        ],
    },
]


def presentation_preset_catalog():
    catalog = []
    for preset in PRESET_DEFINITIONS:
        latest = preset["samples"][-1]
        catalog.append(
            {
                "id": preset["id"],
                "label": preset["label"],
                "category": preset["category"],
                "target_anomaly": preset["target_anomaly"],
                "description": preset["description"],
                "preview": {
                    "temperature_c": latest["temperature_c"],
                    "humidity_pct": latest["humidity_pct"],
                    "co2_ppm": latest["co2_ppm"],
                },
            }
        )
    return catalog


def get_presentation_preset(preset_id):
    for preset in PRESET_DEFINITIONS:
        if preset["id"] == preset_id:
            return copy.deepcopy(preset)
    return None
