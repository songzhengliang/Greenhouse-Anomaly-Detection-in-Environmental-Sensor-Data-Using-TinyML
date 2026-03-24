from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path


OUTPUT_FILE = "greenhouse_action_control_dataset.csv"
DEFAULT_SEED = 42
SCENARIO_ORDER = [
    "stable",
    "transition_band",
    "temperature_low",
    "temperature_high",
    "humidity_low",
    "humidity_high",
    "co2_high",
    "cold_and_dry",
    "hot_and_humid",
    "hot_and_high_co2",
    "humid_and_high_co2",
]

THRESHOLDS = {
    "temperature_low": 18.0,
    "temperature_high": 30.0,
    "humidity_low": 45.0,
    "humidity_high": 75.0,
    "co2_high": 1200.0,
}


def bounded_gauss(rng: random.Random, mean: float, stddev: float, low: float, high: float) -> float:
    for _ in range(12):
        value = rng.gauss(mean, stddev)
        if low <= value <= high:
            return value
    return min(max(value, low), high)


def sample_transition_band(rng: random.Random) -> tuple[float, float, float]:
    temp_center = rng.choice([17.8, 18.2, 29.8, 30.2, 24.0])
    humidity_center = rng.choice([44.2, 45.8, 74.2, 75.8, 60.0])
    co2_center = rng.choice([1130.0, 1190.0, 1230.0, 900.0])
    return (
        bounded_gauss(rng, temp_center, 0.9, 15.0, 33.0),
        bounded_gauss(rng, humidity_center, 3.0, 35.0, 85.0),
        bounded_gauss(rng, co2_center, 90.0, 700.0, 1700.0),
    )


def sample_scenario(name: str, rng: random.Random) -> tuple[float, float, float]:
    if name == "stable":
        return (
            bounded_gauss(rng, 24.5, 2.6, 18.5, 29.5),
            bounded_gauss(rng, 60.0, 7.0, 46.0, 74.0),
            bounded_gauss(rng, 900.0, 130.0, 650.0, 1180.0),
        )
    if name == "transition_band":
        return sample_transition_band(rng)
    if name == "temperature_low":
        return (
            bounded_gauss(rng, 14.2, 2.8, 7.0, 17.9),
            bounded_gauss(rng, 58.0, 8.0, 42.0, 72.0),
            bounded_gauss(rng, 920.0, 170.0, 650.0, 1180.0),
        )
    if name == "temperature_high":
        return (
            bounded_gauss(rng, 33.6, 2.6, 30.1, 40.0),
            bounded_gauss(rng, 57.0, 9.0, 40.0, 74.0),
            bounded_gauss(rng, 1000.0, 180.0, 700.0, 1250.0),
        )
    if name == "humidity_low":
        return (
            bounded_gauss(rng, 24.5, 2.7, 18.0, 29.5),
            bounded_gauss(rng, 34.0, 6.5, 18.0, 44.8),
            bounded_gauss(rng, 930.0, 150.0, 650.0, 1180.0),
        )
    if name == "humidity_high":
        return (
            bounded_gauss(rng, 25.5, 2.6, 18.0, 29.5),
            bounded_gauss(rng, 84.0, 5.5, 75.2, 96.0),
            bounded_gauss(rng, 980.0, 160.0, 700.0, 1200.0),
        )
    if name == "co2_high":
        return (
            bounded_gauss(rng, 25.0, 2.6, 18.0, 29.5),
            bounded_gauss(rng, 58.0, 8.0, 42.0, 72.0),
            bounded_gauss(rng, 1570.0, 220.0, 1205.0, 2600.0),
        )
    if name == "cold_and_dry":
        return (
            bounded_gauss(rng, 13.5, 2.8, 7.0, 17.8),
            bounded_gauss(rng, 30.0, 6.0, 15.0, 44.5),
            bounded_gauss(rng, 960.0, 170.0, 650.0, 1180.0),
        )
    if name == "hot_and_humid":
        return (
            bounded_gauss(rng, 34.0, 2.4, 30.1, 40.0),
            bounded_gauss(rng, 83.0, 5.5, 75.1, 96.0),
            bounded_gauss(rng, 1080.0, 180.0, 820.0, 1350.0),
        )
    if name == "hot_and_high_co2":
        return (
            bounded_gauss(rng, 33.8, 2.5, 30.1, 40.0),
            bounded_gauss(rng, 58.0, 9.0, 40.0, 72.0),
            bounded_gauss(rng, 1760.0, 250.0, 1205.0, 2800.0),
        )
    if name == "humid_and_high_co2":
        return (
            bounded_gauss(rng, 25.8, 2.6, 18.0, 29.8),
            bounded_gauss(rng, 84.5, 5.5, 75.1, 96.0),
            bounded_gauss(rng, 1700.0, 230.0, 1205.0, 2800.0),
        )
    raise ValueError(f"Unsupported scenario: {name}")


