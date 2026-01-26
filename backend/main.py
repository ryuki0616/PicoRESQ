"""
PicoRESQ クイズシステム - FastAPI バックエンドサーバー

このモジュールは、NFCカード検知、クイズ管理、WebSocket通信を提供する
FastAPIアプリケーションです。

主な機能:
- NFCカード検知とリアルタイム通知
- クイズ問題の提供
- クイズ回答の検証
- NFCカードへの進捗記録
- WebSocketによるリアルタイム通信
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from database import engine, SessionLocal, Base, Resident, get_db, init_db
from nfc_reader import NFCReader
from nfc_writer import read_cleared_count, write_cleared_count, write_reception_data, read_reception_data, read_card_pages_ntag213, detect_card_type, read_booth_clearance_flags, set_booth_cleared
from quiz_data import get_quiz_by_booth_id, load_quizzes, get_quizzes_by_booth_id
from quiz_progress import get_next_quiz_number, write_booth_progress, is_booth_cleared, read_booth_progress

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

app = FastAPI(
    title="PicoRESQ API",
    description="NFC防災ヒーロー育成ラリー用クイズシステムのバックエンドAPI",
    version="1.0.0"
)

# 定数定義
# ログ出力用の日本語ラベル定義
LABEL_MAP: Dict[str, str] = {
    "idm": "利用者ID",
    "name": "利用者名",
    "kana": "フリガナ",
    "address": "住所",
    "tel": "電話番号",
    "family_count": "世帯人数",
    "vulnerabilities": "要配慮者情報",
    "medical": "医療・健康情報",
    "allergy": "アレルギー情報",
    "care_needed": "要介護か？",
    "evacuation_type": "避難場所はどこか？",
    "agree_info": "第三者提供への同意",
    "agree_board": "掲示板掲示への同意",
    "registered_at": "登録日"
}

VULNERABILITY_LABELS: Dict[str, str] = {
    "eld": "高齢者か？",
    "inf": "乳幼児か？",
    "prg": "妊産婦か？",
    "dis": "障害者か？",
    "for": "外国人か？"
}

# クイズの1ブースあたりの問題数
QUESTIONS_PER_BOOTH = 3

def print_rich_log(data: Dict[str, Any]) -> None:
    """
    避難者情報を整形してログ出力する
    
    Args:
        data: 避難者情報の辞書（idm, name, kana, address等を含む）
    """
    print("\n" + "─" * 60)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"✅ [{timestamp}] 受付: ID={data.get('idm', 'Unknown')}")
    print("{")
    
    for key, value in data.items():
        if key == "vulnerabilities" and isinstance(value, dict):
            print(f'  "{key}": {{')
            for v_key, v_val in value.items():
                v_label = VULNERABILITY_LABELS.get(v_key, v_key)
                print(f'    "{v_key}": {v_val},'.ljust(30) + f"{v_label}")
            print('  },')
            continue
            
        label = LABEL_MAP.get(key, "")
        val_str = f'"{value}"' if isinstance(value, str) else str(value)
        line = f'  "{key}": {val_str},'
        
        # 右側に日本語ラベルを表示（位置揃え）
        if label:
            print(f"{line:<40} {label}")
        else:
            print(line)
            
    print("}")
    print("─" * 60 + "\n")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket Manager
class ConnectionManager:
    """
    WebSocket接続を管理するクラス
    
    複数のクライアントへのブロードキャスト機能を提供します。
    """
    
    def __init__(self) -> None:
        """ConnectionManagerの初期化"""
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """
        WebSocket接続を受け入れる
        
        Args:
            websocket: 接続するWebSocketクライアント
        """
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """
        WebSocket接続を切断する
        
        Args:
            websocket: 切断するWebSocketクライアント
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        """
        全ての接続中のクライアントにメッセージをブロードキャストする
        
        Args:
            message: 送信するメッセージ（JSON文字列）
        """
        logger.info(f"Broadcasting to {len(self.active_connections)} connection(s)")
        if len(self.active_connections) == 0:
            logger.warning("No active WebSocket connections to broadcast to")
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
                logger.debug(f"Message sent successfully to connection")
            except Exception as e:
                logger.error(f"Error broadcasting: {e}")
                import traceback
                logger.error(traceback.format_exc())

