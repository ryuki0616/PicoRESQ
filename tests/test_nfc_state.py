"""NFC読み取り失敗と進捗保持を、実カードを使わずに検証する。"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import nfc_writer  # noqa: E402

SPEC = importlib.util.spec_from_file_location("nfc_cli", ROOT / "scripts/nfc_cli.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class NfcStateTests(unittest.TestCase):
    """通信失敗を未登録・未クリアに変換しないことを検証する。"""

    def setUp(self) -> None:
        """既存の参加者テストはPCの実際の管理者登録に依存させない。"""
        patcher = patch.object(cli, "_is_admin_card", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def read_card(self) -> tuple[int, dict]:
        """CLIのJSON応答を取得する。"""
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.cmd_read(argparse.Namespace(wait_seconds=0, poll_interval=0.2))
        return code, json.loads(output.getvalue())

    @patch.object(cli, "_detect_uid", return_value="A")
    @patch.object(cli, "_wait_for_uid", return_value="A")
    @patch("time.sleep")
    def test_transient_read_failure_recovers(self, *_: object) -> None:
        """一度失敗しても再試行し、古い受付内フラグよりヘッダーを優先する。"""
        with patch.object(nfc_writer, "read_reception_data", side_effect=[
            None, {"name": "テスト", "quiz_clearance_flags": 0}
        ]), patch.object(nfc_writer, "read_booth_clearance_flags", return_value=[
            True, False, True, False, False
        ]):
            code, data = self.read_card()
        self.assertEqual(code, 0)
        self.assertEqual(data["reception"]["name"], "テスト")
        self.assertEqual(data["reception"]["quiz_clearance_flags"], 5)
        self.assertEqual(data["cleared_count"], 2)

    @patch.object(cli, "_detect_uid", return_value="A")
    @patch.object(cli, "_wait_for_uid", return_value="A")
    @patch("time.sleep")
    def test_unreadable_data_is_error(self, *_: object) -> None:
        """受付情報または進捗が読めない場合、成功の空データを返さない。"""
        for reception, flags in [(None, [False] * 5), ({"name": "テスト"}, None)]:
            with self.subTest(reception=reception, flags=flags):
                with patch.object(nfc_writer, "read_reception_data", return_value=reception), \
                     patch.object(nfc_writer, "read_booth_clearance_flags", return_value=flags):
                    code, data = self.read_card()
                self.assertEqual(code, 1)
                self.assertFalse(data["ok"])
                self.assertNotIn("reception", data)
                self.assertNotIn("clearance_flags", data)

    @patch.object(cli, "_detect_uid", return_value="A")
    @patch.object(cli, "_wait_for_uid", return_value="A")
    def test_blank_card_remains_distinct_from_error(self, *_: object) -> None:
        """正常に読めた未登録カードは、通信エラーと区別する。"""
        with patch.object(nfc_writer, "read_reception_data", return_value={"name": ""}), \
             patch.object(nfc_writer, "read_booth_clearance_flags", return_value=[False] * 5):
            code, data = self.read_card()
        self.assertEqual(code, 0)
        self.assertEqual(data["reception"]["name"], "")
        self.assertEqual(data["cleared_count"], 0)

    @patch.object(cli, "_detect_uid", return_value="B")
    @patch.object(cli, "_wait_for_uid", return_value="A")
    def test_swapped_card_is_rejected(self, *_: object) -> None:
        """読み取り中にカードが交換された応答を採用しない。"""
        with patch.object(nfc_writer, "read_reception_data", return_value={"name": "テスト"}), \
             patch.object(nfc_writer, "read_booth_clearance_flags", return_value=[False] * 5):
            code, data = self.read_card()
        self.assertEqual(code, 1)
        self.assertFalse(data["ok"])

    @patch("time.sleep")
    def test_unreadable_progress_never_overwrites_card(self, *_: object) -> None:
        """既存進捗を読めなければ、書き込みそのものを行わない。"""
        with patch.object(nfc_writer, "read_booth_clearance_flags", return_value=None), \
             patch.object(nfc_writer, "write_booth_clearance_flags") as write:
            self.assertFalse(nfc_writer.set_booth_cleared("A", 2))
        write.assert_not_called()

    def test_previous_clears_are_preserved(self) -> None:
        """新しいブースをクリアしても、以前のクリアは残る。"""
        with patch.object(nfc_writer, "read_booth_clearance_flags", return_value=[
            True, False, False, False, True
        ]), patch.object(nfc_writer, "write_booth_clearance_flags", return_value=True) as write:
            self.assertTrue(nfc_writer.set_booth_cleared("A", 2))
        self.assertEqual(write.call_args.args[1], [True, True, False, False, True])

    @patch.object(cli, "_detect_uid", return_value="A")
    @patch.object(cli, "_wait_for_uid", return_value="A")
    def test_header_update_is_visible_without_changing_registration(self, *_: object) -> None:
        """ヘッダーだけの進捗更新が受付応答にも反映され、氏名・アレルギーは残る。"""
        class MemoryCard:
            """NTAGの読み書きをメモリ上で再現する。"""

            def __init__(self) -> None:
                """空のページ領域を用意する。"""
                self.pages: dict[int, list[int]] = {}

            def transmit(self, apdu: list[int]) -> tuple[list[int], int, int]:
                """データ領域への読み書きAPDUだけを処理する。"""
                if apdu[1] == 0xD6:
                    self.pages[apdu[3]] = apdu[5:9]
                    return [], 0x90, 0
                if apdu[1] == 0xB0:
                    return self.pages.get(apdu[3], [0] * 4), 0x90, 0
                raise AssertionError("想定外のAPDUです")

        card = MemoryCard()
        registration = {"name": "テスト", "allergy": "卵"}
        self.assertTrue(nfc_writer.write_reception_data_ntag213(
            card, nfc_writer.encode_reception_data(registration)
        ))
        before = dict(card.pages)
        self.assertTrue(nfc_writer.write_reception_header_ntag213(card, 1, 5))
        self.assertTrue(all(card.pages[page] == data for page, data in before.items()))
        reception = nfc_writer.decode_reception_data(
            nfc_writer.read_reception_data_ntag213(card)
        )
        bits = nfc_writer.read_reception_header_ntag213(card)[1]
        flags = [bool(bits & (1 << index)) for index in range(5)]
        with patch.object(nfc_writer, "read_reception_data", return_value=reception), \
             patch.object(nfc_writer, "read_booth_clearance_flags", return_value=flags):
            code, data = self.read_card()
        self.assertEqual(code, 0)
        self.assertEqual(data["reception"]["name"], registration["name"])
        self.assertEqual(data["reception"]["allergy"], registration["allergy"])
        self.assertEqual(data["reception"]["quiz_clearance_flags"], 5)
        self.assertEqual(data["cleared_count"], 2)


class AdminCardTests(unittest.TestCase):
    """管理者カードは参加者データを必要とせず、登録ファイルを正とする。"""

    def test_admin_lookup_uses_latest_registry_and_ignores_case(self) -> None:
        """大文字小文字を区別せず、登録変更を次の読み取りで反映する。"""
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "admin_cards.json"
            with patch.object(cli, "ADMIN_CARDS_FILE", registry):
                self.assertFalse(cli._is_admin_card("ABCD"))
                registry.write_text('{"admin_card_ids": ["abcd"]}', encoding="utf-8")
                self.assertTrue(cli._is_admin_card("ABCD"))
                self.assertFalse(cli._is_admin_card("EEEE"))
                registry.write_text('{"admin_card_ids": []}', encoding="utf-8")
                self.assertFalse(cli._is_admin_card("ABCD"))

    @patch.object(cli, "_wait_for_uid", return_value="ABCD")
    def test_admin_without_resident_data_is_recognized(self, *_: object) -> None:
        """カード内の参加者情報が読めなくても、登録済み管理者として返す。"""
        with patch.object(cli, "_is_admin_card", return_value=True), \
             patch.object(nfc_writer, "read_reception_data") as read_resident, \
             patch.object(nfc_writer, "read_booth_clearance_flags") as read_progress:
            output = io.StringIO()
            with redirect_stdout(output):
                code = cli.cmd_read(argparse.Namespace(wait_seconds=0, poll_interval=0.2))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), {
            "ok": True, "idm": "ABCD", "is_admin": True
        })
        read_resident.assert_not_called()
        read_progress.assert_not_called()

    @patch.object(cli, "_wait_for_uid", return_value="ABCD")
    def test_invalid_registry_is_not_treated_as_unregistered(self, *_: object) -> None:
        """登録ファイルの不正を未登録と誤判定しない。"""
        with patch.object(cli, "_is_admin_card", side_effect=ValueError), \
             patch.object(nfc_writer, "read_reception_data") as read_resident:
            output = io.StringIO()
            with redirect_stdout(output):
                code = cli.cmd_read(argparse.Namespace(wait_seconds=0, poll_interval=0.2))
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output.getvalue())["ok"])
        read_resident.assert_not_called()


if __name__ == "__main__":
    unittest.main()
