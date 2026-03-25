#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

try:
    from dashboard_server import DEFAULT_SERIAL_BAUD, detect_serial_port
except Exception:
    DEFAULT_SERIAL_BAUD = 115200
    detect_serial_port = None

try:
    from upload_to_board import sync_board
except Exception:
    sync_board = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the greenhouse dashboard stack in one command."
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--serial-port", default="auto")
    parser.add_argument("--serial-baud", type=int, default=DEFAULT_SERIAL_BAUD)
    parser.add_argument("--no-serial", action="store_true")
    parser.add_argument("--skip-board-sync", action="store_true")
    parser.add_argument("--board-mode", choices=("usb", "wifi"), default="usb")
    parser.add_argument("--skip-board-config", action="store_true")
    parser.add_argument("--emlearn-trees", default="auto")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--browser-delay", type=float, default=1.5)
    return parser.parse_args()


def dashboard_url(host: str, port: int) -> str:
    if host == "0.0.0.0":
        return f"http://127.0.0.1:{port}"
    return f"http://{host}:{port}"


def can_bind(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def maybe_launch_browser(url: str, delay: float) -> None:
    code = (
        "import sys, time, webbrowser\n"
        "time.sleep(float(sys.argv[2]))\n"
        "webbrowser.open(sys.argv[1], new=2)\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", code, url, str(delay)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def print_startup_notes(args: argparse.Namespace) -> None:
    print("Starting the greenhouse dashboard stack...")
    print(f"Project root: {ROOT}")
    print(f"Dashboard URL: {dashboard_url(args.host, args.port)}")

    if args.no_serial:
        print("USB serial bridge: disabled by request")
        return

    if args.serial_port not in ("", "auto"):
        print(f"USB serial bridge: using {args.serial_port} @ {args.serial_baud} baud")
        return

    detected_port = detect_serial_port() if detect_serial_port is not None else None
    if detected_port:
        print(f"Detected ESP32-S3 USB serial port: {detected_port}")
    else:
        print("ESP32-S3 USB serial port not detected yet. The server will keep waiting for it.")

    print("Make sure Thonny or any other serial monitor is closed before starting.")
    print("If the board is already flashed with main.py, press EN/RST once if live data does not appear.")


def maybe_sync_board(args: argparse.Namespace) -> None:
    if args.no_serial or args.skip_board_sync:
        return

    if sync_board is None:
        raise SystemExit("Board sync is unavailable because upload_to_board.py could not be imported.")

    if args.serial_port in ("", "auto"):
        detected_port = detect_serial_port() if detect_serial_port is not None else None
        if not detected_port:
            print("ESP32-S3 not detected yet. Skipping board sync and starting the server in waiting mode.")
            return
        board_port = detected_port
    else:
        board_port = args.serial_port

    print("Checking board files before starting the dashboard...")
    changed = sync_board(
        port=board_port,
        mode=args.board_mode,
        emlearn_trees=args.emlearn_trees,
        skip_config=args.skip_board_config,
        include_main=True,
        reset=True,
        dry_run=False,
    )
    if changed:
        print("Board updated. Starting the dashboard server next.")
    else:
        print("Board is already current. Starting the dashboard server next.")


def main() -> None:
    args = parse_args()
    server_script = ROOT / "dashboard_server.py"
    if not server_script.exists():
        raise SystemExit(f"Missing server entrypoint: {server_script}")

    if not can_bind(args.host, args.port):
        raise SystemExit(
            f"Port {args.port} on {args.host} is already in use. "
            "Stop the existing server or choose a different --port."
        )

    print_startup_notes(args)
    maybe_sync_board(args)

    if not args.no_browser:
        maybe_launch_browser(dashboard_url(args.host, args.port), args.browser_delay)

    command = [
        sys.executable,
        str(server_script),
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.no_serial:
        command.append("--no-serial")
    else:
        command.extend(["--serial-port", args.serial_port])
        command.extend(["--serial-baud", str(args.serial_baud)])

    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()
