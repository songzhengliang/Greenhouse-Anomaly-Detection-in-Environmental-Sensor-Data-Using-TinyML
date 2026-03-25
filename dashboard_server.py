from __future__ import annotations

import argparse
import copy
import csv
import json
import threading
import time
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from ai_greenhouse_control import evaluate_greenhouse_ai
from greenhouse_anomaly_detection import (
    NOMINAL_SAMPLE_INTERVAL_S,
    evaluate_greenhouse_anomaly_ai,
)
from greenhouse_control import Thresholds
from presentation_presets import (
    get_presentation_preset,
    presentation_preset_catalog,
)

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

ROOT = Path(__file__).resolve().parent
DASHBOARD_DIR = ROOT / "dashboard"
DATASET_FILE = ROOT / "greenhouse_action_control_dataset.csv"
LIVE_TIMEOUT_SECONDS = 75
BOARD_LOG_LIMIT = 200
DEFAULT_SERIAL_BAUD = 115200
SERIAL_EVENT_PREFIX = "GHUSB "
ANOMALY_HISTORY_LIMIT = 18
DEFAULT_LIVE_SENSORS = {
    "temperature_c": 24.0,
    "humidity_pct": 60.0,
    "co2_ppm": 900,
}
STATE_RANK = {"stable": 0, "warning": 1, "critical": 2}

LIVE_STATE_LOCK = threading.Lock()
LIVE_STATE = {
    "raw_sensors": None,
    "thresholds": None,
    "device_id": None,
    "received_at": None,
    "board_result": None,
}
PRESENTATION_STATE_LOCK = threading.Lock()
PRESENTATION_STATE = {
    "offsets": {
        "temperature_c": 0.0,
        "humidity_pct": 0.0,
        "co2_ppm": 0,
    },
    "override": None,
}
BOARD_LOG_LOCK = threading.Lock()
BOARD_LOGS = []
SERIAL_BRIDGE = None
MODE_HISTORY_LOCK = threading.Lock()
MODE_SENSOR_HISTORY = {
    "live": [],
    "manual": [],
    "demo": [],
    "preset": [],
}


def waiting_actions() -> list[dict]:
    return [
        {
            "key": "heater",
            "label": "Heater",
            "status": "idle",
            "active": False,
            "reason": "Waiting for the first on-device AI decision from the ESP32-S3.",
        },
        {
            "key": "cooling_fan",
            "label": "Cooling Fan",
            "status": "idle",
            "active": False,
            "reason": "Waiting for the first on-device AI decision from the ESP32-S3.",
        },
        {
            "key": "ventilation",
            "label": "Ventilation",
            "status": "idle",
            "active": False,
            "reason": "Waiting for the first on-device AI decision from the ESP32-S3.",
        },
        {
            "key": "mister",
            "label": "Misting System",
            "status": "idle",
            "active": False,
            "reason": "Waiting for the first on-device AI decision from the ESP32-S3.",
        },
    ]


def waiting_anomaly() -> dict:
    return {
        "label": "normal",
        "display_label": "No anomaly",
        "severity": "stable",
        "summary": "On-device AI anomaly watch is waiting for live board history.",
        "detail": "The ESP32-S3 will report anomalies after its first real samples arrive.",
        "confidence": 1.0,
        "anomaly_score": 0.0,
        "decision_engine": "waiting_for_board_ai",
        "model_available": False,
        "history_ready": False,
        "window_size": 6,
        "top_predictions": [
            {
                "label": "normal",
                "display_label": "No anomaly",
                "confidence": 1.0,
            }
        ],
    }


def load_demo_rows() -> list[dict]:
    if not DATASET_FILE.exists():
        return [
            {"temperature_c": 17.0, "humidity_pct": 41.0, "co2_ppm": 860},
            {"temperature_c": 31.5, "humidity_pct": 79.0, "co2_ppm": 1520},
            {"temperature_c": 24.0, "humidity_pct": 60.0, "co2_ppm": 930},
        ]

    rows = []
    with DATASET_FILE.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "temperature_c": float(row["temperature_c"]),
                    "humidity_pct": float(row["humidity_pct"]),
                    "co2_ppm": float(row["co2_ppm"]),
                }
            )
    return rows


