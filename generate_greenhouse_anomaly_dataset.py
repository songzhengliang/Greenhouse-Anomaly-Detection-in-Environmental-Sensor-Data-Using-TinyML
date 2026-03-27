from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from greenhouse_anomaly_detection import (
    ANOMALY_LABELS,
    ANOMALY_METADATA,
    FEATURE_COLUMNS,
    PLAUSIBLE_BOUNDS,
    WINDOW_SIZE,
    extract_anomaly_features,
)
from project_paths import ANOMALY_DATASET_FILE, ensure_parent_dir


OUTPUT_FILE = ANOMALY_DATASET_FILE
DEFAULT_SEED = 42
ROWS_PER_SCENARIO = 480


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def bounded_gauss(
    rng: random.Random,
    mean: float,
    stddev: float,
    low: float,
    high: float,
) -> float:
    value = mean
    for _ in range(12):
        value = rng.gauss(mean, stddev)
        if low <= value <= high:
            return value
    return clamp(value, low, high)


def nominal_gap(rng: random.Random) -> float:
    return clamp(rng.gauss(30.0, 1.8), 24.0, 36.0)


def stable_sequence(rng: random.Random) -> list[dict]:
    temperature_c = bounded_gauss(rng, 24.5, 1.2, 19.0, 29.0)
    humidity_pct = bounded_gauss(rng, 60.0, 4.0, 48.0, 72.0)
    co2_ppm = bounded_gauss(rng, 900.0, 80.0, 650.0, 1120.0)
    samples = []

    for _ in range(WINDOW_SIZE):
        temperature_c = clamp(temperature_c + rng.gauss(0.0, 0.35), 18.0, 31.0)
        humidity_pct = clamp(humidity_pct + rng.gauss(0.0, 1.2), 35.0, 90.0)
        co2_ppm = clamp(co2_ppm + rng.gauss(0.0, 35.0), 550.0, 1600.0)
        samples.append(
            {
                "temperature_c": round(temperature_c, 3),
                "humidity_pct": round(humidity_pct, 3),
                "co2_ppm": round(co2_ppm, 3),
                "gap_seconds": round(nominal_gap(rng), 3),
            }
        )

    return samples


def apply_linear_adjustment(
    samples: list[dict],
    field: str,
    final_delta: float,
    rng: random.Random,
    noise_stddev: float,
) -> None:
    for index, sample in enumerate(samples):
        fraction = index / (len(samples) - 1)
        sample[field] = round(sample[field] + final_delta * fraction + rng.gauss(0.0, noise_stddev), 3)


def build_temperature_high(rng: random.Random) -> list[dict]:
    samples = stable_sequence(rng)
    apply_linear_adjustment(samples, "temperature_c", rng.uniform(7.5, 12.5), rng, 0.25)
    apply_linear_adjustment(samples, "humidity_pct", -rng.uniform(2.0, 8.0), rng, 0.5)
    return samples


def build_temperature_low(rng: random.Random) -> list[dict]:
    samples = stable_sequence(rng)
    apply_linear_adjustment(samples, "temperature_c", -rng.uniform(7.0, 12.0), rng, 0.25)
    return samples


def build_humidity_high(rng: random.Random) -> list[dict]:
    samples = stable_sequence(rng)
    apply_linear_adjustment(samples, "humidity_pct", rng.uniform(18.0, 28.0), rng, 0.7)
    return samples


def build_humidity_low(rng: random.Random) -> list[dict]:
    samples = stable_sequence(rng)
    apply_linear_adjustment(samples, "humidity_pct", -rng.uniform(18.0, 28.0), rng, 0.7)
    return samples


def build_co2_high(rng: random.Random) -> list[dict]:
    samples = stable_sequence(rng)
    apply_linear_adjustment(samples, "co2_ppm", rng.uniform(650.0, 1300.0), rng, 35.0)
    return samples


def build_sensor_spike(rng: random.Random) -> list[dict]:
    samples = stable_sequence(rng)
    field = rng.choice(["temperature_c", "humidity_pct", "co2_ppm"])
    if field == "temperature_c":
        samples[-1][field] = round(
            clamp(samples[-2][field] + rng.choice([-1, 1]) * rng.uniform(7.0, 12.0), -2.0, 48.0),
            3,
        )
    elif field == "humidity_pct":
        samples[-1][field] = round(
            clamp(samples[-2][field] + rng.choice([-1, 1]) * rng.uniform(22.0, 34.0), 1.0, 99.0),
            3,
        )
    else:
        samples[-1][field] = round(
            clamp(samples[-2][field] + rng.choice([-1, 1]) * rng.uniform(700.0, 1500.0), 280.0, 4200.0),
            3,
        )
    return samples


