"""実カードを使わず、接続の解放・再試行・プロセス間排他を検証する。"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
import nfc_connection
from scripts import nfc_cli
from smartcard.CardConnection import CardConnection
from smartcard.Exceptions import CardConnectionException, NoCardException
from smartcard.scard import SCARD_LEAVE_CARD


class NfcConnectionTests(unittest.TestCase):
    """カードの電源保持と接続競合からの復帰を検証する。"""

    def setUp(self) -> None:
        """起動中の実アプリとは別の場所でロックを検証する。"""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.lock_dir = directory.name
        patcher = patch("nfc_connection.tempfile.gettempdir", return_value=self.lock_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def reader(self, name: str = "SONY FeliCa RC-S300/P") -> MagicMock:
        """通信内容を記録できる疑似リーダーを作る。"""
        reader = MagicMock()
        reader.__str__.return_value = name
        return reader

    def test_rc_s300_uses_t1_and_leaves_card_powered(self) -> None:
        """RC-S300にはT=1と電源保持を指定し、終了時に解放する。"""
        reader = self.reader()
        with nfc_connection.card_connection(reader) as connection:
            self.assertIs(connection, reader.createConnection.return_value)
        connection.connect.assert_called_once_with(
            protocol=CardConnection.T1_protocol, disposition=SCARD_LEAVE_CARD
        )
        connection.release.assert_called_once()

    def test_other_readers_keep_protocol_negotiation(self) -> None:
        """他機種のプロトコル選択は変更せず、電源保持だけを指定する。"""
        reader = self.reader("Other reader")
        with nfc_connection.card_connection(reader) as connection:
            pass
        connection.connect.assert_called_once_with(disposition=SCARD_LEAVE_CARD)

    def test_failed_connection_is_released(self) -> None:
        """接続できなかった場合もPC/SCコンテキストを解放する。"""
        reader = self.reader()
        reader.createConnection.return_value.connect.side_effect = CardConnectionException()
        with self.assertRaises(CardConnectionException):
            with nfc_connection.card_connection(reader):
                self.fail("接続失敗後に処理を続けてはいけません")
        reader.createConnection.return_value.release.assert_called_once()

    @patch("time.sleep")
    def test_detect_retries_unresponsive_card(self, *_: object) -> None:
        """一時的に応答しなかったカードでも再接続でUIDを取得できる。"""
        reader = self.reader()
        failed, connected = MagicMock(), MagicMock()
        failed.connect.side_effect = CardConnectionException("Card is unresponsive")
        connected.transmit.return_value = ([0xAB, 0xCD], 0x90, 0)
        reader.createConnection.side_effect = [failed, connected]
        with patch("smartcard.System.readers", return_value=[reader]):
            self.assertEqual(nfc_cli._detect_uid(), "ABCD")
        failed.release.assert_called_once()
        connected.release.assert_called_once()

    def test_card_removal_is_not_a_communication_error(self) -> None:
        """カードがない場合だけ、正常な未検知として返す。"""
        reader = self.reader()
        reader.createConnection.return_value.connect.side_effect = NoCardException(
            "カードなし", 0x8010000C
        )
        with patch("smartcard.System.readers", return_value=[reader]):
            self.assertIsNone(nfc_cli._detect_uid())

    @patch("time.sleep")
    def test_persistent_connection_error_is_json(self, *_: object) -> None:
        """接続が復帰しない場合は未検知やトレースバックに置き換えない。"""
        reader = self.reader()
        reader.createConnection.return_value.connect.side_effect = CardConnectionException()
        output = io.StringIO()
        with patch("smartcard.System.readers", return_value=[reader]), \
             patch.object(sys, "argv", ["nfc_cli.py", "detect"]), redirect_stdout(output):
            code = nfc_cli.main()
        self.assertEqual(code, 1)
        data = json.loads(output.getvalue())
        self.assertFalse(data["ok"])
        self.assertIn("カードと通信できません", data["error"])
        self.assertNotIn("idm", data)
        self.assertEqual(reader.createConnection.return_value.release.call_count, 3)

    def test_operation_lock_excludes_another_process_and_is_released(self) -> None:
        """別プロセスのCLIを待たせ、例外終了後もロックを解放する。"""
        script = (
            "from nfc_connection import nfc_operation\n"
            "try:\n"
            " with nfc_operation(timeout=0.05): print('取得成功')\n"
            "except TimeoutError:\n"
            " raise SystemExit(3)\n"
        )
        command = [sys.executable, "-B", "-c", script]
        environment = dict(os.environ, TMPDIR=self.lock_dir, TMP=self.lock_dir, TEMP=self.lock_dir)
        with self.assertRaisesRegex(ValueError, "テスト"):
            with nfc_connection.nfc_operation():
                result = subprocess.run(
                    command, cwd=ROOT / "backend", env=environment, capture_output=True, timeout=5
                )
                self.assertEqual(result.returncode, 3, result.stderr)
                raise ValueError("テスト")
        result = subprocess.run(
            command, cwd=ROOT / "backend", env=environment, capture_output=True, timeout=5
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