def guess_content_type(path: Path) -> str:
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "application/javascript; charset=utf-8"
    return "text/html; charset=utf-8"


def normalize_sensors(temperature_c: float, humidity_pct: float, co2_ppm: float) -> dict:
    return {
        "temperature_c": round(float(temperature_c), 1),
        "humidity_pct": round(min(max(float(humidity_pct), 0.0), 100.0), 1),
        "co2_ppm": max(0, int(round(float(co2_ppm)))),
    }


def normalize_offsets(raw: dict | None) -> dict:
    raw = raw or {}
    return {
        "temperature_c": round(float(raw.get("temperature_c", 0.0)), 1),
        "humidity_pct": round(float(raw.get("humidity_pct", 0.0)), 1),
        "co2_ppm": int(round(float(raw.get("co2_ppm", 0)))),
    }


def normalize_override(raw: dict | None) -> dict | None:
    if not raw:
        return None
    return normalize_sensors(
        raw["temperature_c"],
        raw["humidity_pct"],
        raw["co2_ppm"],
    )


def presentation_is_active(presentation_state: dict) -> bool:
    offsets = presentation_state["offsets"]
    has_offsets = any(bool(value) for value in offsets.values())
    return has_offsets or presentation_state["override"] is not None


def promote_state(current: str, incoming: str) -> str:
    return incoming if STATE_RANK.get(incoming, 0) > STATE_RANK.get(current, 0) else current


def apply_presentation_controls(raw_sensors: dict, presentation_state: dict) -> dict:
    override = presentation_state["override"]
    if override is not None:
        return copy.deepcopy(override)

    offsets = presentation_state["offsets"]
    return normalize_sensors(
        raw_sensors["temperature_c"] + offsets["temperature_c"],
        raw_sensors["humidity_pct"] + offsets["humidity_pct"],
        raw_sensors["co2_ppm"] + offsets["co2_ppm"],
    )


def presentation_offsets_for_history(raw_sensors: dict, presentation_state: dict) -> dict:
    override = presentation_state["override"]
    if override is not None:
        return {
            "temperature_c": round(override["temperature_c"] - raw_sensors["temperature_c"], 1),
            "humidity_pct": round(override["humidity_pct"] - raw_sensors["humidity_pct"], 1),
            "co2_ppm": int(round(override["co2_ppm"] - raw_sensors["co2_ppm"])),
        }
    return copy.deepcopy(presentation_state["offsets"])


def apply_offsets_to_history_sample(sample: dict, offsets: dict) -> dict:
    adjusted = normalize_sensors(
        sample["temperature_c"] + offsets["temperature_c"],
        sample["humidity_pct"] + offsets["humidity_pct"],
        sample["co2_ppm"] + offsets["co2_ppm"],
    )
    adjusted["timestamp"] = sample.get("timestamp", time.time())
    adjusted["gap_seconds"] = float(sample.get("gap_seconds", NOMINAL_SAMPLE_INTERVAL_S))
    return adjusted


def append_mode_history(mode: str, sensors: dict, timestamp: float | None = None) -> list[dict]:
    recorded_at = timestamp if timestamp is not None else time.time()
    entry = copy.deepcopy(sensors)
    entry["timestamp"] = recorded_at

    with MODE_HISTORY_LOCK:
        history = MODE_SENSOR_HISTORY.setdefault(mode, [])
        previous_timestamp = history[-1]["timestamp"] if history else recorded_at - NOMINAL_SAMPLE_INTERVAL_S
        entry["gap_seconds"] = max(1.0, recorded_at - previous_timestamp)
        history.append(entry)
        del history[:-ANOMALY_HISTORY_LIMIT]
        return copy.deepcopy(history)


def current_mode_history(mode: str) -> list[dict]:
    with MODE_HISTORY_LOCK:
        return copy.deepcopy(MODE_SENSOR_HISTORY.get(mode, []))


def base_history_for_mode(mode: str, sensors: dict, timestamp: float | None = None) -> list[dict]:
    history = current_mode_history(mode)
    if history:
        return history
    return [
        {
            **copy.deepcopy(sensors),
            "timestamp": timestamp if timestamp is not None else time.time(),
            "gap_seconds": NOMINAL_SAMPLE_INTERVAL_S,
        }
    ]


