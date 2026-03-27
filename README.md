# Greenhouse Action Dashboard for ESP32-S3 + SCD41

This project turns live greenhouse sensor readings into virtual control decisions on a local web dashboard.
It is designed for a university demo where the system recommends actions such as heating, ventilation,
cooling, and misting, but does not directly control real machines.

The current repo supports two ways to connect the ESP32-S3 to the laptop:

1. USB serial mode
2. Wi-Fi mode

USB serial mode is the easiest way to get the system working the first time.

## Tested Hardware

- ESP32-S3 board running MicroPython
- Sensirion SCD41 CO2 / temperature / humidity sensor
- USB connection from the ESP32-S3 to the laptop

## What the Dashboard Does

- Reads temperature, humidity, and CO2 from the SCD41
- Decides whether the greenhouse should be heating, cooling, ventilating, or misting
- Shows those decisions as virtual machine states on a webpage
- Shows live board console messages
- Stores recent sensor history and renders 5-minute charts
- Lets you add presentation offsets or exact overrides during a demo

## Action Mapping

- Temperature high -> cooling / ventilation
- Temperature low -> heating
- Humidity high -> ventilation
- Humidity low -> misting
- CO2 high -> ventilation

## Recommended Setup

Use USB serial first.

Once USB mode is working, you can switch to Wi-Fi mode later if you want the board to be wireless.

## Hardware Wiring

This repo is currently configured for the same wiring used in the project:

- `ESP32-S3 GPIO 8` -> `SCD41 SCL`
- `ESP32-S3 GPIO 9` -> `SCD41 SDA`
- `ESP32-S3 3V3` -> `SCD41 VCC`
- `ESP32-S3 GND` -> `SCD41 GND`

If your wiring is different, change these values in `board_config.py`:

- `I2C_SCL_PIN`
- `I2C_SDA_PIN`
- `I2C_BUS`
- `I2C_FREQ`

## Laptop Requirements

Install Python 3.

If `pyserial` is missing on your laptop, install it:

```bash
python3 -m pip install pyserial
```

## Important Files

- `dashboard_server.py`: laptop HTTP server and USB serial bridge
- `start_everything.py`: one-command launcher for the laptop side
- `upload_to_board.py`: board file synchronizer used by `start_everything.py`
- `dashboard/`: webpage files
- `board_config.example.py`: template config for the board
- `board_config.py`: real board config used by the ESP32-S3
- `esp32_usb_dashboard.py`: MicroPython board program for USB serial mode
- `esp32_wifi_dashboard.py`: MicroPython board program for Wi-Fi mode
- `scd41_driver.py`: MicroPython SCD41 driver
- `main.py`: board startup file that currently launches USB mode

## Quick Start With `start_everything.py`

This is the recommended way to launch the whole system.

From the project folder, run:

```bash
python3 start_everything.py
```

What happens next:

1. the script checks whether the ESP32-S3 is connected
2. if the board is found, it compares the local board files with the copies on the board
3. if files are missing or outdated, it uploads the changed files automatically
4. if anything changed, it soft-resets the board so the new code starts
5. it launches the dashboard server on your laptop
6. it opens the dashboard in your browser

If the board is not connected yet, the script still starts the server and leaves it waiting for the ESP32-S3.

Useful options:

```bash
python3 start_everything.py --skip-board-sync
python3 start_everything.py --skip-board-config
python3 start_everything.py --board-mode wifi
python3 start_everything.py --port 8010
python3 start_everything.py --emlearn-trees /path/to/emlearn_trees.py
```

Notes:

- `--skip-board-sync` keeps the old behavior and starts the server without checking the board files first
- `--skip-board-config` avoids overwriting `board_config.py` on the board
- `--board-mode wifi` makes the generated `main.py` boot the Wi-Fi board client instead of the USB one
- if port `8000` is already busy, use `--port 8010` or stop the existing server first
- if the script warns about `emlearn_trees.py`, either pass it with `--emlearn-trees` or make sure the board already has that file

## Step 1: Prepare the Board Config

Create `board_config.py` from `board_config.example.py`.

The file contains both USB-mode settings and Wi-Fi-mode settings.

For USB mode, the important fields are:

- `DEVICE_ID`
- `I2C_BUS`
- `I2C_SCL_PIN`
- `I2C_SDA_PIN`
- `I2C_FREQ`
- `SAMPLE_INTERVAL_S`

For Wi-Fi mode, these fields also matter:

- `WIFI_SSID`
- `WIFI_PASSWORD`
- `SERVER_HOST`
- `SERVER_PORT`

## Step 2: Put the Files on the ESP32-S3

Use a MicroPython IDE such as Thonny.

If you use `python3 start_everything.py`, this manual upload step is optional because the launcher can sync the board files for you automatically.

Select:

- Interpreter: `MicroPython (ESP32)`
- Port: your ESP32-S3 serial port

Upload these files to the board:

- `board_config.py`
- `scd41_driver.py`
- `esp32_usb_dashboard.py`
- `main.py`

The current `main.py` is:

```python
import esp32_usb_dashboard

esp32_usb_dashboard.main()
```

