"""
ESP32-S3 MicroPython USB serial client for the greenhouse dashboard.

It reads the SCD41 sensor and emits structured serial lines that the
laptop dashboard server can parse over the current USB connection.
"""

from machine import Pin, I2C
import gc
import time

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
    print(SERIAL_EVENT_PREFIX + json.dumps(message))


def log_message(message, level="info"):
    emit_event(
        "log",
        {
            "level": level,
            "message": str(message),
        },
    )


def send_telemetry(co2, temperature, humidity):
    emit_event(
        "telemetry",
        {
            "temperature_c": round(float(temperature), 1),
            "humidity_pct": round(float(humidity), 1),
            "co2_ppm": int(co2),
            "sample_interval_s": SAMPLE_INTERVAL_S,
        },
    )
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
            log_message(
                "CO2={} ppm | Temperature={:.1f} C | Humidity={:.1f}%".format(
                    int(co2), temperature, humidity
                )
            )
            send_telemetry(co2, temperature, humidity)
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
