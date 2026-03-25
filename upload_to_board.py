#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import shutil
import site
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

try:
    import board_model_manifest as manifest
except Exception:
    manifest = None

try:
    from dashboard_server import detect_serial_port
except Exception:
    detect_serial_port = None


USB_BOARD_FILES = [
    "board_config.py",
    "scd41_driver.py",
    "board_ai_runtime.py",
    "board_model_manifest.py",
    "esp32_usb_dashboard.py",
]
WIFI_BOARD_FILES = [
    "board_config.py",
    "scd41_driver.py",
    "esp32_wifi_dashboard.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload the required greenhouse project files to the ESP32-S3."
    )
    parser.add_argument("--port", default="auto")
    parser.add_argument(
        "--mode",
        choices=("usb", "wifi"),
        default="usb",
        help="Which dashboard entrypoint to make the board boot into.",
    )
    parser.add_argument(
        "--mpremote",
        default=shutil.which("mpremote") or "mpremote",
        help="Path to the mpremote executable.",
    )
    parser.add_argument(
        "--emlearn-trees",
        default="auto",
        help="Path to emlearn_trees.py, or 'auto' to search common locations.",
    )
    parser.add_argument("--skip-config", action="store_true")
    parser.add_argument("--no-main", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve_port(requested_port: str) -> str:
    if requested_port not in ("", "auto"):
        return requested_port
    if detect_serial_port is not None:
        detected_port = detect_serial_port()
        if detected_port:
            return detected_port
    return "auto"


def require_mpremote(mpremote_path: str) -> None:
    if Path(mpremote_path).name == mpremote_path:
        resolved = shutil.which(mpremote_path)
        if resolved is None:
            raise SystemExit(
                "mpremote was not found. Install it with `python3 -m pip install mpremote`."
            )
        return

    if not Path(mpremote_path).exists():
        raise SystemExit(f"mpremote executable not found: {mpremote_path}")


def find_emlearn_trees(explicit_path: str) -> Path | None:
    if explicit_path not in ("", "auto"):
        candidate = Path(explicit_path).expanduser().resolve()
        if not candidate.exists():
            raise SystemExit(f"emlearn_trees.py not found: {candidate}")
        return candidate

    repo_candidate = ROOT / "emlearn_trees.py"
    if repo_candidate.exists():
        return repo_candidate

    search_roots = []
    try:
        search_roots.extend(Path(path) for path in site.getsitepackages())
        user_site = site.getusersitepackages()
        if user_site:
            search_roots.append(Path(user_site))
    except Exception:
        pass

    seen = set()
    for root in search_roots:
        if root in seen or not root.exists():
            continue
        seen.add(root)
        for match in root.rglob("emlearn_trees.py"):
            return match.resolve()
    return None


def board_files_for_mode(mode: str, skip_config: bool) -> list[Path]:
    if mode == "usb":
        filenames = list(USB_BOARD_FILES)
        if manifest is None:
            raise SystemExit(
                "board_model_manifest.py could not be imported, so the USB board model files "
                "could not be resolved."
            )

        action_models = getattr(manifest, "ACTION_MODELS", {})
        anomaly_model = getattr(manifest, "ANOMALY_MODEL", {})
        model_filenames = [model["filename"] for model in action_models.values()]
        if anomaly_model:
            model_filenames.append(anomaly_model["filename"])
        filenames.extend(model_filenames)
    else:
        filenames = list(WIFI_BOARD_FILES)

    if skip_config:
        filenames = [name for name in filenames if name != "board_config.py"]

    files = [ROOT / name for name in filenames]
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise SystemExit("Missing required files:\n- " + "\n- ".join(missing))

    return files


def startup_module(mode: str) -> str:
    if mode == "wifi":
        return "esp32_wifi_dashboard"
    return "esp32_usb_dashboard"


def build_main_contents(mode: str) -> str:
    module_name = startup_module(mode)
    return f"import {module_name}\n\n{module_name}.main()\n"


def create_temp_main(mode: str) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        prefix="greenhouse_main_",
        suffix=".py",
        delete=False,
        encoding="utf-8",
    ) as handle:
        handle.write(build_main_contents(mode))
        return Path(handle.name)


