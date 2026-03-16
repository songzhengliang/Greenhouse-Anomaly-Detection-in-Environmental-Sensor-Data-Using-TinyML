# Greenhouse-Anomaly-Detection-in-Environmental-Sensor-Data-Using-TinyML

This repository now supports a safer university-project demo direction:
sensor readings are converted into virtual greenhouse control actions on a local web dashboard,
instead of sending commands to real machines.

Board-side code is written for MicroPython on the ESP32-S3.
Laptop-side dashboard code runs with regular Python 3 because it hosts the webpage and API.

## What the dashboard does

- Reads temperature, humidity, and CO2 values.
- Decides whether the greenhouse should be heating, cooling, ventilating, or misting.
- Shows those decisions as virtual machine states on a webpage.
- Can run from manual inputs or replay rows from `greenhouse_air_quality_dataset.csv`.
- Lets you nudge or override live ESP32-S3 readings during a presentation.

## Action mapping

- Temperature high -> cooling / ventilation
- Temperature low -> heating
- Humidity high -> ventilation
- Humidity low -> misting
- CO2 high -> ventilation

## Run the dashboard

```bash
python3 dashboard_server.py
```

Then open `http://127.0.0.1:8000` on your laptop.

## Wireless ESP32-S3 to laptop flow

The laptop dashboard can now receive live sensor data over Wi-Fi from the ESP32-S3.

1. Start the server so it is reachable on your local network:

```bash
python3 dashboard_server.py --host 0.0.0.0 --port 8000
```

2. Find your laptop's local IP address on the same Wi-Fi network.
On macOS a common command is:

```bash
ipconfig getifaddr en0
```

3. Open `esp32_wifi_dashboard.py` and set:
- `WIFI_SSID`
- `WIFI_PASSWORD`
- `LAPTOP_IP`
- `I2C_SCL_PIN` / `I2C_SDA_PIN` if your ESP32-S3 wiring differs from the repo default

4. Copy `esp32_wifi_dashboard.py` and `scd41_driver.py` to the ESP32-S3 and run the client script.

These two files are the MicroPython side of the system.

5. In the webpage, press `Watch ESP32-S3 Feed` to follow live telemetry.

The ESP32-S3 posts readings to `POST /api/telemetry`, and the webpage reads the latest board state from `GET /api/live`.

## Presentation controls

While the live ESP32-S3 feed is running, the webpage now supports:

- quick `+` / `-` nudges for temperature, humidity, and CO2
- exact manual override values for all three live readings
- resetting offsets without disconnecting the board

This means you can present scenarios such as "too cold", "too humid", or "CO2 too high"
on demand, while still keeping the project framed as a safe virtual decision-support system.

## Main files

- `greenhouse_control.py`: reusable greenhouse decision logic
- `dashboard_server.py`: local HTTP server and JSON API
- `dashboard/`: webpage UI
- `esp32_wifi_dashboard.py`: MicroPython ESP32-S3 Wi-Fi client that sends live telemetry
- `scd41_driver.py`: reusable MicroPython SCD41 driver
- `scd41_test.py`: MicroPython sensor reading prototype
- `train_model.py`: desktop training/export prototype
