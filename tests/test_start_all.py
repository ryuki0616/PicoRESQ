"""実アプリの代わりにダミーを起動し、統一起動のプロセス管理を検証する。"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


@unittest.skipUnless(
    sys.platform.startswith("linux") and all(shutil.which(name) for name in ("bash", "flock", "setsid")),
    "Linux用起動スクリプトの検証に必要なコマンドがありません",
)
class StartAllTests(unittest.TestCase):
    """同時起動・二重実行防止・子孫プロセスの終了を確認する。"""

    def setUp(self) -> None:
        """本物のElectronを起動しない一時プロジェクトを用意する。"""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        shutil.copyfile(
            Path(__file__).resolve().parents[1] / "scripts/start_all.sh",
            self.scripts / "start_all.sh",
        )
        self.environment = dict(os.environ, TMPDIR=str(self.root))
        self.process: subprocess.Popen | None = None
        self.addCleanup(self.stop)
        for app in ("reception", "frontend"):
            (self.scripts / f"start_{app}.sh").write_text(
                f'sleep 60 &\nchild=$!\necho "$$ $child" > {app}.pids\nwait "$child"\n',
                encoding="utf-8",
            )

    def start(self) -> None:
        """統一起動を開始し、ダミーの両アプリが動くまで待つ。"""
        self.process = subprocess.Popen(
            ["bash", str(self.scripts / "start_all.sh")],
            env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, start_new_session=True,
        )
        deadline = time.monotonic() + 5
        while not all((self.root / f"{app}.pids").exists() for app in ("reception", "frontend")):
            if self.process.poll() is not None or time.monotonic() >= deadline:
                self.fail("ダミーアプリの同時起動に失敗しました")
            time.sleep(0.02)

    def stop(self) -> None:
        """テスト失敗時も、作成したダミープロセスだけを後始末する。"""
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            if self.process.stdout is not None:
                self.process.stdout.close()
        for file in self.root.glob("*.pids"):
            pid = int(file.read_text().split()[0])
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def assert_apps_stopped(self) -> None:
        """npm/Electron相当の子孫も動作し続けていないことを確認する。"""
        for file in self.root.glob("*.pids"):
            for pid in map(int, file.read_text().split()):
                stat = Path(f"/proc/{pid}/stat")
                if stat.exists():
                    self.assertEqual(stat.read_text().split()[2], "Z", f"PID {pid} が残っています")

    def test_concurrent_start_duplicate_rejected_and_ctrl_c_stops_children(self) -> None:
        """両アプリを起動し、二重実行を防ぎ、Ctrl+Cで子孫も停止する。"""
        self.start()
        duplicate = subprocess.run(
            ["bash", str(self.scripts / "start_all.sh")], env=self.environment,
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(duplicate.returncode, 1)
        self.assertIn("すでに実行中", duplicate.stderr)
        self.process.send_signal(signal.SIGINT)
        self.assertEqual(self.process.wait(timeout=5), 130)
        self.assert_apps_stopped()

    def test_app_exit_stops_other_app(self) -> None:
        """片方を閉じた場合は、残りのアプリも停止する。"""
        self.start()
        reception_pid = int((self.root / "reception.pids").read_text().split()[0])
        os.kill(reception_pid, signal.SIGTERM)
        self.assertNotEqual(self.process.wait(timeout=5), 0)
        self.assert_apps_stopped()

    def test_start_failure_stops_remaining_app(self) -> None:
        """一方の起動失敗を返し、他方のプロセスを残さない。"""
        (self.scripts / "start_frontend.sh").write_text("sleep 0.2\nexit 7\n", encoding="utf-8")
        self.process = subprocess.Popen(
            ["bash", str(self.scripts / "start_all.sh")], env=self.environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self.assertEqual(self.process.wait(timeout=5), 7)
        self.assert_apps_stopped()


if __name__ == "__main__":
    unittest.main()
