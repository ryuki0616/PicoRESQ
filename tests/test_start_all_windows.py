"""Windows統一起動の制御を疑似APIで検証し、実機用のプロセス終了テストも用意する。"""
from __future__ import annotations

import ctypes
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/start_all_windows.py"
SPEC = importlib.util.spec_from_file_location("start_all_windows", SOURCE)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class WindowsLauncherControlTests(unittest.TestCase):
    """実際のWin32 APIを呼ばず、起動と後始末の分岐を検証する。"""

    def setUp(self) -> None:
        """既存の起動スクリプトがあるルートと疑似APIを用意する。"""
        self.root = SOURCE.parent.parent
        self.api = MagicMock()
        self.api.CreateMutexW.return_value = 1
        self.api.CreateJobObjectW.return_value = 2
        self.api.WaitForSingleObject.return_value = 0
        self.environment = {}
        for patcher in (
            patch.object(launcher, "os", SimpleNamespace(name="nt", environ=self.environment)),
            patch.object(launcher, "windows_api", return_value=self.api),
            patch.object(launcher, "start_app", side_effect=[10, 11]),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_normal_exit_stops_job_and_releases_mutex(self) -> None:
        """片方の正常終了でも、ジョブと全ハンドルを解放する。"""
        with redirect_stdout(io.StringIO()):
            self.assertEqual(launcher.main(self.root), 0)
        launcher.start_app.assert_has_calls([
            call(self.api, 2, self.root / "scripts/start_reception.bat", self.root),
            call(self.api, 2, self.root / "scripts/start_frontend.bat", self.root),
        ])
        self.assertEqual(self.api.CloseHandle.call_args_list, [call(2), call(10), call(11), call(1)])
        self.api.ReleaseMutex.assert_called_once_with(1)
        self.assertNotIn("PICORESQ_COMBINED_START", self.environment)

    def test_duplicate_does_not_start_or_stop_apps(self) -> None:
        """二重実行時は、既存アプリに触れず終了する。"""
        self.api.WaitForSingleObject.return_value = 258
        with redirect_stdout(io.StringIO()):
            self.assertEqual(launcher.main(self.root), 1)
        launcher.start_app.assert_not_called()
        self.api.CreateJobObjectW.assert_not_called()
        self.api.ReleaseMutex.assert_not_called()
        self.api.CloseHandle.assert_called_once_with(1)

    def test_second_start_failure_closes_first_app_job(self) -> None:
        """2個目の起動失敗でも、起動済みアプリのジョブを終了する。"""
        launcher.start_app.side_effect = [10, OSError("テスト用起動失敗")]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(launcher.main(self.root), 1)
        self.assertEqual(self.api.CloseHandle.call_args_list, [call(2), call(10), call(1)])

    def test_ctrl_c_closes_job(self) -> None:
        """Ctrl+Cでジョブ内のアプリを終了する。"""
        self.api.WaitForSingleObject.side_effect = [0, KeyboardInterrupt()]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(launcher.main(self.root), 130)
        self.api.CloseHandle.assert_any_call(2)


class WindowsProcessCreationTests(unittest.TestCase):
    """ジョブへ入れる前に子プロセスを動かさないことを検証する。"""

    def test_suspended_process_is_assigned_before_resume(self) -> None:
        """子孫を生成できるのはジョブ所属後だけであることを確認する。"""
        api = MagicMock()

        def create(*arguments: object) -> int:
            """CreateProcessWが返すハンドルを疑似的に設定する。"""
            info = ctypes.cast(arguments[-1], ctypes.POINTER(launcher.ProcessInfo)).contents
            info.process, info.thread = 10, 11
            return 1

        api.CreateProcessW.side_effect = create
        api.ResumeThread.return_value = 1
        root = SOURCE.parent.parent
        result = launcher.start_app(api, 2, root / "scripts/start_reception.bat", root)
        self.assertEqual(result, 10)
        calls = [entry[0] for entry in api.method_calls]
        self.assertLess(calls.index("AssignProcessToJobObject"), calls.index("ResumeThread"))
        self.assertTrue(api.CreateProcessW.call_args.args[5] & 0x00000004)
        api.CloseHandle.assert_called_once_with(11)

    def test_assignment_failure_terminates_suspended_process(self) -> None:
        """ジョブへ所属できなければ、停止中のプロセスも取り残さない。"""
        api = MagicMock()

        def create(*arguments: object) -> int:
            """CreateProcessWが返すハンドルを疑似的に設定する。"""
            info = ctypes.cast(arguments[-1], ctypes.POINTER(launcher.ProcessInfo)).contents
            info.process, info.thread = 10, 11
            return 1

        api.CreateProcessW.side_effect = create
        api.AssignProcessToJobObject.return_value = False
        with patch.object(ctypes, "WinError", return_value=OSError("割り当て失敗"), create=True), \
             patch.object(ctypes, "get_last_error", return_value=5, create=True):
            with self.assertRaises(OSError):
                launcher.start_app(api, 2, SOURCE, SOURCE.parent)
        api.ResumeThread.assert_not_called()
        api.TerminateProcess.assert_called_once_with(10, 1)
        self.assertEqual(api.CloseHandle.call_args_list, [call(10), call(11)])


@unittest.skipUnless(os.name == "nt", "Windows実機でのみJob Objectの動作を検証します")
class WindowsLauncherNativeTests(unittest.TestCase):
    """実アプリの代わりにダミーの親子を起動し、Windows上で検証する。"""

    def test_duplicate_and_parent_exit_stop_descendants(self) -> None:
        """空白・日本語のあるパスで起動し、二重実行防止と子孫の終了を確認する。"""
        with tempfile.TemporaryDirectory(prefix="pico resq テスト ") as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / SOURCE.name).write_bytes(SOURCE.read_bytes())
            (scripts / "dummy.py").write_text(
                "import json,os,subprocess,sys,time\n"
                "from pathlib import Path\n"
                "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
                "Path(sys.argv[1]+'.json').write_text(json.dumps([os.getpid(),child.pid]))\n"
                "time.sleep(60)\n", encoding="utf-8",
            )
            for app in ("reception", "frontend"):
                (scripts / f"start_{app}.bat").write_text(
                    f'@echo off\n"%PICORESQ_TEST_PYTHON%" "%~dp0dummy.py" {app}\n',
                    encoding="ascii",
                )
            command = [sys.executable, str(scripts / SOURCE.name)]
            environment = dict(os.environ, PICORESQ_TEST_PYTHON=sys.executable)
            process = subprocess.Popen(command, env=environment)
            handles = []
            api = launcher.windows_api()
            api.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
            api.OpenProcess.restype = ctypes.c_void_p
            try:
                deadline = time.monotonic() + 10
                while not all((root / f"{app}.json").exists() for app in ("reception", "frontend")):
                    if process.poll() is not None or time.monotonic() >= deadline:
                        self.fail("Windowsのダミーアプリを起動できませんでした")
                    time.sleep(0.05)
                for app in ("reception", "frontend"):
                    for pid in json.loads((root / f"{app}.json").read_text()):
                        handle = api.OpenProcess(0x00100000, False, pid)
                        self.assertTrue(handle)
                        handles.append(handle)
                duplicate = subprocess.run(command, env=environment, timeout=5)
                self.assertEqual(duplicate.returncode, 1)
                # finallyが実行できない強制終了でも、Job Objectが子孫を止める。
                process.terminate()
                process.wait(timeout=5)
                for handle in handles:
                    self.assertEqual(api.WaitForSingleObject(handle, 5000), 0)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                for handle in handles:
                    api.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()
