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


def main():
    log_message("ESP32-S3 USB dashboard mode starting.")
    log_message("Initialising I2C...")

    i2c = I2C(
        I2C_BUS,
        scl=Pin(I2C_SCL_PIN),
        sda=Pin(I2C_SDA_PIN),
        freq=I2C_FREQ,
    )

    sensor = SCD41(i2c)

    try:
        sensor.stop()
    except Exception:
        pass

    sensor.start()
    log_message("Waiting for the SCD41 warm-up period (35 seconds)...")
    time.sleep(35)

    while True:
        try:
            reading = sensor.read()

            if not reading:
                log_message("Sensor data not ready. Retrying soon...", level="warning")
                time.sleep(5)
                continue

            co2, temperature, humidity = reading
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