That means the board will start in USB serial mode whenever it boots.

## Step 3: Close the IDE Serial Connection

This step is important.

The laptop dashboard server needs exclusive access to the board's USB serial port.
If Thonny or another serial monitor is still connected, the dashboard server will not be able to read live data.

After uploading the files:

1. Stop any running script in the IDE
2. Close the IDE shell or serial connection
3. Leave the board plugged in over USB

## Step 4: Start the Dashboard Server

The fastest way is:

```bash
python3 start_everything.py
```

That launcher will:

- open the dashboard in your browser
- check whether the board files are already current
- upload changed or missing board files before launch
- soft-reset the board only if files actually changed
- start the laptop server
- auto-detect the ESP32-S3 USB serial port
- keep waiting if the board is not visible yet

The normal command is:

```bash
python3 start_everything.py
```

If you do not want the automatic board file check for one run, use:

```bash
python3 start_everything.py --skip-board-sync
```

If you want the manual command instead, run:

```bash
python3 dashboard_server.py --serial-port /dev/cu.usbmodem2101
```

If your laptop uses a different serial device path, replace `/dev/cu.usbmodem2101` with the correct one.

If auto-detection works on your system, this also works:

```bash
python3 dashboard_server.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Step 5: Boot the Board

Press the `EN` or `RST` button on the ESP32-S3 once.

Do not hold the `BOOT` button.

The board will:

1. start `main.py`
2. launch `esp32_usb_dashboard.py`
3. initialize I2C
4. start the SCD41
5. wait for the 35-second SCD41 warm-up period
6. begin sending live readings every 30 seconds

## Step 6: Watch the Dashboard

On the webpage:

1. open the dashboard
2. click `Watch ESP32-S3 Feed`

You should see:

- live temperature, humidity, and CO2 values
- 5-minute line charts
- board console messages in the `Board Console` section
- virtual machine states changing based on the live readings

## What Success Looks Like

Once the system is working, the page will show:

- a connected live feed
- the board device id
- recent board console messages
- current live greenhouse values
- virtual machine states such as `heating`, `ventilating`, `cooling`, or `misting`

## USB Serial Workflow Summary

This is the shortest working path:

1. make sure local `board_config.py` is ready
2. plug in the ESP32-S3 over USB
3. close the IDE serial connection
4. run `python3 start_everything.py`
5. let the launcher sync the board files if needed
6. if the board was not reset automatically, press `EN` or `RST`
7. wait 35 seconds
8. open `http://127.0.0.1:8000`
9. click `Watch ESP32-S3 Feed`

## Optional Wi-Fi Workflow

If you want the board to communicate wirelessly instead of over USB:

1. edit `board_config.py`
2. set:
   - `WIFI_SSID`
   - `WIFI_PASSWORD`
   - `SERVER_HOST`
   - `SERVER_PORT`
3. upload:
   - `board_config.py`
   - `scd41_driver.py`
   - `esp32_wifi_dashboard.py`
4. change `main.py` on the board to:

```python
import esp32_wifi_dashboard

esp32_wifi_dashboard.main()
```

5. run the server on the laptop:

```bash
python3 dashboard_server.py --host 0.0.0.0 --port 8000
```

6. make sure the laptop and ESP32-S3 are on the same network
7. open the dashboard and click `Watch ESP32-S3 Feed`

## Presentation Controls

While the live board feed is running, the webpage also supports:

- plus and minus offset nudges for temperature, humidity, and CO2
- exact override values
- live charts for the last 5 minutes
- virtual machine status cards at the bottom of the page

This is useful for presentations because you can demonstrate greenhouse decisions safely
without actually turning on real machines.

## Troubleshooting

### The dashboard shows no live data

Check these in order:

1. make sure the board is powered and connected over USB
2. make sure the IDE is closed or disconnected from the board
3. make sure `dashboard_server.py` is running
4. make sure the correct serial port is being used
5. press `EN` or `RST` once
6. wait at least 35 seconds for the SCD41 warm-up

### The board enters download mode

If you see text like `waiting for download`, the board is in the ESP32 ROM bootloader.

To recover:

1. release the `BOOT` button if it is pressed
2. press `EN` or `RST` once
3. do not hold `BOOT`
4. try again

### The server cannot open the serial port

That usually means another app is already using the board.

Close:

- Thonny shell
- another serial monitor
- another dashboard server instance

Then start the server again.

### The sensor values never change

Check:

1. `SCL` really goes to `GPIO 8`
2. `SDA` really goes to `GPIO 9`
3. power and ground are correct
4. the SCD41 has had enough warm-up time

## Main Files

- `greenhouse_control.py`: greenhouse decision engine
- `dashboard_server.py`: laptop server and USB serial bridge
- `dashboard/`: webpage UI
- `esp32_usb_dashboard.py`: MicroPython USB serial board program
- `esp32_wifi_dashboard.py`: MicroPython Wi-Fi board program
- `scd41_driver.py`: SCD41 driver for MicroPython
- `board_config.py`: board-specific configuration
- `main.py`: current startup file for USB mode
- `train_model.py`: desktop training and export prototype
