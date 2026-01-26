"""
クイズデータ読み込みユーティリティ

quiz_data.jsonからクイズデータを読み込む機能を提供します。
各試練には3つの問題が含まれています。
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import random


def load_quizzes() -> List[Dict[str, Any]]:
    """
    quiz_data.jsonからクイズデータを読み込む
    
    Returns:
        クイズデータのリスト
    """
    json_path = Path(__file__).parent / "quiz_data.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["quizzes"]


def get_quizzes_by_booth_id(booth_id: int) -> List[Dict[str, Any]]:
    """
    ブースIDから該当するすべてのクイズを取得
    
    Args:
        booth_id: ブースID（1-5）
    
    Returns:
        該当するブースのクイズデータのリスト
    
    Raises:
        ValueError: 指定されたブースIDのクイズが見つからない場合
    """
    quizzes = load_quizzes()
    booth_quizzes = [quiz for quiz in quizzes if quiz["booth_id"] == booth_id]
    if not booth_quizzes:
        raise ValueError(f"Quiz not found for booth_id: {booth_id}")
    return booth_quizzes


def get_quiz_by_booth_id(booth_id: int, quiz_number: Optional[int] = None) -> Dict[str, Any]:
    """
    ブースIDからクイズを取得
    
    Args:
        booth_id: ブースID（1-5）
        quiz_number: クイズ番号（1-3）。指定しない場合はランダムに1つ選択
    
    Returns:
        クイズデータの辞書
    
    Raises:
        ValueError: 指定されたブースIDまたはクイズ番号のクイズが見つからない場合
    """
    booth_quizzes = get_quizzes_by_booth_id(booth_id)
    
    if quiz_number is not None:
        # 指定されたクイズ番号のクイズを取得
        for quiz in booth_quizzes:
            if quiz.get("quiz_number") == quiz_number:
                return quiz
        raise ValueError(f"Quiz not found for booth_id: {booth_id}, quiz_number: {quiz_number}")
    else:
        # ランダムに1つ選択
        return random.choice(booth_quizzes)
