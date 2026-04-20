#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stop the greenhouse dashboard server by its listening port."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Dashboard HTTP port to stop. Defaults to 8000.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Seconds to wait for a clean shutdown before using SIGKILL.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Use SIGKILL immediately instead of trying a graceful SIGTERM first.",
    )
    return parser.parse_args()


def listening_pids(port: int) -> list[int]:
    command = [
        "lsof",
        "-nP",
        "-t",
        f"-iTCP:{port}",
        "-sTCP:LISTEN",
    ]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise SystemExit(result.stderr.strip() or "Failed to inspect listening processes.")

    pids = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return sorted(set(pids))


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_pid(pid: int, timeout: float, force: bool) -> str:
    if force:
        os.kill(pid, signal.SIGKILL)
        return "killed"

    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + max(0.0, timeout)
    while time.time() < deadline:
        if not pid_exists(pid):
            return "stopped"
        time.sleep(0.1)

    if pid_exists(pid):
        os.kill(pid, signal.SIGKILL)
        return "killed"
    return "stopped"


def main() -> None:
    args = parse_args()
    pids = listening_pids(args.port)
    if not pids:
        print(f"No dashboard server is listening on port {args.port}.")
        return

    outcomes = []
    for pid in pids:
        action = stop_pid(pid, timeout=args.timeout, force=args.force)
        outcomes.append((pid, action))

    for pid, action in outcomes:
        if action == "stopped":
            print(f"Stopped dashboard process {pid} on port {args.port}.")
        else:
            print(f"Force-killed dashboard process {pid} on port {args.port}.")


if __name__ == "__main__":
    main()
