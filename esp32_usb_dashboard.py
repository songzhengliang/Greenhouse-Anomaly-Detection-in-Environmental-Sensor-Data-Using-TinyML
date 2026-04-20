"""
ESP32-S3 MicroPython USB serial client for the greenhouse dashboard.

It reads the SCD41 sensor and emits structured serial lines that the
laptop dashboard server can parse over the current USB connection.
"""

import gc
import sys
import time
from machine import Pin, I2C

from board_ai_runtime import BoardAiRuntime
from scd41_driver import SCD41

try:
    import board_config as config
except ImportError:
    config = None

try:
    import ujson as json
except ImportError:
    import json


SERIAL_EVENT_PREFIX = "GHUSB "
SERIAL_TELEMETRY_PREFIX = "GHTLM "
DEVICE_ID = getattr(config, "DEVICE_ID", "esp32-s3-greenhouse-1")

I2C_BUS = int(getattr(config, "I2C_BUS", 0))
I2C_SCL_PIN = int(getattr(config, "I2C_SCL_PIN", 8))
I2C_SDA_PIN = int(getattr(config, "I2C_SDA_PIN", 9))
I2C_FREQ = int(getattr(config, "I2C_FREQ", 100000))
SAMPLE_INTERVAL_S = int(getattr(config, "SAMPLE_INTERVAL_S", 30))
INITIAL_WARMUP_S = int(getattr(config, "INITIAL_WARMUP_S", 35))
RECOVERY_WARMUP_S = int(getattr(config, "RECOVERY_WARMUP_S", 35))
SENSOR_RESTART_DELAY_S = float(getattr(config, "SENSOR_RESTART_DELAY_S", 1))
MAX_NOT_READY_RETRIES = int(getattr(config, "MAX_NOT_READY_RETRIES", 3))
MEASUREMENT_MODE = str(getattr(config, "MEASUREMENT_MODE", "low_power")).strip().lower()
SENSOR_FAILURE_BACKOFF_S = int(getattr(config, "SENSOR_FAILURE_BACKOFF_S", 60))
MODE_READY_TIMEOUTS = {
    "low_power": max(35, INITIAL_WARMUP_S),
    "standard": 12,
    "single_shot": 12,
}


def emit_event(kind, payload):
    message = {
        "kind": kind,
        "device_id": DEVICE_ID,
    }
    message.update(payload)
    sys.stdout.write(SERIAL_EVENT_PREFIX + json.dumps(message) + "\n")
    try:
        sys.stdout.flush()
    except Exception:
        pass


def emit_line(text):
    sys.stdout.write(text + "\n")
    try:
        sys.stdout.flush()
    except Exception:
        pass


def log_message(message, level="info"):
    emit_event(
        "log",
        {
            "level": level,
            "message": str(message),
        },
    )


def compact_board_result(board_result):
    compact_actions = []
    for action in board_result.get("actions", []):
        compact_actions.append(
            {
                "key": action.get("key"),
                "active": bool(action.get("active", False)),
                "confidence": round(float(action.get("confidence", 0.0)), 3),
            }
        )

    anomaly = board_result.get("anomaly", {})
    compact_predictions = []
    for item in anomaly.get("top_predictions", [])[:3]:
        compact_predictions.append(
            {
                "label": item.get("label", "normal"),
                "confidence": round(float(item.get("confidence", 0.0)), 3),
            }
        )

    return {
        "format": "compact_v1",
        "decision_engine": board_result.get("decision_engine", "board_on_device_ai"),
        "model_available": bool(board_result.get("model_available", True)),
        "on_device": True,
        "actions": compact_actions,
        "anomaly": {
            "label": anomaly.get("label", "normal"),
            "confidence": round(float(anomaly.get("confidence", 0.0)), 3),
            "anomaly_score": round(float(anomaly.get("anomaly_score", 0.0)), 3),
            "decision_engine": anomaly.get("decision_engine", "board_anomaly_ai"),
            "model_available": bool(anomaly.get("model_available", True)),
            "history_ready": bool(anomaly.get("history_ready", False)),
            "window_size": int(anomaly.get("window_size", 6)),
            "top_predictions": compact_predictions,
        },
    }


def _confidence_milli(value):
    return int(round(float(value) * 1000))