manager = ConnectionManager()

# グローバル変数（イベントループ用）
loop: Optional[asyncio.AbstractEventLoop] = None

# 現在選択されている試練（ブース）ID（管理者が選択）
current_selected_booth_id: Optional[int] = None

# セッション進捗管理（カードIDm -> {ブースID -> 正解数}）
session_progress: Dict[str, Dict[int, int]] = {}

# 管理者カード管理
ADMIN_CARDS_FILE = Path(__file__).parent / "admin_cards.json"

def load_admin_cards() -> List[str]:
    """
    管理者カードのIDmリストを読み込む
    
    Returns:
        管理者カードのIDmリスト
    """
    try:
        if ADMIN_CARDS_FILE.exists():
            with open(ADMIN_CARDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("admin_card_ids", [])
        return []
    except Exception as e:
        logger.error(f"Error loading admin cards: {e}")
        return []

def is_admin_card(idm: str) -> bool:
    """
    指定されたIDmが管理者カードかどうかをチェック
    
    Args:
        idm: チェックするカードのIDm
    
    Returns:
        管理者カードの場合True、そうでない場合False
    """
    admin_cards = load_admin_cards()
    return idm.upper() in [card.upper() for card in admin_cards]

# NFC Handler
def on_nfc_detected(idm: str) -> None:
    """
    NFCカード検知時のコールバック関数
    
    Args:
        idm: 検知されたNFCカードのIDm（識別子）
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_admin = is_admin_card(idm)
    card_type = "管理者カード" if is_admin else "ユーザーカード"
    print(f"\n🔔 [{timestamp}] カード検知: ID={idm} ({card_type})")
    logger.info(f"Card detected: ID={idm}, is_admin={is_admin}")
    
    # NFCスレッドから実行されるため、イベントループでブロードキャストをスケジュール
    if loop is not None:
        # 受付システム用のメッセージ（nfc_detected）
        message_reception = json.dumps({
            "type": "nfc_detected",
            "idm": idm
        })
        asyncio.run_coroutine_threadsafe(manager.broadcast(message_reception), loop)
        
        # クイズシステム用のメッセージ（card_detected）
        message_quiz = json.dumps({
            "type": "card_detected",
            "idm": idm,
            "is_admin": is_admin
        })
        logger.info(f"Broadcasting WebSocket message: {message_quiz}")
        logger.info(f"Active WebSocket connections: {len(manager.active_connections)}")
        asyncio.run_coroutine_threadsafe(manager.broadcast(message_quiz), loop)
    else:
        logger.error("Event loop is None, cannot broadcast WebSocket message")
        print("⚠️  イベントループが利用できません。WebSocketメッセージを送信できません。")

def on_nfc_removed(idm: str) -> None:
    """
    NFCカード離脱時のコールバック関数
    
    Args:
        idm: 離脱したNFCカードのIDm（識別子）
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n🔔 [{timestamp}] カード離脱: ID={idm}")
    
    # セッション進捗をリセット
    global session_progress
    if idm in session_progress:
        del session_progress[idm]
    
    # NFCスレッドから実行されるため、イベントループでブロードキャストをスケジュール
    if loop is not None:
        # 受付システム用のメッセージ（nfc_removedは送信しない、card_removedのみ）
        # クイズシステム用のメッセージ（card_removed）
        message = json.dumps({"type": "card_removed", "idm": idm})
        logger.info(f"Broadcasting card_removed message: {message}")
        asyncio.run_coroutine_threadsafe(manager.broadcast(message), loop)

nfc_reader = NFCReader(on_tag_detected=on_nfc_detected, on_tag_removed=on_nfc_removed)

@app.on_event("startup")
async def startup_event() -> None:
    """
    アプリケーション起動時のイベントハンドラ
    
    データベースの初期化とNFCリーダーの起動を行います。
    """
    global loop
    loop = asyncio.get_event_loop()
    
    # データベースの初期化
    init_db()
    
    # NFCリーダーの状態を確認
    try:
        from smartcard.System import readers
        reader_list = readers()
        if not reader_list:
            logger.warning("No NFC readers found at startup")
            print("\n⚠️  起動時にNFCリーダーが見つかりませんでした。")
            print("   リーダーを接続してから、サーバーを再起動してください。")
        else:
            logger.info(f"Found {len(reader_list)} NFC reader(s) at startup")
            print(f"\n✓ 起動時に{len(reader_list)}台のNFCリーダーを検出しました")
    except Exception as e:
        logger.error(f"Error checking NFC readers at startup: {e}")
        print(f"\n✗ NFCリーダーの確認中にエラーが発生しました: {e}")
    
    # NFCリーダーを起動
    nfc_reader.start()
    logger.info("PicoRESQ サーバーが起動しました")
    print("\n✓ PicoRESQ サーバーが起動しました")
    print("   APIドキュメント: http://127.0.0.1:8000/docs")
    print("   NFCリーダー状態: http://127.0.0.1:8000/api/system/nfc-status")

@app.on_event("shutdown")
def shutdown_event() -> None:
    """
    アプリケーション終了時のイベントハンドラ
    
    NFCリーダーを停止します。
    """
    nfc_reader.stop()
    logger.info("PicoRESQ サーバーを終了しました")

# Routes
@app.post("/api/quiz/start/{booth_id}")
async def start_quiz(booth_id: int, request: Dict[str, Any]) -> Dict[str, Any]:
    """
    クイズを開始する
    
    Args:
        booth_id: ブースID（1-5、0の場合は管理者が選択した試練を使用）
        request: リクエストボディ（idmを含む）
    
    Returns:
        クイズ情報と進捗状況
    """
    idm = request.get("idm")
    if not idm:
        raise HTTPException(status_code=400, detail="idm is required")
    
    # booth_idが0の場合は、管理者が選択した試練を使用
    global current_selected_booth_id
    if booth_id == 0:
        if current_selected_booth_id is None:
            raise HTTPException(status_code=400, detail="管理者が試練を選択していません")
        booth_id = current_selected_booth_id
    
    if booth_id < 1 or booth_id > 5:
        raise HTTPException(status_code=400, detail="booth_id must be between 1 and 5")
    
    try:
        # NFCカードからクリア数を読み取り
        cleared_count = read_cleared_count(idm)
        
        # セッション進捗を初期化（カードが離れたらリセットされる）
        if idm not in session_progress:
            session_progress[idm] = {}
        if booth_id not in session_progress[idm]:
            # カードから進捗を読み取る
            session_progress[idm][booth_id] = read_booth_progress(idm, booth_id)
        
        current_correct_count = session_progress[idm][booth_id]
        
        # 既に3問すべて正解しているかチェック
        already_cleared = current_correct_count >= QUESTIONS_PER_BOOTH
        
        if already_cleared:
            # 既にクリア済みの場合は、最初の問題を返す（再挑戦用）
            quiz_number = 1
        else:
            # 次の問題番号を取得
            quiz_number = current_correct_count + 1
        
        # クイズ問題を取得（指定された問題番号）
        quiz = get_quiz_by_booth_id(booth_id, quiz_number)
        
        # WebSocketイベントを送信
        if loop is not None:
            message = json.dumps({
                "type": "quiz_started",
                "idm": idm,
                "booth_id": booth_id,
                "quiz_number": quiz.get("quiz_number"),
                "cleared_count": cleared_count
            })
            asyncio.run_coroutine_threadsafe(manager.broadcast(message), loop)
        
        return {
            "quiz": quiz,
            "cleared_count": cleared_count,
            "already_cleared": already_cleared
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting quiz: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/quiz/answer")
async def answer_quiz(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    クイズに回答する
    
    Args:
        request: リクエストボディ（idm, booth_id, answerを含む）
    
    Returns:
        回答結果と進捗状況
    """
    idm = request.get("idm")
    booth_id = request.get("booth_id")
    answer = request.get("answer")
    
    if not idm or booth_id is None or answer is None:
        raise HTTPException(status_code=400, detail="idm, booth_id, and answer are required")
    
    if booth_id < 1 or booth_id > 5:
        raise HTTPException(status_code=400, detail="booth_id must be between 1 and 5")
    
    try:
        # クイズ問題を取得（quiz_numberが指定されている場合はそれを使用、なければランダム）
        quiz_number = request.get("quiz_number")
        quiz = get_quiz_by_booth_id(booth_id, quiz_number)
        
        # セッション進捗を確認
        if idm not in session_progress:
            session_progress[idm] = {}
        if booth_id not in session_progress[idm]:
            session_progress[idm][booth_id] = read_booth_progress(idm, booth_id)
        
        current_correct_count = session_progress[idm][booth_id]
        quiz_number = request.get("quiz_number", 1)
        
        # 正解チェック
        correct = answer == quiz["correct_answer"]
        booth_cleared = False
        all_cleared = False
        new_correct_count = current_correct_count
        
        if correct:
            # 正解数を増やす
            new_correct_count = min(current_correct_count + 1, QUESTIONS_PER_BOOTH)
            session_progress[idm][booth_id] = new_correct_count
            
            # 3問すべて正解した場合、試練をクリアとする
            if new_correct_count >= QUESTIONS_PER_BOOTH:
                booth_cleared = True
                # NFCカードにクリア状態を書き込む
                write_booth_progress(idm, booth_id, new_correct_count)
                
                # 全試練クリアチェック
                cleared_count = read_cleared_count(idm)
                if cleared_count >= 5:
                    all_cleared = True
            
            # WebSocketイベントを送信
            if loop is not None:
                message = json.dumps({
                    "type": "quiz_answered",
                    "idm": idm,
                    "booth_id": booth_id,
                    "correct": correct,
                    "correct_count": new_correct_count,
                    "booth_cleared": booth_cleared
                })
                asyncio.run_coroutine_threadsafe(manager.broadcast(message), loop)
                
                if booth_cleared:
                    cleared_message = json.dumps({
                        "type": "booth_cleared",
                        "idm": idm,
                        "booth_id": booth_id,
                        "cleared_count": cleared_count
                    })
                    asyncio.run_coroutine_threadsafe(manager.broadcast(cleared_message), loop)
                
                if all_cleared:
                    all_cleared_message = json.dumps({
                        "type": "all_cleared",
                        "idm": idm,
                        "cleared_count": cleared_count
                    })
                    asyncio.run_coroutine_threadsafe(manager.broadcast(all_cleared_message), loop)
        
        return {
            "correct": correct,
            "explanation": quiz["explanation"],
            "correct_count": new_correct_count,
            "booth_cleared": booth_cleared,
            "all_cleared": all_cleared,
            "next_quiz_number": new_correct_count + 1 if new_correct_count < QUESTIONS_PER_BOOTH else None
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error answering quiz: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/quiz/progress/{idm}")
async def get_progress(idm: str) -> Dict[str, Any]:
    """
    進捗状況を取得する
    
    Args:
        idm: NFCカードのIDm
    
    Returns:
        進捗状況（クリアした試練の数と各試練のクリア状態）
    """
    try:
        cleared_count = read_cleared_count(idm)
        
        # 各試練のクリア状態を取得（NFCカードから直接読み取る）
        clearance_flags = read_booth_clearance_flags(idm)
        booth_status = {}
        for booth_id in range(1, 6):
            booth_status[booth_id] = clearance_flags[booth_id - 1] if booth_id - 1 < len(clearance_flags) else False
        
        return {
            "cleared_count": cleared_count,
            "total_booths": 5,
            "booth_status": booth_status,
            "clearance_flags": clearance_flags
        }
    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/quiz/finish")
async def finish_quiz(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    最終判定を行う
    
    Args:
        request: リクエストボディ（idmを含む）
    
    Returns:
        最終判定結果
    """
    idm = request.get("idm")
    if not idm:
        raise HTTPException(status_code=400, detail="idm is required")
    
    try:
        cleared_count = read_cleared_count(idm)
        all_cleared = cleared_count >= 5
        
        return {
            "all_cleared": all_cleared,
            "cleared_count": cleared_count
        }
    except Exception as e:
        logger.error(f"Error finishing quiz: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/quiz/list")
async def list_quizzes() -> Dict[str, Any]:
    """
    全クイズのリストを取得する
    
    Returns:
        全クイズのリスト
    """
    try:
        quizzes = load_quizzes()
        return {"quizzes": quizzes}
    except Exception as e:
        logger.error(f"Error listing quizzes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/write-card", response_model=Dict[str, Any])
def write_card_only(
    resident: Dict[str, Any]
) -> Dict[str, Any]:
    """
    NFCカードにのみ書き込む（データベースには保存しない）
    
    Args:
        resident: 避難者情報の辞書
            - idm: NFCカードのIDm（必須）
            - name: 氏名
            - kana: フリガナ
            - address: 住所
            - tel: 電話番号
            - family_count: 世帯人数
            - vulnerabilities: 要配慮者情報（辞書）
            - medical: 医療・健康情報
            - allergy: アレルギー情報
            - care_needed: 要介護かどうか
            - evacuation_type: 避難場所
            - agree_info: 第三者提供への同意
            - agree_board: 掲示板掲示への同意
    
    Returns:
        書き込み結果
    """
    idm = resident.get("idm")
    if not idm:
        raise HTTPException(status_code=400, detail="IDm is required")
    
    try:
        logger.info(f"NFCカードへの書き込みを開始: ID={idm}")
        write_success = write_reception_data(idm, resident, max_retries=3)
        
        if write_success:
            logger.info(f"NFCカードへの書き込みが完了しました: ID={idm}")
            return {
                "success": True,
                "message": "NFCカードへの書き込みが完了しました",
                "idm": idm
            }
        else:
            logger.error(f"NFCカードへの書き込みに失敗しました: ID={idm}")
            raise HTTPException(status_code=500, detail="NFCカードへの書き込みに失敗しました。カードがリーダーにタッチされているか確認してください。")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"NFCカードへの書き込み中にエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail=f"書き込みエラー: {str(e)}")

@app.get("/api/read-card/{idm}", response_model=Dict[str, Any])
def read_card_only(idm: str) -> Dict[str, Any]:
    """
    NFCカードから直接受付データを読み取る（データベースは参照しない）
    
    Args:
        idm: NFCカードのIDm
    
    Returns:
        受付情報（辞書形式）
    
    Raises:
        HTTPException: カードからデータが読み取れない場合（404エラー）
    """
    def normalize_reception_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        受付テンプレートに沿ったキーを揃え、未設定項目はNoneで統一する。
        フロント側で「未設定」表示に変換するための下準備。
        """
        normalized: Dict[str, Any] = {
            "idm": None,
            "name": None,
            "kana": None,
            "address": None,
            "tel": None,
            "family_count": None,
            "vulnerabilities": None,
            "medical": None,
            "allergy": None,
            "care_needed": None,
            "evacuation_type": None,
            "agree_info": None,
            "agree_board": None,
            "registered_at": None
        }
        normalized.update({k: data.get(k) for k in normalized.keys()})
        if not isinstance(normalized.get("vulnerabilities"), dict):
            normalized["vulnerabilities"] = None
        return normalized

    try:
        logger.info(f"NFCカードからの読み取りを開始: ID={idm}")
        reception_data = read_reception_data(idm)
        
        if not reception_data:
            logger.warning(f"カードから受付データが読み取れませんでした: ID={idm}")
            raise HTTPException(status_code=404, detail="カードから受付データが読み取れませんでした。カードがリーダーにタッチされているか、データが書き込まれているか確認してください。")
        
        # 読み取ったデータにidmを追加し、テンプレートに合わせて正規化
        reception_data["idm"] = idm
        reception_data = normalize_reception_data(reception_data)
        logger.info(f"NFCカードからの読み取りが完了しました: ID={idm}")
        return reception_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"NFCカードからの読み取り中にエラーが発生しました: {e}")
        raise HTTPException(status_code=500, detail=f"読み取りエラー: {str(e)}")

@app.post("/api/checkin", response_model=Dict[str, Any])
def create_resident(
    resident: Dict[str, Any],
) -> Dict[str, Any]:
    """
    避難者情報をカードに書き込む（DBには保存しない）
    
    Args:
        resident: 避難者情報の辞書
            - idm: NFCカードのIDm（必須）
            - name: 氏名
            - kana: フリガナ
            - address: 住所
            - tel: 電話番号
            - family_count: 世帯人数
            - vulnerabilities: 要配慮者情報（辞書）
            - medical: 医療・健康情報
            - allergy: アレルギー情報
            - care_needed: 要介護かどうか
            - evacuation_type: 避難場所
            - agree_info: 第三者提供への同意
            - agree_board: 掲示板掲示への同意
    Returns:
        書き込み結果
    
    Raises:
        HTTPException: データベースエラーが発生した場合（400エラー）
    """
    # ログ出力
    print_rich_log(resident)
    
    idm = resident.get("idm")
    if not idm:
        raise HTTPException(status_code=400, detail="IDm is required")
    
    # カード書き込みのみ実行（DBは使用しない）
    try:
        logger.info(f"NFCカードへの書き込みを開始: ID={idm}")
        write_success = write_reception_data(idm, resident, max_retries=3)
        if write_success:
            logger.info(f"NFCカードへの書き込みが完了しました: ID={idm}")
            return {
                "success": True,
                "message": "NFCカードへの書き込みが完了しました",
                "idm": idm
            }
        logger.warning(f"NFCカードへの書き込みに失敗しました: ID={idm}")
        raise HTTPException(status_code=500, detail="NFCカードへの書き込みに失敗しました。")
    except Exception as e:
        logger.error(f"Error creating resident: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/residents", response_model=List[Dict[str, Any]])
def read_residents(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    登録済みの避難者一覧を取得する
    
    Args:
        skip: スキップするレコード数（ページネーション用、デフォルト: 0）
        limit: 取得する最大レコード数（デフォルト: 100）
        db: データベースセッション（依存性注入）
    
    Returns:
        避難者情報のリスト（辞書形式）
    """
    residents = db.query(Resident).offset(skip).limit(limit).all()
    logger.info(f"避難者一覧を取得しました: {len(residents)}件")
    
    # Residentオブジェクトを辞書に変換
    return [
        {
            "id": r.id,
            "idm": r.idm,
            "name": r.name,
            "kana": r.kana,
            "address": r.address,
            "tel": r.tel,
            "family_count": r.family_count,
            "vulnerabilities": r.vulnerabilities,
            "medical": r.medical,
            "allergy": r.allergy,
            "care_needed": r.care_needed,
            "evacuation_type": r.evacuation_type,
            "agree_info": r.agree_info,
            "agree_board": r.agree_board,
            "registered_at": r.registered_at
        }
        for r in residents
    ]

@app.get("/api/residents/{idm}", response_model=Dict[str, Any])
def read_resident(idm: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    IDmで避難者情報を取得する
    
    Args:
        idm: NFCカードのIDm
        db: データベースセッション（依存性注入）
    
    Returns:
        避難者情報（辞書形式）
    
    Raises:
        HTTPException: 避難者情報が見つからない場合（404エラー）
    """
    resident = db.query(Resident).filter(Resident.idm == idm).first()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")
    
    # Residentオブジェクトを辞書に変換
    return {
        "id": resident.id,
        "idm": resident.idm,
        "name": resident.name,
        "kana": resident.kana,
        "address": resident.address,
        "tel": resident.tel,
        "family_count": resident.family_count,
        "vulnerabilities": resident.vulnerabilities,
        "medical": resident.medical,
        "allergy": resident.allergy,
        "care_needed": resident.care_needed,
        "evacuation_type": resident.evacuation_type,
        "agree_info": resident.agree_info,
        "agree_board": resident.agree_board,
        "registered_at": resident.registered_at
    }

@app.get("/api/admin/current-booth")
async def get_current_booth() -> Dict[str, Any]:
    """
    現在選択されている試練IDを取得する（管理者用）
    
    Returns:
        現在選択されている試練ID
    """
    global current_selected_booth_id
    return {
        "booth_id": current_selected_booth_id,
        "has_selection": current_selected_booth_id is not None
    }

@app.get("/api/debug/card-content/{idm}")
async def get_card_content(idm: str) -> Dict[str, Any]:
    """
    デバッグ用: NFCカードの内容を読み取って表示する
    
    Args:
        idm: NFCカードのIDm
    
    Returns:
        カードの内容（ページごとのデータ）
    """
    from smartcard.System import readers
    
    try:
        reader_list = readers()
        if not reader_list:
            raise HTTPException(status_code=404, detail="NFCリーダーが見つかりません")
        
        reader = reader_list[0]
        connection = reader.createConnection()
        connection.connect()
        
        card_type = detect_card_type(connection)
        
        if card_type == "mifare_ultralight":
            # NTAG215/NTAG213の場合
            # 主要な領域を読み取る
            pages = {}
            
            # システム領域（ページ0-3）
            system_pages = read_card_pages_ntag213(connection, 0, 3)
            if system_pages:
                pages["system"] = system_pages
            
            # クイズ進捗領域（ページ0x14）
            quiz_pages = read_card_pages_ntag213(connection, 0x14, 0x14)
            if quiz_pages:
                pages["quiz"] = quiz_pages
            
            # 受付ヘッダー領域（ページ0x15）
            reception_header_pages = read_card_pages_ntag213(connection, 0x15, 0x15)
            if reception_header_pages:
                pages["reception_header"] = reception_header_pages
            
            # 受付データ領域（ページ0x16-0x27）
            reception_data_pages = read_card_pages_ntag213(connection, 0x16, 0x27)
            if reception_data_pages:
                pages["reception_data"] = reception_data_pages
            
            return {
                "card_type": card_type,
                "idm": idm,
                "pages": pages,
                "regions": {
                    "system": {
                        "pages": "0x00-0x03",
                        "description": "システム領域（UID、設定など）"
                    },
                    "quiz": {
                        "pages": "0x14",
                        "description": "クイズ進捗（クリア数）"
                    },
                    "reception_header": {
                        "pages": "0x15",
                        "description": "受付ヘッダー（受付フラグ、クリア可否フラグ）"
                    },
                    "reception_data": {
                        "pages": "0x16-0x27",
                        "description": "受付データ（氏名、住所、電話番号など、48バイト）"
                    }
                }
            }
        else:
            return {
                "card_type": card_type,
                "idm": idm,
                "message": f"カードタイプ {card_type} のデバッグ表示は未実装です"
            }
    except Exception as e:
        logger.error(f"Error reading card content: {e}")
        raise HTTPException(status_code=500, detail=f"カード内容の読み取りに失敗しました: {str(e)}")

@app.get("/api/system/nfc-status")
async def get_nfc_status() -> Dict[str, Any]:
    """
    NFCリーダーの状態を取得する
    
    Returns:
        NFCリーダーの状態情報
    """
    try:
        from smartcard.System import readers
        
        reader_list = readers()
        reader_count = len(reader_list) if reader_list else 0
        
        return {
            "nfc_reader_available": reader_count > 0,
            "reader_count": reader_count,
            "readers": [str(r) for r in reader_list] if reader_list else [],
            "is_running": nfc_reader.is_running,
            "current_card_idm": nfc_reader.current_card_idm
        }
    except Exception as e:
        logger.error(f"Error checking NFC status: {e}")
        return {
            "nfc_reader_available": False,
            "reader_count": 0,
            "readers": [],
            "is_running": False,
            "error": str(e)
        }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket接続エンドポイント
    
    クライアントとのリアルタイム通信を提供します。
    NFCカード検知などのイベントをブロードキャストします。
    
    Args:
        websocket: WebSocket接続
    """
    await manager.connect(websocket)
    logger.info("WebSocket接続が確立されました")
    
    # 接続時に現在選択されている試練IDを送信
    global current_selected_booth_id
    if current_selected_booth_id is not None:
        await websocket.send_text(json.dumps({
            "type": "booth_selected",
            "booth_id": current_selected_booth_id
        }))
    
    try:
        while True:
            # クライアントからのメッセージを受信
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                
                # 管理者からの試練選択メッセージを処理
                if message.get("type") == "booth_selected":
                    booth_id = message.get("booth_id")
                    if booth_id and 1 <= booth_id <= 5:
                        current_selected_booth_id = booth_id
                        logger.info(f"管理者が試練{booth_id}を選択しました")
                        # 全クライアントにブロードキャスト
                        broadcast_message = json.dumps({
                            "type": "booth_selected",
                            "booth_id": booth_id
                        })
                        await manager.broadcast(broadcast_message)
                    elif booth_id is None:
                        # 選択解除
                        current_selected_booth_id = None
                        logger.info("管理者が試練の選択を解除しました")
                        broadcast_message = json.dumps({
                            "type": "booth_unselected"
                        })
                        await manager.broadcast(broadcast_message)
                        
            except json.JSONDecodeError:
                # JSON解析エラーは無視（ping/pongなど）
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket接続が切断されました")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