def replace_mode_history(mode: str, history: list[dict]) -> list[dict]:
    normalized_history = []
    for sample in history[-ANOMALY_HISTORY_LIMIT:]:
        normalized_entry = normalize_sensors(
            temperature_c=sample["temperature_c"],
            humidity_pct=sample["humidity_pct"],
            co2_ppm=sample["co2_ppm"],
        )
        normalized_entry["timestamp"] = float(sample.get("timestamp", time.time()))
        normalized_entry["gap_seconds"] = max(
            1.0,
            float(sample.get("gap_seconds", NOMINAL_SAMPLE_INTERVAL_S)),
        )
        normalized_history.append(normalized_entry)

    with MODE_HISTORY_LOCK:
        MODE_SENSOR_HISTORY[mode] = normalized_history
        return copy.deepcopy(MODE_SENSOR_HISTORY[mode])


def live_effective_history(raw_sensors: dict, presentation_state: dict) -> list[dict]:
    raw_history = base_history_for_mode("live", raw_sensors)
    offsets = presentation_offsets_for_history(raw_sensors, presentation_state)
    return [
        apply_offsets_to_history_sample(sample, offsets)
        for sample in raw_history
    ]


def build_preset_history(samples: list[dict]) -> list[dict]:
    if not samples:
        return []

    gaps = [
        max(1.0, float(sample.get("gap_seconds", NOMINAL_SAMPLE_INTERVAL_S)))
        for sample in samples
    ]
    backfill_seconds = sum(gaps[1:]) if len(gaps) > 1 else 0.0
    current_timestamp = time.time() - backfill_seconds
    history = []

    for index, sample in enumerate(samples):
        sensors = normalize_sensors(
            temperature_c=sample["temperature_c"],
            humidity_pct=sample["humidity_pct"],
            co2_ppm=sample["co2_ppm"],
        )
        history.append(
            {
                **sensors,
                "timestamp": current_timestamp,
                "gap_seconds": gaps[index],
            }
        )
        if index < len(samples) - 1:
            current_timestamp += gaps[index + 1]

    return history


def attach_anomaly(payload: dict, anomaly: dict) -> dict:
    payload["anomaly"] = anomaly
    payload["overall_state"] = promote_state(payload["overall_state"], anomaly["severity"])
    if anomaly["label"] != "normal":
        payload["summary"] = payload["summary"] + " " + anomaly["summary"]
    return payload


def evaluate_history_payload(
    mode: str,
    sensors: dict,
    history: list[dict],
    thresholds: Thresholds | None = None,
) -> dict:
    decision = evaluate_greenhouse_ai(
        temperature_c=sensors["temperature_c"],
        humidity_pct=sensors["humidity_pct"],
        co2_ppm=sensors["co2_ppm"],
        thresholds=thresholds,
    )
    decision = attach_anomaly(
        decision,
        evaluate_greenhouse_anomaly_ai(history),
    )
    decision["mode"] = mode
    decision["history_window"] = copy.deepcopy(history[-6:])
    return decision


def current_board_logs(limit: int = 80) -> list[dict]:
    with BOARD_LOG_LOCK:
        return copy.deepcopy(BOARD_LOGS[-limit:])


def store_board_log(payload: dict) -> dict:
    message = str(payload["message"]).strip()
    if not message:
        raise ValueError("message must not be empty")

    level = str(payload.get("level", "info")).strip().lower() or "info"
    if level not in {"debug", "info", "warning", "error"}:
        level = "info"

    received_at = time.time()
    entry = {
        "device_id": str(payload.get("device_id") or LIVE_STATE.get("device_id") or "esp32-s3-greenhouse"),
        "level": level,
        "message": message,
        "received_at": received_at,
        "received_at_label": time.strftime("%H:%M:%S", time.localtime(received_at)),
    }

    with BOARD_LOG_LOCK:
        BOARD_LOGS.append(entry)
        del BOARD_LOGS[:-BOARD_LOG_LIMIT]
        total = len(BOARD_LOGS)

    return {
        "ok": True,
        "total_logs": total,
        "log": entry,
    }


