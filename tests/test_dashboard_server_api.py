from __future__ import annotations

import threading
import unittest

import dashboard_server


def reset_dashboard_state() -> None:
    with dashboard_server.LIVE_STATE_LOCK:
        dashboard_server.LIVE_STATE.update(
            {
                "raw_sensors": None,
                "thresholds": None,
                "device_id": None,
                "received_at": None,
                "board_result": None,
            }
        )
    with dashboard_server.LIVE_STREAM_CONDITION:
        dashboard_server.LIVE_UPDATE_SEQUENCE = 0
    with dashboard_server.PRESENTATION_STATE_LOCK:
        dashboard_server.PRESENTATION_STATE.update(
            {
                "offsets": {
                    "temperature_c": 0.0,
                    "humidity_pct": 0.0,
                    "co2_ppm": 0,
                },
                "override": None,
            }
        )
    with dashboard_server.BOARD_LOG_LOCK:
        dashboard_server.BOARD_LOGS.clear()
    with dashboard_server.MODE_HISTORY_LOCK:
        for key in dashboard_server.MODE_SENSOR_HISTORY:
            dashboard_server.MODE_SENSOR_HISTORY[key] = []
    dashboard_server.SERIAL_BRIDGE = None
    dashboard_server.DashboardHandler.demo_rows = dashboard_server.load_demo_rows()
    dashboard_server.DashboardHandler.demo_index = 0


class FakeSerialBridge:
    def __init__(self) -> None:
        self.writes = []

    def write(self, payload: bytes) -> int:
        self.writes.append(payload)
        return len(payload)

    def snapshot(self) -> dict:
        return {"enabled": True, "connected": True, "port": "/dev/test", "error": None}


class FakeShutdownServer:
    def __init__(self) -> None:
        self.shutdown_called = threading.Event()

    def shutdown(self) -> None:
        self.shutdown_called.set()


class DashboardServerStateTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_dashboard_state()

    def test_load_demo_rows_reads_dataset(self) -> None:
        rows = dashboard_server.load_demo_rows()
        self.assertGreater(len(rows), 0)
        self.assertIn("temperature_c", rows[0])

    def test_store_live_telemetry_updates_current_live_payload(self) -> None:
        dashboard_server.store_live_telemetry(
            {
                "device_id": "esp32-test",
                "temperature_c": 22.4,
                "humidity_pct": 51.0,
                "co2_ppm": 940,
            }
        )
        payload = dashboard_server.current_live_payload()
        self.assertTrue(payload["connected"])
        self.assertEqual(payload["device_id"], "esp32-test")
        self.assertEqual(payload["raw_sensors"]["co2_ppm"], 940)
        self.assertEqual(payload["sample_sequence"], 1)
        self.assertEqual(len(payload["history_window"]), 1)
        self.assertEqual(payload["history_window"][0]["co2_ppm"], 940)

    def test_store_live_telemetry_expands_compact_board_result(self) -> None:
        dashboard_server.store_live_telemetry(
            {
                "device_id": "esp32-test",
                "temperature_c": 31.2,
                "humidity_pct": 42.5,
                "co2_ppm": 1325,
                "gap_seconds": 30,
                "sample_log": (
                    "CO2=1325 ppm | Temperature=31.2 C | Humidity=42.5% | "
                    "Action=cooling, ventilating | Anomaly=CO2 high"
                ),
                "board_result": {
                    "format": "compact_v1",
                    "decision_engine": "board_on_device_ai",
                    "model_available": True,
                    "on_device": True,
                    "actions": [
                        {"key": "heater", "active": False, "confidence": 0.98},
                        {"key": "cooling_fan", "active": True, "confidence": 0.93},
                        {"key": "ventilation", "active": True, "confidence": 0.91},
                        {"key": "mister", "active": False, "confidence": 0.87},
                    ],
                    "anomaly": {
                        "label": "co2_high",
                        "confidence": 0.88,
                        "anomaly_score": 0.88,
                        "decision_engine": "board_anomaly_ai",
                        "model_available": True,
                        "history_ready": True,
                        "window_size": 6,
                        "top_predictions": [
                            {"label": "co2_high", "confidence": 0.88},
                            {"label": "normal", "confidence": 0.08},
                        ],
                    },
                },
            }
        )
        payload = dashboard_server.current_live_payload()
        self.assertTrue(payload["connected"])
        self.assertEqual(payload["decision_engine"], "board_on_device_ai")
        self.assertEqual(payload["anomaly"]["label"], "co2_high")
        self.assertTrue(any(action["active"] for action in payload["actions"]))
        self.assertTrue(
            any(
                "CO2=1325 ppm" in entry["message"]
                for entry in dashboard_server.current_board_logs()
            )
        )

    def test_parse_compact_telemetry_line(self) -> None:
        payload = dashboard_server.parse_compact_telemetry_line(
            "GHTLM|esp32-test|31.2|42.5|1325|30.0|0|980|1|930|1|910|0|870|co2_high|880|880|board_anomaly_ai|1|6"
        )
        self.assertEqual(payload["device_id"], "esp32-test")
        self.assertEqual(payload["co2_ppm"], 1325)
        self.assertEqual(payload["board_result"]["anomaly"]["label"], "co2_high")
        self.assertTrue(payload["board_result"]["actions"][1]["active"])

    def test_load_presentation_preset_returns_expected_anomaly(self) -> None:
        payload = dashboard_server.load_presentation_preset({"preset_id": "sensor_spike"})
        self.assertEqual(payload["mode"], "preset")
        self.assertEqual(payload["anomaly"]["label"], "sensor_spike")
        self.assertFalse(any(action["active"] for action in payload["actions"]))
        self.assertTrue(payload["action_lock"]["active"])

    def test_store_live_telemetry_locks_actions_for_non_environmental_anomaly(self) -> None:
        dashboard_server.store_live_telemetry(
            {
                "device_id": "esp32-test",
                "temperature_c": 29.0,
                "humidity_pct": 61.0,
                "co2_ppm": 910,
                "gap_seconds": 40,
                "board_result": {
                    "format": "compact_v1",
                    "decision_engine": "board_on_device_ai",
                    "model_available": True,
                    "on_device": True,
                    "actions": [
                        {"key": "heater", "active": False, "confidence": 0.10},
                        {"key": "cooling_fan", "active": True, "confidence": 0.92},
                        {"key": "ventilation", "active": True, "confidence": 0.88},
                        {"key": "mister", "active": False, "confidence": 0.05},
                    ],
                    "anomaly": {
                        "label": "sensor_spike",
                        "confidence": 0.91,
                        "anomaly_score": 0.91,
                        "decision_engine": "board_anomaly_ai",
                        "model_available": True,
                        "history_ready": True,
                        "window_size": 6,
                        "top_predictions": [
                            {"label": "sensor_spike", "confidence": 0.91},
                        ],
                    },
                },
            }
        )
        payload = dashboard_server.current_live_payload()
        self.assertEqual(payload["anomaly"]["label"], "sensor_spike")
        self.assertFalse(any(action["active"] for action in payload["actions"]))
        self.assertTrue(payload["action_lock"]["active"])
        self.assertIn("held idle", payload["summary"])

    def test_store_board_log_round_trip(self) -> None:
        dashboard_server.store_board_log(
            {"device_id": "esp32-test", "level": "info", "message": "hello"}
        )
        payload = dashboard_server.current_board_log_payload()
        messages = [item["message"] for item in payload["logs"]]
        self.assertIn("hello", messages)

    def test_current_live_payload_surfaces_recent_sensor_fault(self) -> None:
        dashboard_server.store_board_log(
            {
                "device_id": "esp32-test",
                "level": "error",
                "message": (
                    "SCD41 seen on I2C but never became ready in low power, standard, "
                    "or single-shot mode. Check sensor power, wiring quality, or hardware."
                ),
            }
        )
        dashboard_server.store_board_log(
            {
                "device_id": "esp32-test",
                "level": "info",
                "message": "Waiting for the SCD41 warm-up period (35 seconds)...",
            }
        )

        payload = dashboard_server.current_live_payload()
        self.assertTrue(payload["connected"])
        self.assertEqual(payload["decision_engine"], "board_sensor_fault")
        self.assertEqual(payload["anomaly"]["label"], "sensor_unavailable")
        self.assertEqual(payload["device_id"], "esp32-test")

    def test_handle_serial_event_ignores_partial_json_fragment(self) -> None:
        dashboard_server.handle_serial_event(
            '"decision_engine": "board_anomaly_warmup", "history_ready": false}}, "co2_ppm": 988}',
            "/dev/test",
        )
        self.assertEqual(dashboard_server.current_board_logs(), [])

    def test_send_serial_console_input_uses_serial_bridge(self) -> None:
        fake_bridge = FakeSerialBridge()
        dashboard_server.SERIAL_BRIDGE = fake_bridge
        payload = dashboard_server.send_serial_console_input({"control": "soft_reset"})
        self.assertTrue(payload["ok"])
        self.assertEqual(fake_bridge.writes, [b"\x04"])

    def test_terminate_dashboard_service_requests_shutdown(self) -> None:
        fake_server = FakeShutdownServer()
        payload = dashboard_server.terminate_dashboard_service(fake_server, delay_seconds=0.0)
        self.assertTrue(payload["ok"])
        self.assertTrue(fake_server.shutdown_called.wait(1.0))
        self.assertTrue(
            any(
                "terminate request received" in entry["message"].lower()
                for entry in dashboard_server.current_board_logs()
            )
        )


if __name__ == "__main__":
    unittest.main()
