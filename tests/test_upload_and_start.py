from __future__ import annotations

import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

import start_everything
import upload_to_board


class UploadAndStartTests(unittest.TestCase):
    def test_build_main_contents_switches_by_mode(self) -> None:
        self.assertIn("esp32_usb_dashboard.main()", upload_to_board.build_main_contents("usb"))
        self.assertIn("esp32_wifi_dashboard.main()", upload_to_board.build_main_contents("wifi"))

    def test_board_files_for_mode_can_skip_config(self) -> None:
        files = upload_to_board.board_files_for_mode("usb", skip_config=True)
        self.assertNotIn(upload_to_board.ROOT / "board_config.py", files)
        self.assertIn(upload_to_board.ROOT / "board_ai_runtime.py", files)

    def test_upload_file_detects_up_to_date_output(self) -> None:
        result = CompletedProcess(
            args=["mpremote"],
            returncode=0,
            stdout="Up to date: board_config.py\n",
            stderr="",
        )
        with mock.patch.object(upload_to_board, "run_mpremote_capture", return_value=result):
            changed = upload_to_board.upload_file("mpremote", "/dev/test", Path("board_config.py"), "board_config.py")
        self.assertFalse(changed)

    def test_sync_board_only_resets_when_a_file_changed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            local_file = temp_dir_path / "board.py"
            main_file = temp_dir_path / "main.py"
            local_file.write_text("board", encoding="utf-8")
            main_file.write_text("main", encoding="utf-8")

            with mock.patch.object(upload_to_board, "board_files_for_mode", return_value=[local_file]), \
                mock.patch.object(upload_to_board, "create_temp_main", return_value=main_file), \
                mock.patch.object(upload_to_board, "upload_file", side_effect=[False, False]) as upload_mock, \
                mock.patch.object(upload_to_board, "run_mpremote") as run_mock:
                changed = upload_to_board.sync_board(
                    port="/dev/test",
                    mode="wifi",
                    include_main=True,
                    reset=True,
                )

        self.assertFalse(changed)
        self.assertEqual(upload_mock.call_count, 2)
        run_mock.assert_not_called()

    def test_sync_board_resets_after_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            local_file = temp_dir_path / "board.py"
            main_file = temp_dir_path / "main.py"
            local_file.write_text("board", encoding="utf-8")
            main_file.write_text("main", encoding="utf-8")

            with mock.patch.object(upload_to_board, "board_files_for_mode", return_value=[local_file]), \
                mock.patch.object(upload_to_board, "create_temp_main", return_value=main_file), \
                mock.patch.object(upload_to_board, "upload_file", side_effect=[True, False]), \
                mock.patch.object(upload_to_board, "run_mpremote") as run_mock:
                changed = upload_to_board.sync_board(
                    port="/dev/test",
                    mode="wifi",
                    include_main=True,
                    reset=True,
                )

        self.assertTrue(changed)
        run_mock.assert_called_once()

    def test_maybe_sync_board_skips_when_no_serial_is_requested(self) -> None:
        args = argparse.Namespace(
            no_serial=True,
            skip_board_sync=False,
            serial_port="auto",
            board_mode="usb",
            emlearn_trees="auto",
            skip_board_config=False,
        )
        with mock.patch.object(start_everything, "sync_board") as sync_mock:
            start_everything.maybe_sync_board(args)
        sync_mock.assert_not_called()

    def test_maybe_sync_board_skips_when_board_is_not_detected(self) -> None:
        args = argparse.Namespace(
            no_serial=False,
            skip_board_sync=False,
            serial_port="auto",
            board_mode="usb",
            emlearn_trees="auto",
            skip_board_config=False,
        )
        with mock.patch.object(start_everything, "detect_serial_port", return_value=None), \
            mock.patch.object(start_everything, "sync_board") as sync_mock:
            with contextlib.redirect_stdout(io.StringIO()):
                start_everything.maybe_sync_board(args)
        sync_mock.assert_not_called()

    def test_maybe_sync_board_calls_sync_for_detected_board(self) -> None:
        args = argparse.Namespace(
            no_serial=False,
            skip_board_sync=False,
            serial_port="auto",
            board_mode="usb",
            emlearn_trees="auto",
            skip_board_config=True,
        )
        with mock.patch.object(start_everything, "detect_serial_port", return_value="/dev/test"), \
            mock.patch.object(start_everything, "sync_board", return_value=True) as sync_mock:
            with contextlib.redirect_stdout(io.StringIO()):
                start_everything.maybe_sync_board(args)
        sync_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