def current_board_log_payload() -> dict:
    with LIVE_STATE_LOCK:
        live_state = copy.deepcopy(LIVE_STATE)

    logs = current_board_logs()
    latest_log_at = logs[-1]["received_at"] if logs else None
    last_activity_at = None
    if live_state["received_at"] is not None and latest_log_at is not None:
        last_activity_at = max(live_state["received_at"], latest_log_at)
    else:
        last_activity_at = live_state["received_at"] or latest_log_at

    age_seconds = None
    connected = False
    if last_activity_at is not None:
        age_seconds = round(max(0.0, time.time() - last_activity_at), 1)
        connected = age_seconds <= LIVE_TIMEOUT_SECONDS

    return {
        "logs": logs,
        "connected": connected,
        "device_id": live_state["device_id"] or (logs[-1]["device_id"] if logs else None),
        "received_at": (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_activity_at))
            if last_activity_at is not None
            else None
        ),
        "age_seconds": age_seconds,
    }


def serial_bridge_snapshot() -> dict:
    if SERIAL_BRIDGE is None:
        return {
            "enabled": False,
            "connected": False,
            "port": None,
            "error": None,
        }
    return SERIAL_BRIDGE.snapshot()


def default_board_device_id() -> str:
    with LIVE_STATE_LOCK:
        live_device_id = LIVE_STATE["device_id"]
    return live_device_id or "esp32-s3-greenhouse-1"


def detect_serial_port() -> str | None:
    if list_ports is None:
        return None

    fallback = None
    for port in list_ports.comports():
        description = (port.description or "").lower()
        if port.vid == 0x303A:
            return port.device
        if (
            "esp32" in description
            or "usb jtag/serial" in description
            or "usb serial" in description
            or "usb single serial" in description
            or "usbmodem" in (port.device or "").lower()
        ):
            fallback = fallback or port.device
    return fallback


def open_serial_connection(port: str, baudrate: int):
    connection = serial.Serial()
    connection.port = port
    connection.baudrate = baudrate
    connection.timeout = 1.0
    connection.write_timeout = 1.0
    connection.rtscts = False
    connection.dsrdtr = False
    connection.dtr = False
    connection.rts = False
    connection.open()
    time.sleep(0.2)
    try:
        connection.reset_input_buffer()
    except Exception:
        pass
    return connection


def handle_serial_event(raw_line: str, port: str) -> None:
    line = raw_line.strip()
    if not line:
        return

    if not line.startswith(SERIAL_EVENT_PREFIX):
        store_board_log(
            {
                "device_id": default_board_device_id(),
                "level": "info",
                "message": line,
            }
        )
        return

    payload_text = line[len(SERIAL_EVENT_PREFIX):].strip()
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        store_board_log(
            {
                "device_id": default_board_device_id(),
                "level": "warning",
                "message": f"Malformed USB serial payload from {port}: {payload_text}",
            }
        )
        return

    kind = str(payload.get("kind", "")).strip().lower()
    if kind == "telemetry":
        try:
            store_live_telemetry(payload)
        except (KeyError, ValueError, TypeError) as exc:
            store_board_log(
                {
                    "device_id": str(payload.get("device_id") or default_board_device_id()),
                    "level": "error",
                    "message": f"Invalid USB telemetry payload: {exc}",
                }
            )
        return

    if kind == "log":
        store_board_log(payload)
        return

    store_board_log(
        {
            "device_id": str(payload.get("device_id") or default_board_device_id()),
            "level": "warning",
            "message": f"Unsupported USB event kind: {kind or 'missing'}",
        }
    )


