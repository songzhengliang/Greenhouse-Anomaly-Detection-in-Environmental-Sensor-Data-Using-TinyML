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

from greenhouse_control import Thresholds, evaluate_greenhouse

ROOT = Path(__file__).resolve().parent
DASHBOARD_DIR = ROOT / "dashboard"
DATASET_FILE = ROOT / "greenhouse_air_quality_dataset.csv"
LIVE_TIMEOUT_SECONDS = 75
DEFAULT_LIVE_SENSORS = {
    "temperature_c": 24.0,
    "humidity_pct": 60.0,
    "co2_ppm": 900,
}

LIVE_STATE_LOCK = threading.Lock()
LIVE_STATE = {
    "raw_sensors": None,
    "thresholds": None,
    "device_id": None,
    "received_at": None,
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


def default_live_payload() -> dict:
    payload = evaluate_greenhouse(
        DEFAULT_LIVE_SENSORS["temperature_c"],
        DEFAULT_LIVE_SENSORS["humidity_pct"],
        DEFAULT_LIVE_SENSORS["co2_ppm"],
    )
    payload.update(
        {
            "mode": "live",
            "connected": False,
            "device_id": None,
            "received_at": None,
            "age_seconds": None,
            "raw_sensors": copy.deepcopy(DEFAULT_LIVE_SENSORS),
            "presentation": copy.deepcopy(PRESENTATION_STATE),
            "summary": (
                "Waiting for live telemetry from the ESP32-S3. Start the board and keep "
                "it on the same Wi-Fi network as this laptop."
            ),
        }
    )
    return payload


def current_live_payload() -> dict:
    with LIVE_STATE_LOCK:
        state = copy.deepcopy(LIVE_STATE)
    with PRESENTATION_STATE_LOCK:
        presentation_state = copy.deepcopy(PRESENTATION_STATE)

    raw_sensors = state["raw_sensors"] or copy.deepcopy(DEFAULT_LIVE_SENSORS)
    thresholds = Thresholds.from_mapping(state["thresholds"])
    effective_sensors = apply_presentation_controls(raw_sensors, presentation_state)
    payload = evaluate_greenhouse(
        temperature_c=effective_sensors["temperature_c"],
        humidity_pct=effective_sensors["humidity_pct"],
        co2_ppm=effective_sensors["co2_ppm"],
        thresholds=thresholds,
    )

    if state["received_at"] is None:
        payload.update(
            {
                "mode": "live",
                "connected": False,
                "device_id": None,
                "received_at": None,
                "age_seconds": None,
                "raw_sensors": raw_sensors,
                "presentation": {
                    **presentation_state,
                    "active": presentation_is_active(presentation_state),
                    "override_active": presentation_state["override"] is not None,
                },
            }
        )
        if presentation_is_active(presentation_state):
            payload["summary"] = (
                "Presentation controls are active while waiting for the first ESP32-S3 sample. "
                + payload["summary"]
            )
        else:
            payload["summary"] = (
                "Waiting for live telemetry from the ESP32-S3. Start the board and keep "
                "it on the same Wi-Fi network as this laptop."
            )
        return payload

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
            "presentation": {
                **presentation_state,
                "active": presentation_is_active(presentation_state),
                "override_active": presentation_state["override"] is not None,
            },
        }
    )

    summary_prefix = []
    if connected:
        summary_prefix.append("Live ESP32-S3 update received.")
    else:
        summary_prefix.append("Live feed is stale. Showing the last ESP32-S3 reading.")

    if presentation_state["override"] is not None:
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
                }
            )
            return

        if route == "/api/demo":
            self._send_json(self._next_demo_payload())
            return

        if route == "/api/live":
            self._send_json(current_live_payload())
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
                decision = evaluate_greenhouse(
                    temperature_c=float(payload["temperature_c"]),
                    humidity_pct=float(payload["humidity_pct"]),
                    co2_ppm=float(payload["co2_ppm"]),
                    thresholds=thresholds,
                )
                decision["mode"] = "manual"
                self._send_json(decision)
                return

            if route == "/api/telemetry":
                self._send_json(store_live_telemetry(payload))
                return

            if route == "/api/live/control":
                self._send_json(update_presentation_controls(payload))
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
        decision = evaluate_greenhouse(
            temperature_c=row["temperature_c"],
            humidity_pct=row["humidity_pct"],
            co2_ppm=row["co2_ppm"],
        )
        decision["mode"] = "demo"
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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


if __name__ == "__main__":
    main()