def build_sensor_drift(rng: random.Random) -> list[dict]:
    samples = stable_sequence(rng)
    field = rng.choice(["temperature_c", "humidity_pct", "co2_ppm"])
    if field == "temperature_c":
        final_delta = rng.choice([-1, 1]) * rng.uniform(3.2, 5.2)
        noise = 0.06
    elif field == "humidity_pct":
        final_delta = rng.choice([-1, 1]) * rng.uniform(8.0, 13.0)
        noise = 0.16
    else:
        final_delta = rng.choice([-1, 1]) * rng.uniform(240.0, 420.0)
        noise = 10.0
    apply_linear_adjustment(samples, field, final_delta, rng, noise)
    for other_field in ("temperature_c", "humidity_pct", "co2_ppm"):
        if other_field == field:
            continue
        apply_linear_adjustment(samples, other_field, rng.uniform(-0.6, 0.6), rng, 0.04 if other_field != "co2_ppm" else 4.0)
    return samples


def build_sensor_stuck(rng: random.Random) -> list[dict]:
    samples = stable_sequence(rng)
    field = rng.choice(["temperature_c", "humidity_pct", "co2_ppm"])
    anchor = samples[1][field]
    for index in range(2, len(samples)):
        samples[index][field] = anchor
    return samples


def build_sensor_dropout(rng: random.Random) -> list[dict]:
    samples = stable_sequence(rng)
    samples[-1]["gap_seconds"] = round(rng.uniform(120.0, 240.0), 3)
    for field in ("temperature_c", "humidity_pct", "co2_ppm"):
        samples[-1][field] = samples[-2][field]
    return samples


def build_cross_variable_inconsistency(rng: random.Random) -> list[dict]:
    samples = stable_sequence(rng)
    pattern = rng.choice(["hot_humid_low_co2", "flat_temp_dry_high_co2"])
    if pattern == "hot_humid_low_co2":
        apply_linear_adjustment(samples, "temperature_c", rng.uniform(6.0, 9.0), rng, 0.2)
        apply_linear_adjustment(samples, "humidity_pct", rng.uniform(18.0, 24.0), rng, 0.35)
        apply_linear_adjustment(samples, "co2_ppm", -rng.uniform(300.0, 520.0), rng, 20.0)
    else:
        apply_linear_adjustment(samples, "temperature_c", rng.uniform(-0.8, 0.8), rng, 0.08)
        apply_linear_adjustment(samples, "humidity_pct", -rng.uniform(20.0, 28.0), rng, 0.35)
        apply_linear_adjustment(samples, "co2_ppm", rng.uniform(850.0, 1250.0), rng, 30.0)
    return samples


def build_out_of_range(rng: random.Random) -> list[dict]:
    samples = stable_sequence(rng)
    field = rng.choice(["temperature_c", "humidity_pct", "co2_ppm"])
    low, high = PLAUSIBLE_BOUNDS[field]
    if rng.random() < 0.5:
        samples[-1][field] = round(low - rng.uniform(4.0, 20.0), 3)
    else:
        samples[-1][field] = round(high + rng.uniform(4.0, 1200.0), 3)
    return samples


BUILDERS = {
    "normal": stable_sequence,
    "temperature_high": build_temperature_high,
    "temperature_low": build_temperature_low,
    "humidity_high": build_humidity_high,
    "humidity_low": build_humidity_low,
    "co2_high": build_co2_high,
    "sensor_spike": build_sensor_spike,
    "sensor_drift": build_sensor_drift,
    "sensor_stuck": build_sensor_stuck,
    "sensor_dropout": build_sensor_dropout,
    "cross_variable_inconsistency": build_cross_variable_inconsistency,
    "out_of_range": build_out_of_range,
}


def generate_rows(rows_per_scenario: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows = []

    for anomaly_label in ANOMALY_LABELS:
        builder = BUILDERS[anomaly_label]
        for sample_index in range(rows_per_scenario):
            samples = builder(rng)
            features = extract_anomaly_features(samples)
            rows.append(
                {
                    **features,
                    "anomaly_label": anomaly_label,
                    "severity": ANOMALY_METADATA[anomaly_label]["severity"],
                    "scenario": anomaly_label,
                    "sequence_id": f"{anomaly_label}-{sample_index:04d}",
                }
            )

    rng.shuffle(rows)
    return rows


def write_dataset(rows: list[dict], output_path: Path) -> None:
    fieldnames = FEATURE_COLUMNS + [
        "anomaly_label",
        "severity",
        "scenario",
        "sequence_id",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a synthetic greenhouse anomaly dataset with rolling features."
    )
    parser.add_argument("--rows-per-scenario", type=int, default=ROWS_PER_SCENARIO)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = generate_rows(args.rows_per_scenario, args.seed)
    output_path = ensure_parent_dir(args.output)
    write_dataset(rows, output_path)
    print(f"Wrote {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