class SerialBridge(threading.Thread):
    def __init__(self, requested_port: str | None, baudrate: int):
        super().__init__(daemon=True)
        self.requested_port = requested_port
        self.baudrate = baudrate
        self.stop_event = threading.Event()
        self.status_lock = threading.Lock()
        self.connection_lock = threading.Lock()
        self.connection = None
        self.status = {
            "enabled": True,
            "connected": False,
            "port": None,
            "error": None,
        }

    def snapshot(self) -> dict:
        with self.status_lock:
            return copy.deepcopy(self.status)

    def set_status(self, **updates: object) -> None:
        with self.status_lock:
            self.status.update(updates)

    def resolve_port(self) -> str | None:
        if self.requested_port in (None, "", "auto"):
            return detect_serial_port()
        return self.requested_port

    def stop(self) -> None:
        self.stop_event.set()

    def write(self, payload: bytes) -> int:
        if not payload:
            return 0

        with self.connection_lock:
            connection = self.connection
            if connection is None or not connection.is_open:
                raise RuntimeError("serial bridge is not connected")
            written = connection.write(payload)
            try:
                connection.flush()
            except Exception:
                pass
            return int(written)

    def run(self) -> None:
        if serial is None:
            print("PySerial is not available. USB serial bridge disabled.")
            self.set_status(enabled=False, error="pyserial not installed")
            return

        announced_waiting = False
        while not self.stop_event.is_set():
            port = self.resolve_port()
            if not port:
                if not announced_waiting:
                    print("Waiting for an ESP32-S3 USB serial port...")
                    announced_waiting = True
                self.set_status(connected=False, port=None, error="serial device not found")
                self.stop_event.wait(2.0)
                continue

            announced_waiting = False
            connection = None
            try:
                connection = open_serial_connection(port, self.baudrate)
                with self.connection_lock:
                    self.connection = connection
                self.set_status(connected=True, port=port, error=None)
                print(f"USB serial bridge attached to {port}.")

                while not self.stop_event.is_set():
                    raw = connection.readline()
                    if not raw:
                        continue
                    handle_serial_event(raw.decode("utf-8", "replace"), port)

            except Exception as exc:
                self.set_status(connected=False, port=port, error=str(exc))
                print(f"USB serial bridge error on {port}: {exc}")
                self.stop_event.wait(2.0)
            finally:
                with self.connection_lock:
                    if self.connection is connection:
                        self.connection = None
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass


def default_live_payload() -> dict:
    return {
        "sensors": copy.deepcopy(DEFAULT_LIVE_SENSORS),
        "thresholds": copy.deepcopy(Thresholds().__dict__),
        "overall_state": "stable",
        "summary": (
            "Waiting for live telemetry from the ESP32-S3. Start the board and connect "
            "it over USB serial or Wi-Fi."
        ),
        "triggered_conditions": [],
        "actions": waiting_actions(),
        "decision_engine": "waiting_for_board_ai",
        "model_available": False,
        "mode": "live",
        "connected": False,
        "device_id": None,
        "received_at": None,
        "age_seconds": None,
        "raw_sensors": copy.deepcopy(DEFAULT_LIVE_SENSORS),
        "presentation": {
            "offsets": {"temperature_c": 0.0, "humidity_pct": 0.0, "co2_ppm": 0},
            "override": None,
            "active": False,
            "override_active": False,
        },
        "anomaly": waiting_anomaly(),
    }


def current_live_payload() -> dict:
    with LIVE_STATE_LOCK:
        state = copy.deepcopy(LIVE_STATE)
    with PRESENTATION_STATE_LOCK:
        presentation_state = copy.deepcopy(PRESENTATION_STATE)

    if state["received_at"] is None:
        return default_live_payload()

    raw_sensors = state["raw_sensors"] or copy.deepcopy(DEFAULT_LIVE_SENSORS)
    board_result = copy.deepcopy(state.get("board_result"))
    if board_result is not None:
        payload = board_result
        payload["sensors"] = copy.deepcopy(raw_sensors)
    else:
        payload = default_live_payload()
        payload["sensors"] = copy.deepcopy(raw_sensors)
        payload["raw_sensors"] = copy.deepcopy(raw_sensors)
        payload["device_id"] = state["device_id"]
        payload["connected"] = True
        payload["received_at"] = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(state["received_at"]),
        )
        payload["age_seconds"] = round(max(0.0, time.time() - state["received_at"]), 1)
        payload["summary"] = (
            "Live sensor data arrived from the ESP32-S3, but no on-device AI result "
            "was included in the payload yet."
        )

    age_seconds = max(0.0, time.time() - state["received_at"])
    connected = age_seconds <= LIVE_TIMEOUT_SECONDS
    payload.update(
        {
            "mode": "live",
            "connected": connected,
            "device_id": state["device_id"],
            "received_at": time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(state["received_at"]),
            ),
            "age_seconds": round(age_seconds, 1),
            "raw_sensors": raw_sensors,
            "presentation": (
                {
                    "offsets": {"temperature_c": 0.0, "humidity_pct": 0.0, "co2_ppm": 0},
                    "override": None,
                    "active": False,
                    "override_active": False,
                }
                if board_result is not None
                else {
                    **presentation_state,
                    "active": presentation_is_active(presentation_state),
                    "override_active": presentation_state["override"] is not None,
                }
            ),
        }
    )

    summary_prefix = []
    if connected:
        summary_prefix.append(
            "Live ESP32-S3 on-device AI update received."
            if board_result is not None
            else "Live ESP32-S3 update received."
        )
    else:
        summary_prefix.append("Live feed is stale. Showing the last ESP32-S3 reading.")

    if board_result is not None and presentation_is_active(presentation_state):
        summary_prefix.append("Presentation controls are disabled while live on-device AI is active.")
    elif presentation_state["override"] is not None:
        summary_prefix.append("Presentation override is active.")
    elif presentation_is_active(presentation_state):
        summary_prefix.append("Presentation offsets are active.")

    payload["summary"] = " ".join(summary_prefix + [payload["summary"]])
    return payload


