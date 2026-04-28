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


def _configure_stdio() -> None:
    """
    Windows を含む各環境で JSON 入出力を UTF-8 に固定する。
    """
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


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
    from smartcard.Exceptions import NoCardException

    reader_list = readers()
    if not reader_list:
        return None

    reader = reader_list[0]
    connection = reader.createConnection()
    try:
        connection.connect()
    except NoCardException:
        return None

    apdu = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    try:
        response, sw1, sw2 = connection.transmit(apdu)
        if sw1 == 0x90 and sw2 == 0x00:
            return toHexString(response).replace(" ", "")
        return None
    except NoCardException:
        return None


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
    from nfc_writer import read_reception_data, read_reception_data_raw, read_cleared_count, read_booth_clearance_flags  # type: ignore

    uid = _wait_for_uid(args.wait_seconds, args.poll_interval)
    if not uid:
        return _emit_error("カードが検知できません")

    reception = read_reception_data(uid)
    raw_reception = read_reception_data_raw(uid) if args.raw else None
    cleared_count = read_cleared_count(uid)
    clearance_flags = read_booth_clearance_flags(uid)
    # Noneの場合は空のリストにフォールバック
    if clearance_flags is None:
        clearance_flags = [False] * 5

    return _emit_ok(
        {
            "idm": uid,
            "reception": reception or {},
            "raw_reception": raw_reception,
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
    read.add_argument("--raw", action="store_true", help="受付データの生バイト診断も返す")
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
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
