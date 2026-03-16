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


WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
LAPTOP_IP = "192.168.1.100"
SERVER_URL = "http://{}:8000/api/telemetry".format(LAPTOP_IP)
DEVICE_ID = "esp32-s3-greenhouse-1"

I2C_BUS = 0
# Default SCD41 wiring used elsewhere in this repo for ESP32-S3 boards.
# Change these if your specific ESP32-S3 board uses different pins.
I2C_SCL_PIN = 8
I2C_SDA_PIN = 9
I2C_FREQ = 100000
SAMPLE_INTERVAL_S = 30
WIFI_TIMEOUT_S = 20


def connect_wifi(ssid, password, timeout_s=WIFI_TIMEOUT_S):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("Wi-Fi already connected:", wlan.ifconfig())
        return wlan

    print("Connecting to Wi-Fi:", ssid)
    wlan.connect(ssid, password)

    started_ms = time.ticks_ms()
    timeout_ms = int(timeout_s * 1000)
    while time.ticks_diff(time.ticks_ms(), started_ms) < timeout_ms:
        if wlan.isconnected():
            print("Wi-Fi connected:", wlan.ifconfig())
            return wlan
        time.sleep(0.5)

    raise RuntimeError("Wi-Fi connection timed out")


def ensure_wifi(wlan):
    if wlan.isconnected():
        return wlan
    print("Wi-Fi dropped. Reconnecting...")
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
    client.connect(address)

    request = (
        "POST {path} HTTP/1.1\r\n"
        "Host: {host}\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: {length}\r\n"
        "Connection: close\r\n\r\n"
        "{body}"
    ).format(path=path, host=host, length=len(body), body=body)

    client.send(request.encode("utf-8"))

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
    print("Telemetry status:", status_code)

    if isinstance(response, dict):
        print("Dashboard mode:", response.get("mode", "unknown"))
        print("Decision:", response.get("summary", "No summary returned"))
    else:
        print("Dashboard response:", response)

    gc.collect()


def main():
    wlan = connect_wifi(WIFI_SSID, WIFI_PASSWORD)

    print("Initialising I2C...")
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
    print("Waiting for the SCD41 warm-up period (35 seconds)...")
    time.sleep(35)

    while True:
        try:
            wlan = ensure_wifi(wlan)
            reading = sensor.read()

            if not reading:
                print("Sensor data not ready. Retrying soon...")
                time.sleep(5)
                continue

            co2, temperature, humidity = reading
            print(
                "CO2={} ppm | Temperature={:.1f} C | Humidity={:.1f}%".format(
                    int(co2), temperature, humidity
                )
            )
            send_telemetry(wlan, co2, temperature, humidity)
            time.sleep(SAMPLE_INTERVAL_S)

        except KeyboardInterrupt:
            print("Stopping telemetry loop.")
            break
        except Exception as exc:
            print("Loop error:", exc)
            time.sleep(5)

    try:
        sensor.stop()
    except Exception:
        pass


if __name__ == "__main__":
    main()