def store_live_telemetry(payload: dict) -> dict:
    thresholds = Thresholds.from_mapping(payload.get("thresholds"))
    raw_sensors = normalize_sensors(
        temperature_c=float(payload["temperature_c"]),
        humidity_pct=float(payload["humidity_pct"]),
        co2_ppm=float(payload["co2_ppm"]),
    )

    with LIVE_STATE_LOCK:
        LIVE_STATE["raw_sensors"] = copy.deepcopy(raw_sensors)
        LIVE_STATE["thresholds"] = copy.deepcopy(thresholds.__dict__)
        LIVE_STATE["device_id"] = str(payload.get("device_id", "esp32-s3-greenhouse"))
        LIVE_STATE["received_at"] = time.time()
        LIVE_STATE["board_result"] = copy.deepcopy(payload.get("board_result"))

    append_mode_history("live", raw_sensors, timestamp=LIVE_STATE["received_at"])
    response = current_live_payload()
    response["posted_payload"] = raw_sensors
    return response


def update_presentation_controls(payload: dict) -> dict:
    presentation_state = {
        "offsets": normalize_offsets(payload.get("offsets")),
        "override": normalize_override(payload.get("override")),
    }
    with PRESENTATION_STATE_LOCK:
        PRESENTATION_STATE["offsets"] = presentation_state["offsets"]
        PRESENTATION_STATE["override"] = presentation_state["override"]
    return current_live_payload()


def load_presentation_preset(payload: dict) -> dict:
    preset_id = str(payload.get("preset_id", "")).strip()
    preset = get_presentation_preset(preset_id)
    if preset is None:
        raise ValueError(f"unknown preset: {preset_id or 'missing'}")

    thresholds = Thresholds.from_mapping(payload.get("thresholds"))
    history = build_preset_history(preset["samples"])
    history = replace_mode_history("preset", history)
    sensors = copy.deepcopy(history[-1])
    decision = evaluate_history_payload(
        mode="preset",
        sensors=sensors,
        history=history,
        thresholds=thresholds,
    )
    decision["preset_id"] = preset["id"]
    decision["preset_label"] = preset["label"]
    decision["preset_category"] = preset["category"]
    decision["preset_description"] = preset["description"]
    decision["preset_target_anomaly"] = preset["target_anomaly"]
    return decision


def send_serial_console_input(payload: dict) -> dict:
    if SERIAL_BRIDGE is None:
        raise ValueError("serial bridge is disabled")

    control = str(payload.get("control", "")).strip().lower()
    text = str(payload.get("text", ""))
    append_newline = bool(payload.get("append_newline", True))

    if control:
        control_map = {
            "interrupt": (b"\x03", "Dashboard sent Ctrl+C to the board console."),
            "soft_reset": (b"\x04", "Dashboard sent Ctrl+D (soft reset) to the board console."),
            "newline": (b"\r\n", "Dashboard sent a newline to the board console."),
        }
        if control not in control_map:
            raise ValueError(f"unsupported control command: {control}")
        raw_bytes, description = control_map[control]
    else:
        if not text.strip():
            raise ValueError("command text must not be empty")
        raw_bytes = text.encode("utf-8")
        if append_newline:
            raw_bytes += b"\r\n"
        description = f"Dashboard sent console input: {text.strip()}"

    try:
        bytes_sent = SERIAL_BRIDGE.write(raw_bytes)
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    store_board_log(
        {
            "device_id": "dashboard-host",
            "level": "info",
            "message": description,
        }
    )
    return {
        "ok": True,
        "bytes_sent": bytes_sent,
        "serial_bridge": serial_bridge_snapshot(),
    }


