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

    try:
        sensor.stop()
    except Exception:
        pass

    sensor.start()
    log_message(
        "Waiting for the SCD41 warm-up period ({} seconds)...".format(
            INITIAL_WARMUP_S
        )
    )
    time.sleep(INITIAL_WARMUP_S)
    retry_count = 0
    last_sample_ms = None

    while True:
        try:
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
                    log_i2c_scan(i2c)
                    restart_sensor(
                        sensor,
                        RECOVERY_WARMUP_S,
                        "Too many consecutive empty SCD41 reads. Restarting sensor.",
                    )
                    retry_count = 0
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
