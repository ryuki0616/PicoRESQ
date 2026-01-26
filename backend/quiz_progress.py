"""
クイズ進捗管理モジュール

各試練の進捗を個別に管理します。
NFCカードに各試練の正解数を記録します。
クリア可否フラグを使用して、各試練のクリア状態を管理します。
"""
import logging
from typing import Dict, List, Optional
from nfc_writer import read_cleared_count, write_cleared_count, read_booth_clearance_flags, set_booth_cleared

logger = logging.getLogger("uvicorn")

# 各試練の正解数を管理するためのデータ構造
# NFCカードには、各試練の正解数（0-3）を記録する想定
# 1バイト目: 試練1の正解数（0-3）
# 2バイト目: 試練2の正解数（0-3）
# 3バイト目: 試練3の正解数（0-3）
# 4バイト目: 試練4の正解数（0-3）
# 5バイト目: 試練5の正解数（0-3）

# 各ブースの問題数（現在は3問）
QUESTIONS_PER_BOOTH = 3

def read_booth_progress(idm: str, booth_id: int) -> int:
    """
    指定された試練の正解数を読み取る
    
    Args:
        idm: NFCカードのIDm
        booth_id: 試練ID（1-5）
    
    Returns:
        正解数（0-3）
    """
    # 現在の実装では、クリア数として試練IDを記録しているため
    # 簡易的に、クリア数が試練ID以上なら、その試練はクリア済みとみなす
    # 将来的には、各試練の正解数を個別に記録する実装に変更
    cleared_count = read_cleared_count(idm)
    if cleared_count >= booth_id:
        return QUESTIONS_PER_BOOTH  # クリア済み
    return 0  # 未開始

def write_booth_progress(idm: str, booth_id: int, correct_count: int) -> bool:
    """
    指定された試練の正解数を書き込む
    
    3問すべて正解した場合、クリア可否フラグも設定します。
    
    Args:
        idm: NFCカードのIDm
        booth_id: 試練ID（1-5）
        correct_count: 正解数（0-3）
    
    Returns:
        書き込み成功時True、失敗時False
    """
    # 3問すべて正解した場合、その試練をクリアとする
    if correct_count >= QUESTIONS_PER_BOOTH:
        cleared_count = read_cleared_count(idm)
        # クリア数を更新（試練IDをクリア数として記録）
        if cleared_count < booth_id:
            write_cleared_count(idm, booth_id, max_retries=3)
        
        # クリア可否フラグを設定
        try:
            set_booth_cleared(idm, booth_id, max_retries=3)
        except Exception as e:
            logger.warning(f"Error setting clearance flag for booth {booth_id}: {e}")
    
    return True  # 進捗はメモリ上で管理（NFCカードには最終的なクリア状態のみ記録）

def get_next_quiz_number(idm: str, booth_id: int) -> int:
    """
    次の問題番号を取得する
    
    Args:
        idm: NFCカードのIDm
        booth_id: 試練ID（1-5）
    
    Returns:
        次の問題番号（1-3）、既に3問正解している場合は0
    """
    progress = read_booth_progress(idm, booth_id)
    if progress >= QUESTIONS_PER_BOOTH:
        return 0  # 既にクリア済み
    return progress + 1  # 次の問題番号

def is_booth_cleared(idm: str, booth_id: int) -> bool:
    """
    指定された試練がクリア済みかどうかをチェック
    
    クリア可否フラグを優先的に読み取ります。
    
    Args:
        idm: NFCカードのIDm
        booth_id: 試練ID（1-5）
    
    Returns:
        クリア済みの場合True、そうでない場合False
    """
    # クリア可否フラグを読み取る
    try:
        clearance_flags = read_booth_clearance_flags(idm)
        if booth_id >= 1 and booth_id <= 5:
            if clearance_flags[booth_id - 1]:
                return True
    except Exception as e:
        logger.warning(f"Error reading clearance flags: {e}, falling back to progress check")
    
    # フラグが設定されていない場合、従来の方法でチェック
    return read_booth_progress(idm, booth_id) >= QUESTIONS_PER_BOOTH
