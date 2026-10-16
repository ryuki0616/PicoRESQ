#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PicoRESQ - NFCカード操作CLI（オフライン用）

Electronから呼び出すことを想定し、JSON入出力で結果を返す。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _add_backend_to_syspath() -> Path:
    """
    `backend/` を import 対象に追加して、nfc_writer.py を読み込めるようにする。

    Returns:
        backendディレクトリのPath
    """
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    backend_dir = project_root / "backend"
    sys.path.insert(0, str(backend_dir))
    return backend_dir


def _detect_uid() -> Optional[str]:
    """
    現在タッチされているカードのUID/IDmを取得する（可能な範囲で）。

    Returns:
        UID/IDm（16進文字列）、取得失敗時はNone
    """
    from smartcard.System import readers
    from smartcard.util import toHexString
    from smartcard.Exceptions import NoCardException, CardConnectionException
    _add_backend_to_syspath()
    from nfc_connection import card_connection
    from nfc_writer import _select_preferred_reader

    reader_list = readers()
    if not reader_list:
        return None

    reader = _select_preferred_reader(reader_list)
    for attempt in range(3):
        try:
            with card_connection(reader) as connection:
                response, sw1, sw2 = connection.transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
                if sw1 == 0x90 and sw2 == 0x00:
                    return toHexString(response).replace(" ", "")
                raise CardConnectionException("カードIDを読み取れませんでした")
        except NoCardException:
            return None
        except CardConnectionException:
            if attempt == 2:
                raise
            time.sleep(0.1)


def _wait_for_uid(wait_seconds: float, poll_interval: float) -> Optional[str]:
    """
    一定時間、カードのタッチを待ってUID/IDmを取得する。

    Args:
        wait_seconds: 待機秒数（0以下なら即時判定）
        poll_interval: ポーリング間隔（秒）

    Returns:
        UID/IDm（16進文字列）、時間切れ/未検知ならNone
    """
    if wait_seconds <= 0:
        return _detect_uid()

    deadline = time.time() + wait_seconds
    while True:
        uid = _detect_uid()
        if uid:
            return uid
        if time.time() >= deadline:
            return None
        time.sleep(max(poll_interval, 0.05))


def _emit_ok(payload: Dict[str, Any]) -> int:
    """成功レスポンスをJSONで出力する"""
    print(json.dumps({"ok": True, **payload}, ensure_ascii=False))
    return 0


def _emit_error(message: str) -> int:
    """エラーレスポンスをJSONで出力する"""
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    return 1


def cmd_detect(args: argparse.Namespace) -> int:
    """カード検知"""
    uid = _wait_for_uid(args.wait_seconds, args.poll_interval)
    return _emit_ok({"idm": uid})


def cmd_read(args: argparse.Namespace) -> int:
    """カード内容を読み取る"""
    _add_backend_to_syspath()
    from nfc_writer import read_reception_data, read_booth_clearance_flags  # type: ignore

    uid = _wait_for_uid(args.wait_seconds, args.poll_interval)
    if not uid:
        return _emit_error("カードが検知できません")

    # 通信失敗を空の登録情報や未クリアに置き換えない。
    for attempt in range(3):
        reception = read_reception_data(uid)
        clearance_flags = read_booth_clearance_flags(uid)
        if _detect_uid() != uid:
            return _emit_error("カードが離れたか、別のカードに交換されました")
        if reception is not None and clearance_flags is not None:
            break
        if attempt < 2:
            time.sleep(0.2)
    else:
        return _emit_error("カード情報を読み取れませんでした。カードを置いたまま再試行してください")

    # 両画面ともヘッダーのクリアフラグを正とし、旧データ領域の値は使わない。
    reception["quiz_clearance_flags"] = sum(
        1 << index for index, cleared in enumerate(clearance_flags) if cleared
    )
    cleared_count = sum(clearance_flags)

    return _emit_ok(
        {
            "idm": uid,
            "reception": reception,
            "cleared_count": cleared_count,
            "clearance_flags": clearance_flags,
        }
    )




def _load_payload(args: argparse.Namespace) -> Dict[str, Any]:
    """
    JSON入力（ファイル or STDIN）を読み込む
    """
    if args.json == "-":
        data = json.loads(sys.stdin.read())
    else:
        path = Path(args.json)
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSONはオブジェクト形式（辞書）である必要があります")
    return data


