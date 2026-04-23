"""
ESP32-S3 MicroPython client for the laptop greenhouse dashboard.

It reads the SCD41 sensor and sends live telemetry to:
http://<laptop-ip>:8000/api/telemetry
"""

from machine import Pin, I2C
import gc
import network
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

try:
    import urequests
except ImportError:
    urequests = None

try:
    import usocket as socket
except ImportError:
    import socket


WIFI_SSID = getattr(config, "WIFI_SSID", "YOUR_WIFI_NAME")
WIFI_PASSWORD = getattr(config, "WIFI_PASSWORD", "YOUR_WIFI_PASSWORD")
SERVER_HOST = getattr(config, "SERVER_HOST", "YOUR_LAPTOP_IP")
SERVER_PORT = int(getattr(config, "SERVER_PORT", 8000))
SERVER_URL = "http://{}:{}/api/telemetry".format(SERVER_HOST, SERVER_PORT)
BOARD_LOG_URL = "http://{}:{}/api/board/log".format(SERVER_HOST, SERVER_PORT)
DEVICE_ID = getattr(config, "DEVICE_ID", "esp32-s3-greenhouse-1")

I2C_BUS = int(getattr(config, "I2C_BUS", 0))
# Default SCD41 wiring used elsewhere in this repo for ESP32-S3 boards.
# Change these if your specific ESP32-S3 board uses different pins.
I2C_SCL_PIN = int(getattr(config, "I2C_SCL_PIN", 8))
I2C_SDA_PIN = int(getattr(config, "I2C_SDA_PIN", 9))
I2C_FREQ = int(getattr(config, "I2C_FREQ", 100000))
SAMPLE_INTERVAL_S = int(getattr(config, "SAMPLE_INTERVAL_S", 40))
WIFI_TIMEOUT_S = int(getattr(config, "WIFI_TIMEOUT_S", 20))
HTTP_TIMEOUT_S = int(getattr(config, "HTTP_TIMEOUT_S", 10))
MEASUREMENT_MODE = str(getattr(config, "MEASUREMENT_MODE", "low_power")).strip().lower()


def config_is_placeholder(value):
    text = str(value).strip()
    if not text:
        return True
    if text.startswith("YOUR_"):
        return True
    return False


def validate_config():
    if config_is_placeholder(WIFI_SSID):
        raise RuntimeError("Set WIFI_SSID in board_config.py before running.")
    if config_is_placeholder(WIFI_PASSWORD):
        raise RuntimeError("Set WIFI_PASSWORD in board_config.py before running.")
    if config_is_placeholder(SERVER_HOST):
        raise RuntimeError("Set SERVER_HOST in board_config.py before running.")


def normalized_measurement_mode():
    if MEASUREMENT_MODE in ("low_power", "low-power", "lowpower"):
        return "low_power"
    return "standard"


def measurement_startup_delay_s():
    if normalized_measurement_mode() == "low_power":
        return 35
    return max(5, SAMPLE_INTERVAL_S)