class DashboardHandler(BaseHTTPRequestHandler):
    demo_rows = load_demo_rows()
    demo_index = 0

    def do_GET(self) -> None:
        route = urlparse(self.path).path

        if route == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "demo_rows": len(self.demo_rows),
                    "serial_bridge": serial_bridge_snapshot(),
                }
            )
            return

        if route == "/api/demo":
            self._send_json(self._next_demo_payload())
            return

        if route == "/api/presets":
            self._send_json({"presets": presentation_preset_catalog()})
            return

        if route == "/api/live":
            self._send_json(current_live_payload())
            return

        if route == "/api/board/logs":
            self._send_json(current_board_log_payload())
            return

        if route == "/":
            route = "/index.html"

        file_path = DASHBOARD_DIR / route.lstrip("/")
        if file_path.is_file():
            self._send_file(file_path)
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if route == "/api/recommend":
                thresholds = Thresholds.from_mapping(payload.get("thresholds"))
                sensors = normalize_sensors(
                    temperature_c=float(payload["temperature_c"]),
                    humidity_pct=float(payload["humidity_pct"]),
                    co2_ppm=float(payload["co2_ppm"]),
                )
                history = append_mode_history("manual", sensors)
                decision = evaluate_history_payload(
                    mode="manual",
                    sensors=sensors,
                    history=history,
                    thresholds=thresholds,
                )
                self._send_json(decision)
                return

            if route == "/api/preset":
                self._send_json(load_presentation_preset(payload))
                return

            if route == "/api/serial/write":
                self._send_json(send_serial_console_input(payload))
                return

            if route == "/api/telemetry":
                self._send_json(store_live_telemetry(payload))
                return

            if route == "/api/live/control":
                self._send_json(update_presentation_controls(payload))
                return

            if route == "/api/board/log":
                self._send_json(store_board_log(payload))
                return

            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
        except (KeyError, ValueError, TypeError) as exc:
            self._send_json(
                {"error": f"Invalid request payload: {exc}"},
                status=HTTPStatus.BAD_REQUEST,
            )

    def log_message(self, fmt: str, *args) -> None:
        return

    @classmethod
    def _next_demo_payload(cls) -> dict:
        row = cls.demo_rows[cls.demo_index % len(cls.demo_rows)]
        cls.demo_index += 1
        sensors = normalize_sensors(**row)
        history = append_mode_history("demo", sensors)
        decision = evaluate_history_payload(
            mode="demo",
            sensors=sensors,
            history=history,
        )
        decision["demo_row"] = cls.demo_index
        return decision

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", guess_content_type(path))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the virtual greenhouse action dashboard."
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--serial-port", default="auto")
    parser.add_argument("--serial-baud", type=int, default=DEFAULT_SERIAL_BAUD)
    parser.add_argument("--no-serial", action="store_true")
    return parser.parse_args()


def main() -> None:
    global SERIAL_BRIDGE
    args = parse_args()
    if not args.no_serial:
        SERIAL_BRIDGE = SerialBridge(args.serial_port, args.serial_baud)
        SERIAL_BRIDGE.start()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    display_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    print(f"Dashboard available at http://{display_host}:{args.port}")
    if args.host == "0.0.0.0":
        print("LAN clients can reach it using this laptop's local IP address on the same Wi-Fi network.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        server.server_close()
        if SERIAL_BRIDGE is not None:
            SERIAL_BRIDGE.stop()
            SERIAL_BRIDGE.join(timeout=2.0)
            SERIAL_BRIDGE = None


if __name__ == "__main__":
    main()