def evaluate_actions(temperature_c: float, humidity_pct: float, co2_ppm: float) -> dict[str, int | str]:
    heater_on = int(temperature_c < THRESHOLDS["temperature_low"])
    cooling_fan_on = int(temperature_c > THRESHOLDS["temperature_high"])
    ventilation_on = int(
        cooling_fan_on
        or humidity_pct > THRESHOLDS["humidity_high"]
        or co2_ppm > THRESHOLDS["co2_high"]
    )
    mister_on = int(humidity_pct < THRESHOLDS["humidity_low"])

    temperature_gap = max(
        THRESHOLDS["temperature_low"] - temperature_c,
        temperature_c - THRESHOLDS["temperature_high"],
        0.0,
    )
    humidity_gap = max(
        THRESHOLDS["humidity_low"] - humidity_pct,
        humidity_pct - THRESHOLDS["humidity_high"],
        0.0,
    )
    co2_gap = max(co2_ppm - THRESHOLDS["co2_high"], 0.0)

    overall_state = "stable"
    if temperature_gap >= 4.0 or humidity_gap >= 10.0 or co2_gap >= 500.0:
        overall_state = "critical"
    elif any([heater_on, cooling_fan_on, ventilation_on, mister_on]):
        overall_state = "warning"

    return {
        "heater_on": heater_on,
        "cooling_fan_on": cooling_fan_on,
        "ventilation_on": ventilation_on,
        "mister_on": mister_on,
        "trigger_count": heater_on + cooling_fan_on + ventilation_on + mister_on,
        "overall_state": overall_state,
    }


def generate_rows(rows_per_scenario: int, seed: int) -> list[dict[str, int | float | str]]:
    rng = random.Random(seed)
    rows = []

    for scenario in SCENARIO_ORDER:
        for _ in range(rows_per_scenario):
            temperature_c, humidity_pct, co2_ppm = sample_scenario(scenario, rng)
            labels = evaluate_actions(temperature_c, humidity_pct, co2_ppm)
            rows.append(
                {
                    "temperature_c": round(temperature_c, 1),
                    "humidity_pct": round(humidity_pct, 1),
                    "co2_ppm": int(round(co2_ppm)),
                    "heater_on": labels["heater_on"],
                    "cooling_fan_on": labels["cooling_fan_on"],
                    "ventilation_on": labels["ventilation_on"],
                    "mister_on": labels["mister_on"],
                    "trigger_count": labels["trigger_count"],
                    "overall_state": labels["overall_state"],
                    "scenario": scenario,
                }
            )

    rng.shuffle(rows)
    return rows


def write_dataset(rows: list[dict[str, int | float | str]], output_path: Path) -> None:
    fieldnames = [
        "temperature_c",
        "humidity_pct",
        "co2_ppm",
        "heater_on",
        "cooling_fan_on",
        "ventilation_on",
        "mister_on",
        "trigger_count",
        "overall_state",
        "scenario",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic greenhouse control-action dataset."
    )
    parser.add_argument("--rows-per-scenario", type=int, default=550)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", default=OUTPUT_FILE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = generate_rows(args.rows_per_scenario, args.seed)
    output_path = Path(args.output)
    write_dataset(rows, output_path)
    print(f"Wrote {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