def run_mpremote(mpremote_path: str, port: str, args: list[str]) -> None:
    command = [mpremote_path, "connect", port, *args]
    try:
        subprocess.run(command, cwd=str(ROOT), check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "mpremote failed while talking to the board.\n"
            "Make sure Thonny, the dashboard server, and any other serial monitor are closed,\n"
            "then press EN/RST once and try again.\n"
            f"Failed command: {' '.join(command)}\n"
            f"Exit code: {exc.returncode}"
        ) from exc


def run_mpremote_capture(mpremote_path: str, port: str, args: list[str]) -> subprocess.CompletedProcess:
    command = [mpremote_path, "connect", port, *args]
    try:
        return subprocess.run(
            command,
            cwd=str(ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "mpremote failed while talking to the board.\n"
            "Make sure Thonny, the dashboard server, and any other serial monitor are closed,\n"
            "then press EN/RST once and try again.\n"
            f"Failed command: {' '.join(command)}\n"
            f"Exit code: {exc.returncode}\n"
            f"{exc.stderr.strip()}"
        ) from exc


def upload_file(mpremote_path: str, port: str, local_path: Path, remote_name: str) -> bool:
    print(f"Uploading {local_path.name} -> {remote_name}")
    result = run_mpremote_capture(
        mpremote_path,
        port,
        ["fs", "cp", str(local_path), f":{remote_name}"],
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return f"Up to date: {remote_name}" not in result.stdout


def print_plan(
    port: str,
    mode: str,
    files: list[Path],
    include_main: bool,
    emlearn_trees_path: Path | None,
    dry_run: bool,
) -> None:
    print("Board upload plan")
    print(f"- Port: {port}")
    print(f"- Mode: {mode}")
    print(f"- Upload count: {len(files) + (1 if include_main else 0) + (1 if emlearn_trees_path else 0)}")
    for path in files:
        print(f"  - {path.name}")
    if emlearn_trees_path is not None:
        print(f"  - {emlearn_trees_path.name}")
    if include_main:
        print(f"  - main.py ({startup_module(mode)})")
    if dry_run:
        print("Dry run only. No files will be copied.")


def sync_board(
    *,
    port: str,
    mode: str = "usb",
    mpremote_path: str | None = None,
    emlearn_trees: str = "auto",
    skip_config: bool = False,
    include_main: bool = True,
    reset: bool = False,
    dry_run: bool = False,
) -> bool:
    mpremote_executable = mpremote_path or (shutil.which("mpremote") or "mpremote")
    require_mpremote(mpremote_executable)

    files = board_files_for_mode(mode, skip_config)
    emlearn_trees_path = None

    if mode == "usb":
        emlearn_trees_path = find_emlearn_trees(emlearn_trees)
        if emlearn_trees_path is None:
            print(
                "Warning: emlearn_trees.py was not found locally.\n"
                "The upload will continue, but the USB on-device AI runtime needs that file.\n"
                "If it is not already on the ESP32-S3, add it with --emlearn-trees /path/to/emlearn_trees.py."
            )

    print_plan(
        port=port,
        mode=mode,
        files=files,
        include_main=include_main,
        emlearn_trees_path=emlearn_trees_path,
        dry_run=dry_run,
    )
    if dry_run:
        return False

    any_changed = False
    temp_main_path = None

    try:
        for file_path in files:
            any_changed = upload_file(mpremote_executable, port, file_path, file_path.name) or any_changed

        if emlearn_trees_path is not None:
            any_changed = (
                upload_file(mpremote_executable, port, emlearn_trees_path, "emlearn_trees.py")
                or any_changed
            )

        if include_main:
            temp_main_path = create_temp_main(mode)
            any_changed = upload_file(mpremote_executable, port, temp_main_path, "main.py") or any_changed

        if reset and any_changed:
            print("Soft-resetting the board...")
            run_mpremote(mpremote_executable, port, ["soft-reset"])

    finally:
        with contextlib.suppress(FileNotFoundError):
            if temp_main_path is not None:
                temp_main_path.unlink()

    if any_changed:
        print("Board files synced.")
    else:
        print("Board files are already up to date.")
    return any_changed


def main() -> None:
    args = parse_args()
    port = resolve_port(args.port)
    sync_board(
        port=port,
        mode=args.mode,
        mpremote_path=args.mpremote,
        emlearn_trees=args.emlearn_trees,
        skip_config=args.skip_config,
        include_main=not args.no_main,
        reset=args.reset,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