def not_ready_retry_delay_s():
    return 1 if SAMPLE_INTERVAL_S <= 5 else min(5, max(1, SAMPLE_INTERVAL_S // 3))


def connect_wifi(ssid, password, timeout_s=WIFI_TIMEOUT_S):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        log_message("Wi-Fi already connected: {}".format(wlan.ifconfig()))
        return wlan

    log_message("Connecting to Wi-Fi: {}".format(ssid), remote=False)
    wlan.connect(ssid, password)

    started_ms = time.ticks_ms()
    timeout_ms = int(timeout_s * 1000)
    while time.ticks_diff(time.ticks_ms(), started_ms) < timeout_ms:
        if wlan.isconnected():
            log_message("Wi-Fi connected: {}".format(wlan.ifconfig()))
            return wlan
        time.sleep(0.5)

    raise RuntimeError("Wi-Fi connection timed out")


def ensure_wifi(wlan):
    if wlan.isconnected():
        return wlan
    log_message("Wi-Fi dropped. Reconnecting...", level="warning", remote=False)
    return connect_wifi(WIFI_SSID, WIFI_PASSWORD)


def parse_http_url(url):
    if not url.startswith("http://"):
        raise ValueError("Only http:// URLs are supported in this script")

    remainder = url[7:]
    host_port, _, path = remainder.partition("/")
    path = "/" + path if path else "/"

    if ":" in host_port:
        host, port_text = host_port.split(":", 1)
        port = int(port_text)
    else:
        host = host_port
        port = 80

    return host, port, path


def socket_send_all(client, payload):
    if hasattr(client, "sendall"):
        client.sendall(payload)
        return

    total_sent = 0
    while total_sent < len(payload):
        sent = client.send(payload[total_sent:])
        if not sent:
            raise OSError("socket send failed")
        total_sent += sent


def post_json(url, payload):
    body = json.dumps(payload)

    if urequests is not None:
        response = urequests.post(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            text = response.text
            try:
                return response.status_code, json.loads(text)
            except Exception:
                return response.status_code, text
        finally:
            response.close()

    host, port, path = parse_http_url(url)
    address = socket.getaddrinfo(host, port)[0][-1]
    client = socket.socket()
    if hasattr(client, "settimeout"):
        client.settimeout(HTTP_TIMEOUT_S)
    client.connect(address)

    request = (
        "POST {path} HTTP/1.1\r\n"
        "Host: {host}:{port}\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: {length}\r\n"
        "Connection: close\r\n\r\n"
        "{body}"
    ).format(path=path, host=host, port=port, length=len(body), body=body)

    socket_send_all(client, request.encode("utf-8"))

    chunks = []
    while True:
        data = client.recv(256)
        if not data:
            break
        chunks.append(data)

    client.close()
    raw_response = b"".join(chunks)
    headers, _, response_body = raw_response.partition(b"\r\n\r\n")

    try:
        status_code = int(headers.split(None, 2)[1])
    except Exception:
        status_code = 0

    text = response_body.decode("utf-8")
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = text
    return status_code, parsed


def post_board_log(message, level="info"):
    payload = {
        "device_id": DEVICE_ID,
        "level": level,
        "message": str(message),
    }
    return post_json(BOARD_LOG_URL, payload)


def log_message(message, level="info", remote=True):
    text = str(message)
    print(text)

    if not remote:
        return

    try:
        post_board_log(text, level=level)
    except Exception:
        pass


def send_telemetry(wlan, co2, temperature, humidity):
    payload = {
        "device_id": DEVICE_ID,
        "temperature_c": round(float(temperature), 1),
        "humidity_pct": round(float(humidity), 1),
        "co2_ppm": int(co2),
        "sample_interval_s": SAMPLE_INTERVAL_S,
        "ip_address": wlan.ifconfig()[0],
    }

    try:
        payload["signal_strength_dbm"] = wlan.status("rssi")
    except Exception:
        pass

    status_code, response = post_json(SERVER_URL, payload)

    if isinstance(response, dict):
        log_message(
            "Telemetry status: {} | Dashboard mode: {} | Decision: {}".format(
                status_code,
                response.get("mode", "unknown"),
                response.get("summary", "No summary returned"),
            )
        )
    else:
        log_message(
            "Telemetry status: {} | Dashboard response: {}".format(
                status_code, response
            )
        )

    gc.collect()


def main():
    validate_config()
    wlan = connect_wifi(WIFI_SSID, WIFI_PASSWORD)
    log_message(
        "Server target: http://{}:{} | Device ID: {}".format(
            SERVER_HOST, SERVER_PORT, DEVICE_ID
        )
    )
    log_message("ESP32-S3 connected. Sensor warm-up is starting.")

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

    mode = normalized_measurement_mode()
    sensor.start(low_power=(mode == "low_power"))
    startup_delay_s = measurement_startup_delay_s()
    log_message(
        "Waiting for the SCD41 warm-up period ({} seconds)...".format(startup_delay_s)
    )
    time.sleep(startup_delay_s)

    while True:
        try:
            wlan = ensure_wifi(wlan)
            reading = sensor.read()

            if not reading:
                log_message("Sensor data not ready. Retrying soon...", level="warning")
                time.sleep(not_ready_retry_delay_s())
                continue

            co2, temperature, humidity = reading
            log_message(
                "CO2={} ppm | Temperature={:.1f} C | Humidity={:.1f}%".format(
                    int(co2), temperature, humidity
                )
            )
            send_telemetry(wlan, co2, temperature, humidity)
            time.sleep(SAMPLE_INTERVAL_S)

        except KeyboardInterrupt:
            log_message("Stopping telemetry loop.", remote=False)
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
