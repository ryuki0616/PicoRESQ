#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PicoRESQ - NFCカードのみ運用ツール（サーバー不要）

バックエンド（FastAPI）やデータベースを起動せずに、
NFCカードに対して「受付データ」「クイズ進捗（クリア数）」の読み書きを行います。

使い方:
  python3 scripts/card_only.py status
  python3 scripts/card_only.py read
  python3 scripts/card_only.py write --name "山田太郎" --address "東京都" --tel "090..." --family-count 3 --care-needed 0
  python3 scripts/card_only.py write --json ./resident.json
  python3 scripts/card_only.py write-cleared --count 2
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

    # Get Data（UID/IDm）
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


def cmd_status(args: argparse.Namespace) -> int:
    """NFCリーダー状態を表示する"""
    try:
        from smartcard.System import readers
    except ImportError:
        print("✗ pyscardがインストールされていません（NFC操作に必要です）")
        print("  対処: backend で依存を入れてから実行してください。")
        print("  - uv を使う場合: cd backend && uv sync")
        print("  - venv を使う場合: cd backend && source venv/bin/activate && pip install -r requirements.txt")
        return 1

    reader_list = readers()
    if not reader_list:
        print("✗ NFCリーダーが見つかりません")
        return 1

    print(f"✓ NFCリーダー: {len(reader_list)} 台")
    for i, r in enumerate(reader_list):
        print(f"- [{i}] {r}")

    uid = _wait_for_uid(args.wait_seconds, args.poll_interval)
    if uid:
        print(f"✓ カード検知: {uid}")
    else:
        if args.wait_seconds > 0:
            print(f"ℹ カードは未検知（{args.wait_seconds}秒待機しました）")
        else:
            print("ℹ カードは未検知（カードをタッチしてください）")
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    """受付データとクリア数を読み取って表示する"""
    _add_backend_to_syspath()
    from nfc_writer import read_reception_data, read_cleared_count  # type: ignore

    uid = _wait_for_uid(args.wait_seconds, args.poll_interval)
    if not uid:
        print("✗ カードが検知できません（リーダーにタッチしてください）")
        return 1

    reception = read_reception_data(uid)
    cleared = read_cleared_count(uid)

    print(f"✓ カード: {uid}")
    print("== 受付データ ==")
    print(json.dumps(reception or {}, ensure_ascii=False, indent=2))
    print("== クイズ進捗 ==")
    print(json.dumps({"cleared_count": cleared}, ensure_ascii=False, indent=2))
    return 0


def _load_resident_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    """
    CLI引数から受付データ辞書を構築する

    Returns:
        受付データ（name/address/tel/family_count/care_needed）
    """
    if args.json:
        p = Path(args.json)
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSONはオブジェクト形式（辞書）である必要があります")
        return data

    return {
        "name": args.name or "",
        "address": args.address or "",
        "tel": args.tel or "",
        "family_count": args.family_count,
        "care_needed": args.care_needed,
    }


def cmd_write(args: argparse.Namespace) -> int:
    """受付データをNFCカードに書き込む（サーバー不要）"""
    _add_backend_to_syspath()
    from nfc_writer import write_reception_data  # type: ignore

    uid = _wait_for_uid(args.wait_seconds, args.poll_interval)
    if not uid:
        print("✗ カードが検知できません（リーダーにタッチしてください）")
        return 1

    resident = _load_resident_from_args(args)
    resident["idm"] = uid  # 情報として付与（書き込み処理は現状、タッチ中カードに対して実行）

    print(f"✓ 対象カード: {uid}")
    print("書き込む内容（最小）:")
    print(json.dumps({k: resident.get(k) for k in ["name", "address", "tel", "family_count", "care_needed"]}, ensure_ascii=False, indent=2))

    if not args.yes:
        ans = input("この内容で書き込みますか？ [y/N]: ").strip().lower()
        if ans not in {"y", "yes"}:
            print("中断しました。")
            return 0

    ok = write_reception_data(uid, resident, max_retries=3)
    if ok:
        print("✓ 書き込み成功")
        return 0
    print("✗ 書き込み失敗（カード種別/鍵/タッチ状態を確認してください）")
    return 1


def cmd_write_cleared(args: argparse.Namespace) -> int:
    """クリア数を書き込む（サーバー不要）"""
    _add_backend_to_syspath()
    from nfc_writer import write_cleared_count  # type: ignore

    uid = _wait_for_uid(args.wait_seconds, args.poll_interval)
    if not uid:
        print("✗ カードが検知できません（リーダーにタッチしてください）")
        return 1

    ok = write_cleared_count(uid, int(args.count), max_retries=3)
    if ok:
        print(f"✓ クリア数を書き込みました: {args.count} / card={uid}")
        return 0
    print("✗ クリア数の書き込みに失敗しました")
    return 1


def build_parser() -> argparse.ArgumentParser:
    """引数パーサーを生成"""
    p = argparse.ArgumentParser(prog="card_only.py", description="PicoRESQ NFCカードのみ運用ツール")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="NFCリーダー/カード検知状態を表示")
    s.add_argument("--wait-seconds", type=float, default=0, help="カードタッチ待機秒数（0なら待機しない）")
    s.add_argument("--poll-interval", type=float, default=0.5, help="ポーリング間隔（秒）")

    r = sub.add_parser("read", help="受付データとクリア数を読み取り表示")
    r.add_argument("--wait-seconds", type=float, default=10, help="カードタッチ待機秒数")
    r.add_argument("--poll-interval", type=float, default=0.5, help="ポーリング間隔（秒）")

    w = sub.add_parser("write", help="受付データを書き込み（サーバー不要）")
    w.add_argument("--json", help="受付データJSONファイル（辞書）", default=None)
    w.add_argument("--name", help="氏名", default=None)
    w.add_argument("--address", help="住所", default=None)
    w.add_argument("--tel", help="電話番号（ASCII）", default=None)
    w.add_argument("--family-count", type=int, default=0, help="世帯人数（0-255）")
    w.add_argument("--care-needed", type=int, default=0, help="要介護（0/1）")
    w.add_argument("-y", "--yes", action="store_true", help="確認なしで書き込む")
    w.add_argument("--wait-seconds", type=float, default=10, help="カードタッチ待機秒数")
    w.add_argument("--poll-interval", type=float, default=0.5, help="ポーリング間隔（秒）")

    wc = sub.add_parser("write-cleared", help="クイズ進捗（クリア数）を書き込み")
    wc.add_argument("--count", type=int, required=True, help="クリア数（0-5）")
    wc.add_argument("--wait-seconds", type=float, default=10, help="カードタッチ待機秒数")
    wc.add_argument("--poll-interval", type=float, default=0.5, help="ポーリング間隔（秒）")

    return p


def main() -> int:
    """エントリーポイント"""
    args = build_parser().parse_args()
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "read":
        return cmd_read(args)
    if args.cmd == "write":
        return cmd_write(args)
    if args.cmd == "write-cleared":
        return cmd_write_cleared(args)
    print("✗ 不明なコマンドです")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