def cmd_write(args: argparse.Namespace) -> int:
    """受付データを書き込む"""
    _add_backend_to_syspath()
    from nfc_writer import write_reception_data  # type: ignore

    uid = _wait_for_uid(args.wait_seconds, args.poll_interval)
    if not uid:
        return _emit_error("カードが検知できません")

    try:
        payload = _load_payload(args)
    except Exception as e:
        return _emit_error(f"JSON読み込みエラー: {e}")

    payload["idm"] = uid
    ok = write_reception_data(uid, payload, max_retries=3)
    if ok:
        return _emit_ok({"idm": uid})
    return _emit_error("書き込みに失敗しました")


def cmd_write_cleared(args: argparse.Namespace) -> int:
    """クリア数を書き込む"""
    _add_backend_to_syspath()
    from nfc_writer import write_cleared_count  # type: ignore

    uid = _wait_for_uid(args.wait_seconds, args.poll_interval)
    if not uid:
        return _emit_error("カードが検知できません")

    ok = write_cleared_count(uid, int(args.count), max_retries=3)
    if ok:
        return _emit_ok({"idm": uid, "cleared_count": int(args.count)})
    return _emit_error("クリア数の書き込みに失敗しました")


def cmd_set_booth_cleared(args: argparse.Namespace) -> int:
    """ブースのクリアフラグを設定する"""
    _add_backend_to_syspath()
    from nfc_writer import set_booth_cleared  # type: ignore

    uid = _wait_for_uid(args.wait_seconds, args.poll_interval)
    if not uid:
        return _emit_error("カードが検知できません")

    ok = set_booth_cleared(uid, int(args.booth_id), max_retries=3)
    if ok:
        return _emit_ok({"idm": uid, "booth_id": int(args.booth_id)})
    return _emit_error("クリアフラグの書き込みに失敗しました")


def cmd_erase(args: argparse.Namespace) -> int:
    """カードデータを完全消去する（セキュリティ対策）"""
    _add_backend_to_syspath()
    from nfc_writer import erase_card_data  # type: ignore

    uid = _wait_for_uid(args.wait_seconds, args.poll_interval)
    if not uid:
        return _emit_error("カードが検知できません")

    ok = erase_card_data(uid, max_retries=3)
    if ok:
        return _emit_ok({"idm": uid, "erased": True})
    return _emit_error("カードデータの消去に失敗しました")


def build_parser() -> argparse.ArgumentParser:
    """CLI引数定義"""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    detect = sub.add_parser("detect", help="カード検知")
    detect.add_argument("--wait-seconds", type=float, default=0.0)
    detect.add_argument("--poll-interval", type=float, default=0.2)
    detect.set_defaults(func=cmd_detect)

    read = sub.add_parser("read", help="カード読み取り")
    read.add_argument("--wait-seconds", type=float, default=5.0)
    read.add_argument("--poll-interval", type=float, default=0.2)
    read.set_defaults(func=cmd_read)


    write = sub.add_parser("write", help="カード書き込み（JSON）")
    write.add_argument("--json", required=True, help="JSONファイルのパス、または '-' でSTDIN")
    write.add_argument("--wait-seconds", type=float, default=10.0)
    write.add_argument("--poll-interval", type=float, default=0.2)
    write.set_defaults(func=cmd_write)

    cleared = sub.add_parser("write-cleared", help="クリア数を書き込み")
    cleared.add_argument("--count", required=True, type=int)
    cleared.add_argument("--wait-seconds", type=float, default=10.0)
    cleared.add_argument("--poll-interval", type=float, default=0.2)
    cleared.set_defaults(func=cmd_write_cleared)

    booth = sub.add_parser("set-booth-cleared", help="ブースクリアフラグ設定")
    booth.add_argument("--booth-id", required=True, type=int)
    booth.add_argument("--wait-seconds", type=float, default=10.0)
    booth.add_argument("--poll-interval", type=float, default=0.2)
    booth.set_defaults(func=cmd_set_booth_cleared)

    erase = sub.add_parser("erase", help="カードデータを完全消去（セキュリティ対策）")
    erase.add_argument("--wait-seconds", type=float, default=3.0)  # 事前にカード検知済みなので短めに
    erase.add_argument("--poll-interval", type=float, default=0.2)
    erase.set_defaults(func=cmd_erase)

    return parser


def main() -> int:
    """エントリーポイント"""
    parser = build_parser()
    args = parser.parse_args()
    _add_backend_to_syspath()
    from nfc_connection import nfc_operation
    from smartcard.Exceptions import CardConnectionException

    try:
        with nfc_operation():
            return args.func(args)
    except CardConnectionException:
        return _emit_error("カードと通信できませんでした。カードを置いたまま再試行してください")
    except TimeoutError as error:
        return _emit_error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