def format_sample_log(co2, temperature, humidity, board_result):
    active_actions = [
        action["status"]
        for action in board_result.get("actions", [])
        if action.get("active")
    ]
    action_text = ", ".join(active_actions) if active_actions else "idle"
    anomaly = board_result.get("anomaly", {})
    return (
        "CO2={co2} ppm | Temperature={temperature:.1f} C | Humidity={humidity:.1f}% | "
        "Action={action} | Anomaly={anomaly}"
    ).format(
        co2=int(co2),
        temperature=float(temperature),
        humidity=float(humidity),
        action=action_text,
        anomaly=anomaly.get("display_label", "No anomaly"),
    )


def send_telemetry(co2, temperature, humidity, board_result, gap_seconds):
    compact = compact_board_result(board_result)
    actions_by_key = {
        item["key"]: item
        for item in compact["actions"]
    }
    anomaly = compact["anomaly"]
    fields = [
        SERIAL_TELEMETRY_PREFIX.rstrip(),
        DEVICE_ID,
        "{:.1f}".format(float(temperature)),
        "{:.1f}".format(float(humidity)),
        str(int(co2)),
        "{:.1f}".format(float(gap_seconds)),
        "1" if actions_by_key.get("heater", {}).get("active") else "0",
        str(_confidence_milli(actions_by_key.get("heater", {}).get("confidence", 0.0))),
        "1" if actions_by_key.get("cooling_fan", {}).get("active") else "0",
        str(_confidence_milli(actions_by_key.get("cooling_fan", {}).get("confidence", 0.0))),
        "1" if actions_by_key.get("ventilation", {}).get("active") else "0",
        str(_confidence_milli(actions_by_key.get("ventilation", {}).get("confidence", 0.0))),
        "1" if actions_by_key.get("mister", {}).get("active") else "0",
        str(_confidence_milli(actions_by_key.get("mister", {}).get("confidence", 0.0))),
        str(anomaly.get("label", "normal")),
        str(_confidence_milli(anomaly.get("confidence", 0.0))),
        str(_confidence_milli(anomaly.get("anomaly_score", 0.0))),
        str(anomaly.get("decision_engine", "board_anomaly_ai")),
        "1" if anomaly.get("history_ready") else "0",
        str(int(anomaly.get("window_size", 6))),
    ]
    emit_line("|".join(fields))
    gc.collect()


def log_i2c_scan(i2c):
    try:
        devices = [hex(device) for device in i2c.scan()]
        if devices:
            log_message("I2C scan found devices: {}".format(", ".join(devices)))
        else:
            log_message("I2C scan found no devices.", level="warning")
    except Exception as exc:
        log_message("I2C scan failed: {}".format(exc), level="error")


def normalize_measurement_mode(mode):
    text = str(mode or "low_power").strip().lower()
    if text in ("standard", "standard_periodic", "periodic"):
        return "standard"
    if text in ("single", "single_shot", "single-shot", "oneshot", "one_shot"):
        return "single_shot"
    return "low_power"


def measurement_mode_plan(preferred_mode):
    preferred = normalize_measurement_mode(preferred_mode)
    plan = []
    for mode in (preferred, "standard", "single_shot"):
        if mode not in plan:
            plan.append(mode)
    return plan


def start_measurement_mode(sensor, mode):
    if mode == "standard":
        sensor.start_standard_periodic()
        return
    if mode == "single_shot":
        sensor.start_single_shot()
        return
    sensor.start_low_power()


def wait_for_ready(sensor, timeout_s):
    deadline = time.time() + max(1.0, float(timeout_s))
    last_status = None
    while time.time() < deadline:
        status = sensor.data_ready_status()
        if status:
            return True, status
        last_status = status
        time.sleep(1)
    return False, last_status


def initialize_sensor_mode(sensor, i2c, preferred_mode):
    log_i2c_scan(i2c)
    for mode in measurement_mode_plan(preferred_mode):
        try:
            sensor.wake_up()
        except Exception:
            pass
        try:
            sensor.stop()
        except Exception:
            pass
        time.sleep(SENSOR_RESTART_DELAY_S)
        start_measurement_mode(sensor, mode)
        timeout_s = MODE_READY_TIMEOUTS[mode]
        if mode == "low_power":
            log_message("Waiting for the SCD41 warm-up period ({} seconds)...".format(timeout_s))
        else:
            log_message(
                "Trying SCD41 {} mode for up to {} seconds...".format(
                    mode.replace("_", " "),
                    timeout_s,
                ),
                level="warning",
            )
        ready, status = wait_for_ready(sensor, timeout_s)
        if ready:
            log_message("SCD41 measurement mode ready: {}.".format(mode.replace("_", " ")))
            return mode
        log_message(
            "SCD41 {} mode did not produce a ready sample. Last status: {}.".format(
                mode.replace("_", " "),
                "crc/error" if status is None else status,
            ),
            level="warning",
        )

    log_message(
        "SCD41 seen on I2C but never became ready in low power, standard, or single-shot mode. Check sensor power, wiring quality, or hardware.",
        level="error",
    )
    return None


