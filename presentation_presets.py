import copy


PRESET_DEFINITIONS = [
    {
        "id": "normal_baseline",
        "label": "Nominal Greenhouse",
        "category": "Baseline",
        "target_anomaly": "normal",
        "description": "Healthy rolling window with natural greenhouse variation and no active anomaly.",
        "samples": [
            {"temperature_c": 23.5, "humidity_pct": 56.0, "co2_ppm": 820, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 59.0, "co2_ppm": 860, "gap_seconds": 30},
            {"temperature_c": 24.7, "humidity_pct": 62.0, "co2_ppm": 910, "gap_seconds": 30},
            {"temperature_c": 24.2, "humidity_pct": 58.0, "co2_ppm": 890, "gap_seconds": 30},
            {"temperature_c": 23.8, "humidity_pct": 61.0, "co2_ppm": 940, "gap_seconds": 30},
            {"temperature_c": 24.5, "humidity_pct": 57.0, "co2_ppm": 880, "gap_seconds": 30},
        ],
    },
    {
        "id": "temperature_high",
        "label": "Heat Stress",
        "category": "Environmental",
        "target_anomaly": "temperature_high",
        "description": "Sustained hot greenhouse window that should trigger high-temperature detection.",
        "samples": [
            {"temperature_c": 31.8, "humidity_pct": 58.0, "co2_ppm": 930, "gap_seconds": 30},
            {"temperature_c": 32.2, "humidity_pct": 57.8, "co2_ppm": 935, "gap_seconds": 30},
            {"temperature_c": 32.5, "humidity_pct": 57.5, "co2_ppm": 940, "gap_seconds": 30},
            {"temperature_c": 33.0, "humidity_pct": 57.1, "co2_ppm": 948, "gap_seconds": 30},
            {"temperature_c": 33.4, "humidity_pct": 56.8, "co2_ppm": 952, "gap_seconds": 30},
            {"temperature_c": 33.8, "humidity_pct": 56.4, "co2_ppm": 960, "gap_seconds": 30},
        ],
    },
    {
        "id": "temperature_low",
        "label": "Cold Snap",
        "category": "Environmental",
        "target_anomaly": "temperature_low",
        "description": "Sustained cold window for demonstrating low-temperature greenhouse alerts.",
        "samples": [
            {"temperature_c": 16.8, "humidity_pct": 61.0, "co2_ppm": 890, "gap_seconds": 30},
            {"temperature_c": 16.4, "humidity_pct": 61.2, "co2_ppm": 892, "gap_seconds": 30},
            {"temperature_c": 16.0, "humidity_pct": 61.4, "co2_ppm": 895, "gap_seconds": 30},
            {"temperature_c": 15.6, "humidity_pct": 61.5, "co2_ppm": 898, "gap_seconds": 30},
            {"temperature_c": 15.2, "humidity_pct": 61.7, "co2_ppm": 900, "gap_seconds": 30},
            {"temperature_c": 14.9, "humidity_pct": 62.0, "co2_ppm": 905, "gap_seconds": 30},
        ],
    },
    {
        "id": "humidity_high",
        "label": "Humidity Surge",
        "category": "Environmental",
        "target_anomaly": "humidity_high",
        "description": "Very damp greenhouse window for showing persistent high-humidity behaviour.",
        "samples": [
            {"temperature_c": 22.8, "humidity_pct": 82.0, "co2_ppm": 890, "gap_seconds": 30},
            {"temperature_c": 22.7, "humidity_pct": 84.0, "co2_ppm": 892, "gap_seconds": 30},
            {"temperature_c": 22.6, "humidity_pct": 86.0, "co2_ppm": 894, "gap_seconds": 30},
            {"temperature_c": 22.5, "humidity_pct": 88.0, "co2_ppm": 896, "gap_seconds": 30},
            {"temperature_c": 22.4, "humidity_pct": 90.0, "co2_ppm": 898, "gap_seconds": 30},
            {"temperature_c": 22.3, "humidity_pct": 92.0, "co2_ppm": 900, "gap_seconds": 30},
        ],
    },
    {
        "id": "humidity_low",
        "label": "Dry Air Pocket",
        "category": "Environmental",
        "target_anomaly": "humidity_low",
        "description": "Dry-air scenario that should push the anomaly model into low-humidity mode.",
        "samples": [
            {"temperature_c": 23.5, "humidity_pct": 34.0, "co2_ppm": 905, "gap_seconds": 30},
            {"temperature_c": 23.4, "humidity_pct": 32.0, "co2_ppm": 907, "gap_seconds": 30},
            {"temperature_c": 23.3, "humidity_pct": 30.0, "co2_ppm": 910, "gap_seconds": 30},
            {"temperature_c": 23.2, "humidity_pct": 28.0, "co2_ppm": 912, "gap_seconds": 30},
            {"temperature_c": 23.1, "humidity_pct": 26.0, "co2_ppm": 915, "gap_seconds": 30},
            {"temperature_c": 23.0, "humidity_pct": 24.0, "co2_ppm": 918, "gap_seconds": 30},
        ],
    },
    {
        "id": "co2_high",
        "label": "CO2 Buildup",
        "category": "Environmental",
        "target_anomaly": "co2_high",
        "description": "Closed-vent scenario with rising CO2 concentration across the recent window.",
        "samples": [
            {"temperature_c": 24.2, "humidity_pct": 59.2, "co2_ppm": 1380, "gap_seconds": 30},
            {"temperature_c": 24.1, "humidity_pct": 59.0, "co2_ppm": 1440, "gap_seconds": 30},
            {"temperature_c": 24.1, "humidity_pct": 58.8, "co2_ppm": 1510, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 58.5, "co2_ppm": 1580, "gap_seconds": 30},
            {"temperature_c": 23.9, "humidity_pct": 58.2, "co2_ppm": 1660, "gap_seconds": 30},
            {"temperature_c": 23.8, "humidity_pct": 58.0, "co2_ppm": 1740, "gap_seconds": 30},
        ],
    },
    {
        "id": "sensor_spike",
        "label": "Sensor Spike",
        "category": "Sensor Fault",
        "target_anomaly": "sensor_spike",
        "description": "Mostly stable conditions with one sudden jump that looks like a spike fault.",
        "samples": [
            {"temperature_c": 24.0, "humidity_pct": 60.0, "co2_ppm": 900, "gap_seconds": 30},
            {"temperature_c": 24.1, "humidity_pct": 60.2, "co2_ppm": 905, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 60.1, "co2_ppm": 902, "gap_seconds": 30},
            {"temperature_c": 24.2, "humidity_pct": 60.3, "co2_ppm": 908, "gap_seconds": 30},
            {"temperature_c": 24.1, "humidity_pct": 60.2, "co2_ppm": 906, "gap_seconds": 30},
            {"temperature_c": 37.6, "humidity_pct": 60.4, "co2_ppm": 910, "gap_seconds": 30},
        ],
    },
    {
        "id": "sensor_drift",
        "label": "Sensor Drift",
        "category": "Sensor Fault",
        "target_anomaly": "sensor_drift",
        "description": "Gradual sensor bias building across the last few samples instead of a hard threshold breach.",
        "samples": [
            {"temperature_c": 23.8, "humidity_pct": 59.0, "co2_ppm": 890, "gap_seconds": 30},
            {"temperature_c": 24.6, "humidity_pct": 59.1, "co2_ppm": 892, "gap_seconds": 30},
            {"temperature_c": 25.5, "humidity_pct": 59.2, "co2_ppm": 894, "gap_seconds": 30},
            {"temperature_c": 26.5, "humidity_pct": 59.3, "co2_ppm": 896, "gap_seconds": 30},
            {"temperature_c": 27.6, "humidity_pct": 59.4, "co2_ppm": 898, "gap_seconds": 30},
            {"temperature_c": 28.8, "humidity_pct": 59.5, "co2_ppm": 900, "gap_seconds": 30},
        ],
    },
    {
        "id": "sensor_stuck",
        "label": "Sensor Stuck",
        "category": "Sensor Fault",
        "target_anomaly": "sensor_stuck",
        "description": "One reading channel stays frozen while the other variables continue to move.",
        "samples": [
            {"temperature_c": 24.0, "humidity_pct": 58.2, "co2_ppm": 905, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 58.8, "co2_ppm": 918, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 59.6, "co2_ppm": 929, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 60.4, "co2_ppm": 941, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 61.1, "co2_ppm": 952, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 61.9, "co2_ppm": 964, "gap_seconds": 30},
        ],
    },
    {
        "id": "sensor_dropout",
        "label": "Telemetry Dropout",
        "category": "Telemetry",
        "target_anomaly": "sensor_dropout",
        "description": "A delayed update gap that mimics a missed sample or transport outage.",
        "samples": [
            {"temperature_c": 24.2, "humidity_pct": 59.4, "co2_ppm": 905, "gap_seconds": 30},
            {"temperature_c": 24.1, "humidity_pct": 59.6, "co2_ppm": 910, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 59.7, "co2_ppm": 914, "gap_seconds": 30},
            {"temperature_c": 24.1, "humidity_pct": 59.8, "co2_ppm": 918, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 60.0, "co2_ppm": 922, "gap_seconds": 30},
            {"temperature_c": 24.1, "humidity_pct": 60.1, "co2_ppm": 926, "gap_seconds": 180},
        ],
    },
    {
        "id": "cross_variable_inconsistency",
        "label": "Cross-Signal Conflict",
        "category": "Consistency",
        "target_anomaly": "cross_variable_inconsistency",
        "description": "Sensor pattern that does not match believable greenhouse relationships.",
        "samples": [
            {"temperature_c": 24.0, "humidity_pct": 60.0, "co2_ppm": 900, "gap_seconds": 30},
            {"temperature_c": 24.2, "humidity_pct": 60.2, "co2_ppm": 910, "gap_seconds": 30},
            {"temperature_c": 24.4, "humidity_pct": 60.4, "co2_ppm": 920, "gap_seconds": 30},
            {"temperature_c": 30.0, "humidity_pct": 88.0, "co2_ppm": 470, "gap_seconds": 30},
            {"temperature_c": 31.5, "humidity_pct": 92.0, "co2_ppm": 420, "gap_seconds": 30},
            {"temperature_c": 33.0, "humidity_pct": 95.0, "co2_ppm": 390, "gap_seconds": 30},
        ],
    },
    {
        "id": "out_of_range",
        "label": "Out-of-Range Fault",
        "category": "Extreme",
        "target_anomaly": "out_of_range",
        "description": "Physically implausible sensor value for demonstrating a hard fault condition.",
        "samples": [
            {"temperature_c": 24.0, "humidity_pct": 60.0, "co2_ppm": 900, "gap_seconds": 30},
            {"temperature_c": 24.1, "humidity_pct": 60.2, "co2_ppm": 905, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 60.1, "co2_ppm": 902, "gap_seconds": 30},
            {"temperature_c": 24.2, "humidity_pct": 60.3, "co2_ppm": 908, "gap_seconds": 30},
            {"temperature_c": 24.1, "humidity_pct": 60.2, "co2_ppm": 906, "gap_seconds": 30},
            {"temperature_c": 24.0, "humidity_pct": 104.0, "co2_ppm": 910, "gap_seconds": 30},
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