def restart_sensor(sensor, wait_s, reason):
    log_message(reason, level="warning")
    try:
        sensor.stop()
    except Exception:
        pass

    time.sleep(SENSOR_RESTART_DELAY_S)
    sensor.start()
    log_message(
        "Waiting {} seconds for SCD41 warm-up after restart.".format(wait_s)
    )
    time.sleep(wait_s)


def main():
    log_message("ESP32-S3 USB dashboard mode starting.")
    log_message("Initialising I2C...")

    i2c = I2C(
        I2C_BUS,
        scl=Pin(I2C_SCL_PIN),
        sda=Pin(I2C_SDA_PIN),
        freq=I2C_FREQ,
    )
    log_i2c_scan(i2c)

    sensor = SCD41(i2c)
    log_message("Loading on-device AI models...")
    board_ai = BoardAiRuntime()
    log_message("On-device AI models loaded.")
    active_mode = initialize_sensor_mode(sensor, i2c, MEASUREMENT_MODE)
    retry_count = 0
    last_sample_ms = None

    while True:
        try:
            if active_mode is None:
                log_message(
                    "SCD41 is still not producing measurements. Retrying full sensor recovery in {} seconds.".format(
                        SENSOR_FAILURE_BACKOFF_S
                    ),
                    level="error",
                )
                time.sleep(SENSOR_FAILURE_BACKOFF_S)
                active_mode = initialize_sensor_mode(sensor, i2c, MEASUREMENT_MODE)
                retry_count = 0
                last_sample_ms = None
                continue

            if active_mode == "single_shot":
                start_measurement_mode(sensor, active_mode)
                ready, status = wait_for_ready(sensor, MODE_READY_TIMEOUTS["single_shot"])
                if not ready:
                    log_message(
                        "Single-shot measurement did not become ready. Last status: {}.".format(
                            "crc/error" if status is None else status
                        ),
                        level="warning",
                    )
                    active_mode = initialize_sensor_mode(sensor, i2c, MEASUREMENT_MODE)
                    retry_count = 0
                    last_sample_ms = None
                    continue

            reading = sensor.read()

            if not reading:
                retry_count += 1
                log_message(
                    "Sensor data not ready. Retrying soon... ({}/{})".format(
                        retry_count, MAX_NOT_READY_RETRIES
                    ),
                    level="warning",
                )
                if retry_count >= MAX_NOT_READY_RETRIES:
                    status = sensor.data_ready_status()
                    log_message(
                        "Too many consecutive empty SCD41 reads. Reinitialising the measurement mode. Last ready status: {}.".format(
                            "crc/error" if status is None else status
                        ),
                        level="warning",
                    )
                    active_mode = initialize_sensor_mode(sensor, i2c, MEASUREMENT_MODE)
                    retry_count = 0
                    last_sample_ms = None
                else:
                    time.sleep(5)
                continue

            co2, temperature, humidity = reading
            retry_count = 0
            now_ms = time.ticks_ms()
            if last_sample_ms is None:
                gap_seconds = SAMPLE_INTERVAL_S
            else:
                gap_seconds = time.ticks_diff(now_ms, last_sample_ms) / 1000.0
            last_sample_ms = now_ms
            board_result = board_ai.update(
                temperature_c=temperature,
                humidity_pct=humidity,
                co2_ppm=co2,
                gap_seconds=gap_seconds,
            )
            log_message(format_sample_log(co2, temperature, humidity, board_result))
            send_telemetry(co2, temperature, humidity, board_result, gap_seconds)
            time.sleep(SAMPLE_INTERVAL_S)

        except KeyboardInterrupt:
            log_message("Stopping USB telemetry loop.")
            break
        except Exception as exc:
            log_message("Loop error: {}".format(exc), level="error")
            time.sleep(5)

    try:
        sensor.stop()
    except Exception:
        pass


if __name__ == "__main__":
    main()
