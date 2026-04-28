"""
NFC書き込み機能 - クイズ進捗の記録

NFCカードの物理メモリにクリアした試練の数を記録します。
システム領域は一切変更せず、ユーザーデータ領域のみを使用します。
"""
import logging
import time
from typing import Optional, Dict, Any, List
from smartcard.util import toHexString, toBytes
from smartcard.CardConnection import CardConnection

logger = logging.getLogger("uvicorn")


def _select_preferred_reader(reader_list: List[object]) -> Optional[object]:
    """
    複数のNFCリーダーがある場合に、SONY(PaSoRi)系を優先して選択する。

    Args:
        reader_list: smartcard.System.readers() の戻り値

    Returns:
        優先リーダー（存在しない場合はNone）
    """
    if not reader_list:
        return None

    def score(reader: object) -> tuple:
        s = str(reader).lower()
        # SONY / FeliCa / PaSoRi を優先
        preferred = ("sony" in s) or ("felica" in s) or ("pasori" in s)
        return (0 if preferred else 1, s)

    return sorted(reader_list, key=score)[0]

# クイズシステム専用の領域定義
QUIZ_SERVICE_CODE = 0x120B  # FeliCa用
QUIZ_BLOCK_NUMBER = 0  # FeliCa用ブロック番号
QUIZ_SECTOR = 14  # Mifare Classic用セクター
QUIZ_BLOCK = 56  # Mifare Classic用ブロック（セクター14のデータブロック）
QUIZ_PAGE = 0x14  # Mifare Ultralight用ページ

# 受付情報用の領域定義
RECEPTION_SECTOR = 14  # Mifare Classic用セクター
RECEPTION_BLOCK_HEADER = 57  # ヘッダー + フラグ
RECEPTION_BLOCK_DATA_START = 58  # データ開始ブロック
RECEPTION_BLOCK_DATA_END = 60  # データ終了ブロック

# FeliCa用
RECEPTION_SERVICE_CODE = 0x120C
RECEPTION_BLOCK_HEADER_NUM = 1
RECEPTION_BLOCK_DATA_START_NUM = 2
RECEPTION_BLOCK_DATA_END_NUM = 4

# NTAG213/NTAG215（Mifare Ultralight）用
RECEPTION_PAGE_HEADER = 0x15  # ヘッダー + フラグ（4バイト）
RECEPTION_PAGE_DATA_START = 0x16  # データ開始ページ
RECEPTION_PAGE_DATA_END = 0x27  # データ終了ページ（12ページ = 48バイト）
# NTAG215は504バイト（126ページ）の容量があるが、受付データは48バイト（12ページ）で十分


def detect_card_type(card_connection: CardConnection) -> Optional[str]:
    """
    カードタイプを検出する
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        カードタイプ（"felica", "mifare_classic", "mifare_ultralight", None）
    """
    try:
        atr = card_connection.getATR()
        atr_hex = toHexString(atr)
        atr_hex_compact = atr_hex.replace(" ", "").upper()
        
        # ATRからカードタイプを判定
        # NTAG215/NTAG213などのMifare Ultralight系カード
        # ATRパターン: 3B 88 01 00 00 00 00 00 00 00 00 など
        if "3B88010000000000000000" in atr_hex_compact or \
           atr_hex_compact.startswith("3B8801"):
            return "mifare_ultralight"
        # Mifare Ultralight / NTAG21xのATRパターン
        elif "3B8F8001804F0CA000000306030001000000006A" in atr_hex_compact or \
             "3B8F8001804F0CA0000003060300030000000068" in atr_hex_compact or \
             atr_hex_compact.startswith("3B8F8001804F0CA00000030603"):
            return "mifare_ultralight"
        # Mifare Classic
        elif "3B88800100000000000000" in atr_hex_compact:
            return "mifare_classic"
        else:
            # ATRが不明な場合、IDmの長さで判定を試みる
            # NTAG215/NTAG213は7バイトのUIDを持つことが多い
            logger.warning(f"Unknown card type, ATR: {atr_hex}")
            # デフォルトでmifare_ultralightとして扱う（NTAG215/NTAG213の可能性が高い）
            logger.info("Assuming Mifare Ultralight (NTAG215/NTAG213) based on unknown ATR")
            return "mifare_ultralight"
    except Exception as e:
        logger.error(f"Error detecting card type: {e}")
        return None


def _read_ntag_page(card_connection: CardConnection, page: int) -> Optional[List[int]]:
    """
    NTAG213/NTAG215の1ページ(4バイト)を読み取る。
    一部のリーダーではLe=0x04で失敗し、0x10が必要なためフォールバックする。
    """
    # まず4バイト読み取りを試す
    read_apdu = [0xFF, 0xB0, 0x00, page, 0x04]
    response, sw1, sw2 = card_connection.transmit(read_apdu)
    if sw1 == 0x90 and sw2 == 0x00 and len(response) >= 4:
        return list(response[:4])
    # 0x6Cは正しいLeを示す（例: 0x10）
    if sw1 == 0x6C:
        retry_len = sw2
        retry_apdu = [0xFF, 0xB0, 0x00, page, retry_len]
        response, sw1, sw2 = card_connection.transmit(retry_apdu)
        if sw1 == 0x90 and sw2 == 0x00 and len(response) >= 4:
            return list(response[:4])
    logger.warning(f"Failed to read NTAG page {hex(page)}, SW: {hex(sw1)} {hex(sw2)}")
    return None


def read_cleared_count_felica(card_connection: CardConnection) -> int:
    """
    FeliCaカードからクリア数を読み取る
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        クリア数（0-5）、読み取り失敗時は0
    """
    try:
        # PollingコマンドでIDmを取得
        polling_apdu = [0xFF, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00]
        response, sw1, sw2 = card_connection.transmit(polling_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning("Failed to poll FeliCa card")
            return 0
        
        # Read Without Encryptionコマンド
        # サービスコード0x120B、ブロック0を読み取り
        read_apdu = [
            0xFF, 0xB0, 0x00, QUIZ_BLOCK_NUMBER, 0x10  # Read Binary
        ]
        response, sw1, sw2 = card_connection.transmit(read_apdu)
        
        if sw1 == 0x90 and sw2 == 0x00 and len(response) > 0:
            cleared_count = response[0] & 0x0F  # 下位4ビットのみ使用（0-5）
            if cleared_count > 5:
                cleared_count = 0
            return cleared_count
        else:
            logger.warning(f"Failed to read FeliCa card, SW: {hex(sw1)} {hex(sw2)}")
            return 0
    except Exception as e:
        logger.error(f"Error reading FeliCa card: {e}")
        return 0


def write_cleared_count_felica(card_connection: CardConnection, count: int) -> bool:
    """
    FeliCaカードにクリア数を書き込む
    
    Args:
        card_connection: カード接続オブジェクト
        count: クリア数（0-5）
    
    Returns:
        書き込み成功時True、失敗時False
    """
    try:
        if count < 0 or count > 5:
            logger.error(f"Invalid cleared count: {count}")
            return False
        
        # 書き込みデータ（1バイト目にクリア数、残りは0で埋める）
        write_data = [count] + [0] * 15
        
        # Write Binaryコマンド
        write_apdu = [0xFF, 0xD6, 0x00, QUIZ_BLOCK_NUMBER, 0x10] + write_data
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        
        if sw1 == 0x90 and sw2 == 0x00:
            logger.info(f"Successfully wrote cleared count {count} to FeliCa card")
            return True
        else:
            logger.warning(f"Failed to write FeliCa card, SW: {hex(sw1)} {hex(sw2)}")
            return False
    except Exception as e:
        logger.error(f"Error writing FeliCa card: {e}")
        return False


def read_cleared_count_mifare_classic(card_connection: CardConnection) -> int:
    """
    Mifare Classicカードからクリア数を読み取る
    
    システム領域（セクター0、Trailer Block）は一切読み書きしません。
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        クリア数（0-5）、読み取り失敗時は0
    """
    try:
        # セクター14のブロック56を読み取り（Trailer Blockは読み取らない）
        # Load Keysコマンド（デフォルトキーA: FF FF FF FF FF FFを使用）
        load_key_apdu = [0xFF, 0x82, 0x00, 0x00, 0x06, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
        response, sw1, sw2 = card_connection.transmit(load_key_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning("Failed to load key for Mifare Classic")
            return 0
        
        # Authenticateコマンド（セクター14、キーAを使用）
        # 0x60 = キーAを使用、0x00 = キースロット0
        auth_apdu = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, QUIZ_SECTOR, 0x60, 0x00]
        response, sw1, sw2 = card_connection.transmit(auth_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to authenticate Mifare Classic sector {QUIZ_SECTOR}, SW: {hex(sw1)} {hex(sw2)}")
            return 0
        
        # Read Binaryコマンド（ブロック56）
        read_apdu = [0xFF, 0xB0, 0x00, QUIZ_BLOCK, 0x10]
        response, sw1, sw2 = card_connection.transmit(read_apdu)
        
        if sw1 == 0x90 and sw2 == 0x00 and len(response) > 0:
            cleared_count = response[0] & 0x0F  # 下位4ビットのみ使用（0-5）
            if cleared_count > 5:
                cleared_count = 0
            return cleared_count
        else:
            logger.warning(f"Failed to read Mifare Classic block {QUIZ_BLOCK}, SW: {hex(sw1)} {hex(sw2)}")
            return 0
    except Exception as e:
        logger.error(f"Error reading Mifare Classic card: {e}")
        return 0


def write_cleared_count_mifare_classic(card_connection: CardConnection, count: int) -> bool:
    """
    Mifare Classicカードにクリア数を書き込む
    
    システム領域（セクター0、Trailer Block）は一切書き込みません。
    
    Args:
        card_connection: カード接続オブジェクト
        count: クリア数（0-5）
    
    Returns:
        書き込み成功時True、失敗時False
    """
    try:
        if count < 0 or count > 5:
            logger.error(f"Invalid cleared count: {count}")
            return False
        
        # Load Keysコマンド（デフォルトキーA: FF FF FF FF FF FFを使用）
        load_key_apdu = [0xFF, 0x82, 0x00, 0x00, 0x06, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
        response, sw1, sw2 = card_connection.transmit(load_key_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning("Failed to load key for Mifare Classic")
            return False
        
        # Authenticateコマンド（セクター14、キーAを使用）
        auth_apdu = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, QUIZ_SECTOR, 0x60, 0x00]
        response, sw1, sw2 = card_connection.transmit(auth_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to authenticate Mifare Classic sector {QUIZ_SECTOR}, SW: {hex(sw1)} {hex(sw2)}")
            return False
        
        # 書き込みデータ（1バイト目にクリア数、残りは0で埋める）
        write_data = [count] + [0] * 15
        
        # Update Binaryコマンド（ブロック56）
        write_apdu = [0xFF, 0xD6, 0x00, QUIZ_BLOCK, 0x10] + write_data
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        
        if sw1 == 0x90 and sw2 == 0x00:
            logger.info(f"Successfully wrote cleared count {count} to Mifare Classic card")
            return True
        else:
            logger.warning(f"Failed to write Mifare Classic block {QUIZ_BLOCK}, SW: {hex(sw1)} {hex(sw2)}")
            return False
    except Exception as e:
        logger.error(f"Error writing Mifare Classic card: {e}")
        return False


def read_cleared_count_mifare_ultralight(card_connection: CardConnection) -> int:
    """
    Mifare Ultralightカードからクリア数を読み取る
    
    システム領域（ページ0-3）は一切読み書きしません。
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        クリア数（0-5）、読み取り失敗時は0
    """
    try:
        page_data = _read_ntag_page(card_connection, QUIZ_PAGE)
        if page_data:
            cleared_count = page_data[0] & 0x0F  # 下位4ビットのみ使用（0-5）
            if cleared_count > 5:
                cleared_count = 0
            return cleared_count
        return 0
    except Exception as e:
        logger.error(f"Error reading Mifare Ultralight card: {e}")
        return 0


def write_cleared_count_mifare_ultralight(card_connection: CardConnection, count: int) -> bool:
    """
    Mifare Ultralightカードにクリア数を書き込む
    
    システム領域（ページ0-3）は一切書き込みません。
    
    Args:
        card_connection: カード接続オブジェクト
        count: クリア数（0-5）
    
    Returns:
        書き込み成功時True、失敗時False
    """
    try:
        if count < 0 or count > 5:
            logger.error(f"Invalid cleared count: {count}")
            return False
        
        # 書き込みデータ（1バイト目にクリア数、残りは0で埋める）
        write_data = [count] + [0] * 3
        
        # Update Binaryコマンド（ページ0x14）
        write_apdu = [0xFF, 0xD6, 0x00, QUIZ_PAGE, 0x04] + write_data
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        
        if sw1 == 0x90 and sw2 == 0x00:
            logger.info(f"Successfully wrote cleared count {count} to Mifare Ultralight card")
            return True
        else:
            logger.warning(f"Failed to write Mifare Ultralight page {hex(QUIZ_PAGE)}, SW: {hex(sw1)} {hex(sw2)}")
            return False
    except Exception as e:
        logger.error(f"Error writing Mifare Ultralight card: {e}")
        return False


def read_cleared_count(idm: str) -> int:
    """
    NFCカードからクリア数を読み取る
    
    Args:
        idm: NFCカードのIDm（UID）
    
    Returns:
        クリア数（0-5）、読み取り失敗時は0
    """
    from smartcard.System import readers
    from smartcard.CardConnection import CardConnection
    
    try:
        reader_list = readers()
        if not reader_list:
            logger.warning("No NFC readers found")
            return 0
        
        # リーダーを選択（複数ある場合はSONY(PaSoRi)を優先）
        reader = _select_preferred_reader(reader_list)
        if reader is None:
            logger.warning("No NFC readers found")
            return 0
        connection = reader.createConnection()
        connection.connect()
        
        # カードタイプを検出
        card_type = detect_card_type(connection)
        
        if card_type == "felica":
            return read_cleared_count_felica(connection)
        elif card_type == "mifare_classic":
            return read_cleared_count_mifare_classic(connection)
        elif card_type == "mifare_ultralight":
            return read_cleared_count_mifare_ultralight(connection)
        else:
            logger.warning(f"Unsupported card type: {card_type}")
            return 0
    except Exception as e:
        logger.error(f"Error reading cleared count: {e}")
        return 0


def write_cleared_count(idm: str, count: int, max_retries: int = 3) -> bool:
    """
    NFCカードにクリア数を書き込む
    
    システム領域は一切書き込みません。リトライ機能付き。
    
    Args:
        idm: NFCカードのIDm（UID）
        count: クリア数（0-5）
        max_retries: 最大リトライ回数
    
    Returns:
        書き込み成功時True、失敗時False
    """
    from smartcard.System import readers
    from smartcard.CardConnection import CardConnection
    
    if count < 0 or count > 5:
        logger.error(f"Invalid cleared count: {count}")
        return False
    
    for attempt in range(max_retries):
        try:
            reader_list = readers()
            if not reader_list:
                logger.warning("No NFC readers found")
                if attempt < max_retries - 1:
                    time.sleep(0.2)
                    continue
                return False
            
            # リーダーを選択（複数ある場合はSONY(PaSoRi)を優先）
            reader = _select_preferred_reader(reader_list)
            if reader is None:
                logger.warning("No NFC readers found")
                if attempt < max_retries - 1:
                    time.sleep(0.2)
                    continue
                return False
            connection = reader.createConnection()
            connection.connect()
            
            # カードタイプを検出
            card_type = detect_card_type(connection)
            
            success = False
            if card_type == "felica":
                success = write_cleared_count_felica(connection, count)
            elif card_type == "mifare_classic":
                success = write_cleared_count_mifare_classic(connection, count)
            elif card_type == "mifare_ultralight":
                success = write_cleared_count_mifare_ultralight(connection, count)
            else:
                logger.warning(f"Unsupported card type: {card_type}")
                return False
            
            if success:
                return True
            elif attempt < max_retries - 1:
                logger.info(f"Write attempt {attempt + 1} failed, retrying...")
        except Exception as e:
            logger.error(f"Error writing cleared count (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                continue
    
    logger.error(f"Failed to write cleared count after {max_retries} attempts")
    return False


# ============================================================================
# 受付情報書き込み機能
# ============================================================================

def write_reception_header_felica(card_connection: CardConnection, reception_flag: int, clearance_flags: int) -> bool:
    """
    FeliCaカードに受付情報ヘッダーとクリア可否フラグを書き込む
    
    Args:
        card_connection: カード接続オブジェクト
        reception_flag: 受付済みフラグ（0x00=未受付、0x01=受付済み）
        clearance_flags: クリア可否フラグ（5bit、bit0-4が試練1-5に対応）
    
    Returns:
        書き込み成功時True、失敗時False
    """
    try:
        # ヘッダー（受付フラグ + クリア可否フラグ + 予約領域）
        write_data = [reception_flag, clearance_flags, 0x00, 0x00] + [0] * 12
        write_apdu = [0xFF, 0xD6, 0x00, RECEPTION_BLOCK_HEADER_NUM, 0x10] + write_data
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        
        if sw1 == 0x90 and sw2 == 0x00:
            logger.info(f"Successfully wrote reception header to FeliCa")
            return True
        else:
            logger.warning(f"Failed to write FeliCa block {RECEPTION_BLOCK_HEADER_NUM}, SW: {hex(sw1)} {hex(sw2)}")
            return False
    except Exception as e:
        logger.error(f"Error writing reception header to FeliCa: {e}")
        return False


def read_reception_header_felica(card_connection: CardConnection) -> Optional[tuple]:
    """
    FeliCaカードから受付情報ヘッダーとクリア可否フラグを読み取る
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        (受付済みフラグ, クリア可否フラグ)のタプル、失敗時None
    """
    try:
        read_apdu = [0xFF, 0xB0, 0x00, RECEPTION_BLOCK_HEADER_NUM, 0x10]
        response, sw1, sw2 = card_connection.transmit(read_apdu)
        
        if sw1 == 0x90 and sw2 == 0x00 and len(response) >= 4:
            reception_flag = response[0]
            clearance_flags = response[1]
            return (reception_flag, clearance_flags)
        else:
            logger.warning(f"Failed to read FeliCa block {RECEPTION_BLOCK_HEADER_NUM}, SW: {hex(sw1)} {hex(sw2)}")
            return None
    except Exception as e:
        logger.error(f"Error reading reception header from FeliCa: {e}")
        return None


def write_reception_data_felica(card_connection: CardConnection, data: bytes) -> bool:
    """
    FeliCaカードに受付情報データを書き込む
    
    Args:
        card_connection: カード接続オブジェクト
        data: 書き込むデータ（56バイト、実際には48バイトまで使用）
    
    Returns:
        書き込み成功時True、失敗時False
    """
    try:
        # 48バイト以上あることを確認
        if len(data) < 48:
            logger.error(f"Invalid data length: {len(data)}, expected at least 48 bytes")
            return False
        
        # 実際に書き込むのは48バイト（3ブロック = 48バイト）
        write_data = data[:48] if len(data) > 48 else data
        
        # ブロック2-4に書き込み（3ブロック = 48バイト）
        for i in range(3):
            block = RECEPTION_BLOCK_DATA_START_NUM + i
            block_data = list(write_data[i*16:(i+1)*16])
            # 16バイトに満たない場合は0で埋める
            while len(block_data) < 16:
                block_data.append(0)
            
            write_apdu = [0xFF, 0xD6, 0x00, block, 0x10] + block_data
            response, sw1, sw2 = card_connection.transmit(write_apdu)
            
            if sw1 != 0x90 or sw2 != 0x00:
                logger.warning(f"Failed to write FeliCa block {block}, SW: {hex(sw1)} {hex(sw2)}")
                return False
        
        logger.info("Successfully wrote reception data to FeliCa")
        return True
    except Exception as e:
        logger.error(f"Error writing reception data to FeliCa: {e}")
        return False


def read_reception_data_felica(card_connection: CardConnection) -> Optional[bytes]:
    """
    FeliCaカードから受付情報データを読み取る
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        読み取ったデータ（48バイト）、失敗時None
    """
    try:
        data = bytearray()
        
        # ブロック2-4を読み取り（3ブロック = 48バイト）
        for i in range(3):
            block = RECEPTION_BLOCK_DATA_START_NUM + i
            read_apdu = [0xFF, 0xB0, 0x00, block, 0x10]
            response, sw1, sw2 = card_connection.transmit(read_apdu)
            
            if sw1 == 0x90 and sw2 == 0x00 and len(response) >= 16:
                data.extend(response[:16])
            else:
                logger.warning(f"Failed to read FeliCa block {block}, SW: {hex(sw1)} {hex(sw2)}")
                return None
        
        return bytes(data[:48])
    except Exception as e:
        logger.error(f"Error reading reception data from FeliCa: {e}")
        return None


def write_reception_header_ntag213(card_connection: CardConnection, reception_flag: int, clearance_flags: int) -> bool:
    """
    NTAG213に受付情報ヘッダーとクリア可否フラグを書き込む
    
    Args:
        card_connection: カード接続オブジェクト
        reception_flag: 受付済みフラグ（0x00=未受付、0x01=受付済み）
        clearance_flags: クリア可否フラグ（5bit、bit0-4が試練1-5に対応）
    
    Returns:
        書き込み成功時True、失敗時False
    """
    try:
        # ページ0x15に書き込み（4バイト）
        write_data = [reception_flag, clearance_flags, 0x00, 0x00]
        write_apdu = [0xFF, 0xD6, 0x00, RECEPTION_PAGE_HEADER, 0x04] + write_data
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        
        if sw1 == 0x90 and sw2 == 0x00:
            logger.info(f"Successfully wrote reception header to NTAG213")
            return True
        else:
            logger.warning(f"Failed to write NTAG213 page {hex(RECEPTION_PAGE_HEADER)}, SW: {hex(sw1)} {hex(sw2)}")
            return False
    except Exception as e:
        logger.error(f"Error writing reception header to NTAG213: {e}")
        return False


def read_reception_header_ntag213(card_connection: CardConnection) -> Optional[tuple]:
    """
    NTAG213から受付情報ヘッダーとクリア可否フラグを読み取る
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        (受付済みフラグ, クリア可否フラグ)のタプル、失敗時None
    """
    try:
        page_data = _read_ntag_page(card_connection, RECEPTION_PAGE_HEADER)
        if page_data and len(page_data) >= 2:
            reception_flag = page_data[0]
            clearance_flags = page_data[1]
            return (reception_flag, clearance_flags)
        return None
    except Exception as e:
        logger.error(f"Error reading reception header from NTAG213: {e}")
        return None


def write_reception_data_ntag213(card_connection: CardConnection, data: bytes) -> bool:
    """
    NTAG213に受付情報データを書き込む
    
    Args:
        card_connection: カード接続オブジェクト
        data: 書き込むデータ（48バイト）
    
    Returns:
        書き込み成功時True、失敗時False
    """
    try:
        # 48バイト以上あることを確認（実際には56バイトまで対応）
        if len(data) < 48:
            logger.error(f"Invalid data length: {len(data)}, expected at least 48 bytes")
            return False
        
        # 実際に書き込むのは48バイト（12ページ）
        write_data = data[:48] if len(data) > 48 else data
        
        # ページ0x16-0x27に書き込み（12ページ = 48バイト）
        for i in range(12):
            page = RECEPTION_PAGE_DATA_START + i
            page_data = list(write_data[i*4:(i+1)*4])
            # 4バイトに満たない場合は0で埋める
            while len(page_data) < 4:
                page_data.append(0)
            
            write_apdu = [0xFF, 0xD6, 0x00, page, 0x04] + page_data
            response, sw1, sw2 = card_connection.transmit(write_apdu)
            
            if sw1 != 0x90 or sw2 != 0x00:
                logger.warning(f"Failed to write NTAG213 page {hex(page)}, SW: {hex(sw1)} {hex(sw2)}")
                return False
        
        logger.info("Successfully wrote reception data to NTAG213")
        return True
    except Exception as e:
        logger.error(f"Error writing reception data to NTAG213: {e}")
        return False


def read_card_pages_ntag213(card_connection: CardConnection, start_page: int, end_page: int) -> Optional[Dict[int, List[int]]]:
    """
    NTAG213/NTAG215から指定範囲のページを読み取る（デバッグ用）
    
    Args:
        card_connection: カード接続オブジェクト
        start_page: 開始ページ番号
        end_page: 終了ページ番号（含む）
    
    Returns:
        ページ番号をキー、4バイトのデータリストを値とする辞書、失敗時None
    """
    try:
        result = {}
        for page in range(start_page, end_page + 1):
            page_data = _read_ntag_page(card_connection, page)
            result[page] = page_data
        
        return result
    except Exception as e:
        logger.error(f"Error reading card pages: {e}")
        return None


def read_reception_data_ntag213(card_connection: CardConnection) -> Optional[bytes]:
    """
    NTAG213から受付情報データを読み取る
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        読み取ったデータ（48バイト）、失敗時None
    """
    try:
        data = bytearray()
        # ページ0x16-0x27を読み取り（12ページ = 48バイト）
        for i in range(12):
            page = RECEPTION_PAGE_DATA_START + i
            page_data = _read_ntag_page(card_connection, page)
            if page_data:
                data.extend(page_data[:4])
            else:
                return None
        
        return bytes(data)
    except Exception as e:
        logger.error(f"Error reading reception data from NTAG213: {e}")
        return None


def write_reception_header_mifare_classic(card_connection: CardConnection, reception_flag: int, clearance_flags: int) -> bool:
    """
    Mifare Classicに受付情報ヘッダーとクリア可否フラグを書き込む
    
    Args:
        card_connection: カード接続オブジェクト
        reception_flag: 受付済みフラグ（0x00=未受付、0x01=受付済み）
        clearance_flags: クリア可否フラグ（5bit、bit0-4が試練1-5に対応）
    
    Returns:
        書き込み成功時True、失敗時False
    """
    try:
        # Load Keysコマンド
        load_key_apdu = [0xFF, 0x82, 0x00, 0x00, 0x06, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
        response, sw1, sw2 = card_connection.transmit(load_key_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning("Failed to load key for Mifare Classic")
            return False
        
        # Authenticateコマンド（セクター14）
        auth_apdu = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, RECEPTION_SECTOR, 0x60, 0x00]
        response, sw1, sw2 = card_connection.transmit(auth_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to authenticate Mifare Classic sector {RECEPTION_SECTOR}")
            return False
        
        # 書き込みデータ（ブロック57）
        write_data = [reception_flag, clearance_flags] + [0] * 14
        write_apdu = [0xFF, 0xD6, 0x00, RECEPTION_BLOCK_HEADER, 0x10] + write_data
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        
        if sw1 == 0x90 and sw2 == 0x00:
            logger.info("Successfully wrote reception header to Mifare Classic")
            return True
        else:
            logger.warning(f"Failed to write Mifare Classic block {RECEPTION_BLOCK_HEADER}, SW: {hex(sw1)} {hex(sw2)}")
            return False
    except Exception as e:
        logger.error(f"Error writing reception header to Mifare Classic: {e}")
        return False


def read_reception_header_mifare_classic(card_connection: CardConnection) -> Optional[tuple]:
    """
    Mifare Classicから受付情報ヘッダーとクリア可否フラグを読み取る
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        (受付済みフラグ, クリア可否フラグ)のタプル、失敗時None
    """
    try:
        # Load Keysコマンド
        load_key_apdu = [0xFF, 0x82, 0x00, 0x00, 0x06, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
        response, sw1, sw2 = card_connection.transmit(load_key_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning("Failed to load key for Mifare Classic")
            return None
        
        # Authenticateコマンド（セクター14）
        auth_apdu = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, RECEPTION_SECTOR, 0x60, 0x00]
        response, sw1, sw2 = card_connection.transmit(auth_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to authenticate Mifare Classic sector {RECEPTION_SECTOR}")
            return None
        
        # ブロック57を読み取り
        read_apdu = [0xFF, 0xB0, 0x00, RECEPTION_BLOCK_HEADER, 0x10]
        response, sw1, sw2 = card_connection.transmit(read_apdu)
        
        if sw1 == 0x90 and sw2 == 0x00 and len(response) >= 2:
            reception_flag = response[0]
            clearance_flags = response[1]
            return (reception_flag, clearance_flags)
        else:
            logger.warning(f"Failed to read Mifare Classic block {RECEPTION_BLOCK_HEADER}, SW: {hex(sw1)} {hex(sw2)}")
            return None
    except Exception as e:
        logger.error(f"Error reading reception header from Mifare Classic: {e}")
        return None


def write_reception_data_mifare_classic(card_connection: CardConnection, data: bytes) -> bool:
    """
    Mifare Classicに受付情報データを書き込む
    
    Args:
        card_connection: カード接続オブジェクト
        data: 書き込むデータ（48バイト）
    
    Returns:
        書き込み成功時True、失敗時False
    """
    try:
        if len(data) != 48:
            logger.error(f"Invalid data length: {len(data)}, expected 48 bytes")
            return False
        
        # Load Keysコマンド
        load_key_apdu = [0xFF, 0x82, 0x00, 0x00, 0x06, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
        response, sw1, sw2 = card_connection.transmit(load_key_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning("Failed to load key for Mifare Classic")
            return False
        
        # Authenticateコマンド（セクター14）
        auth_apdu = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, RECEPTION_SECTOR, 0x60, 0x00]
        response, sw1, sw2 = card_connection.transmit(auth_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to authenticate Mifare Classic sector {RECEPTION_SECTOR}")
            return False
        
        # ブロック58-60に書き込み（3ブロック = 48バイト）
        for i in range(3):
            block = RECEPTION_BLOCK_DATA_START + i
            block_data = list(data[i*16:(i+1)*16])
            # 16バイトに満たない場合は0で埋める
            while len(block_data) < 16:
                block_data.append(0)
            
            write_apdu = [0xFF, 0xD6, 0x00, block, 0x10] + block_data
            response, sw1, sw2 = card_connection.transmit(write_apdu)
            
            if sw1 != 0x90 or sw2 != 0x00:
                logger.warning(f"Failed to write Mifare Classic block {block}, SW: {hex(sw1)} {hex(sw2)}")
                return False
        
        logger.info("Successfully wrote reception data to Mifare Classic")
        return True
    except Exception as e:
        logger.error(f"Error writing reception data to Mifare Classic: {e}")
        return False


def read_reception_data_mifare_classic(card_connection: CardConnection) -> Optional[bytes]:
    """
    Mifare Classicから受付情報データを読み取る
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        読み取ったデータ（48バイト）、失敗時None
    """
    try:
        # Load Keysコマンド
        load_key_apdu = [0xFF, 0x82, 0x00, 0x00, 0x06, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
        response, sw1, sw2 = card_connection.transmit(load_key_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning("Failed to load key for Mifare Classic")
            return None
        
        # Authenticateコマンド（セクター14）
        auth_apdu = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, RECEPTION_SECTOR, 0x60, 0x00]
        response, sw1, sw2 = card_connection.transmit(auth_apdu)
        
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to authenticate Mifare Classic sector {RECEPTION_SECTOR}")
            return None
        
        data = bytearray()
        # ブロック58-60を読み取り（3ブロック = 48バイト）
        for i in range(3):
            block = RECEPTION_BLOCK_DATA_START + i
            read_apdu = [0xFF, 0xB0, 0x00, block, 0x10]
            response, sw1, sw2 = card_connection.transmit(read_apdu)
            
            if sw1 == 0x90 and sw2 == 0x00 and len(response) >= 16:
                data.extend(response[:16])
            else:
                logger.warning(f"Failed to read Mifare Classic block {block}, SW: {hex(sw1)} {hex(sw2)}")
                return None
        
        return bytes(data)
    except Exception as e:
        logger.error(f"Error reading reception data from Mifare Classic: {e}")
        return None


def _truncate_utf8(value: str, max_bytes: int) -> bytes:
    """
    UTF-8のバイト長で安全に切り詰める（途中で文字が壊れないよう調整）。
    """
    raw = value.encode("utf-8")
    if len(raw) <= max_bytes:
        return raw
    trimmed = raw[:max_bytes]
    while trimmed:
        try:
            trimmed.decode("utf-8")
            return trimmed
        except UnicodeDecodeError:
            trimmed = trimmed[:-1]
    return b""


RECEPTION_TOTAL_BYTES = 48
RECEPTION_NAME_BYTES = 24
RECEPTION_ALLERGY_BYTES = 21
RECEPTION_ALLERGY_FLAG_INDEX = 45
RECEPTION_VULNERABILITY_INDEX = 46
RECEPTION_QUIZ_FLAGS_INDEX = 47


def encode_reception_data(resident_data: Dict[str, Any]) -> bytes:
    """
    受付情報をバイナリ形式にエンコードする（48バイト固定）
    
    優先順位: 氏名 > 配慮項目 > アレルギー
    
    フォーマット（計48バイト）:
    - 氏名: 24バイト（UTF-8）
    - アレルギー: 21バイト（UTF-8）
    - アレルギー溢れフラグ: 1ビット（格納領域の最終バイト）
    - 配慮項目フラグ: 1バイト（5bit）
    - クイズ可否フラグ: 1バイト（5bit）
    """
    data = bytearray(RECEPTION_TOTAL_BYTES)
    
    # 氏名（24バイト、UTF-8）
    name = _truncate_utf8(str(resident_data.get("name", "")), RECEPTION_NAME_BYTES)
    if name:
        data[0:len(name)] = name
    
    # アレルギー（21バイト、UTF-8）
    allergy_offset = RECEPTION_NAME_BYTES
    allergy_raw = str(resident_data.get("allergy", ""))
    allergy_raw_bytes = allergy_raw.encode("utf-8")
    allergy_overflow = len(allergy_raw_bytes) > RECEPTION_ALLERGY_BYTES
    if resident_data.get("allergy_overflow"):
        allergy_overflow = True
    allergy = _truncate_utf8(allergy_raw, RECEPTION_ALLERGY_BYTES)
    if allergy:
        data[allergy_offset:allergy_offset + len(allergy)] = allergy
    if allergy_overflow:
        data[RECEPTION_ALLERGY_FLAG_INDEX] = data[RECEPTION_ALLERGY_FLAG_INDEX] | 0x01
    
    # 配慮項目フラグ（1バイト）
    vul = resident_data.get("vulnerabilities", {}) or {}
    vuln_flags = 0
    if isinstance(vul, dict):
        if vul.get("eld"):
            vuln_flags |= 1 << 0
        if vul.get("inf"):
            vuln_flags |= 1 << 1
        if vul.get("prg"):
            vuln_flags |= 1 << 2
        if vul.get("dis"):
            vuln_flags |= 1 << 3
        if vul.get("for"):
            vuln_flags |= 1 << 4
    data[RECEPTION_VULNERABILITY_INDEX] = vuln_flags
    
    # クイズ可否フラグ（1バイト、インデックス47）
    quiz_flags = resident_data.get("quiz_clearance_flags", 0)
    try:
        quiz_flags = int(quiz_flags) if quiz_flags is not None else 0
    except (ValueError, TypeError):
        quiz_flags = 0
    data[RECEPTION_QUIZ_FLAGS_INDEX] = quiz_flags & 0x1F
    
    return bytes(data)


def decode_reception_data(data: bytes) -> Dict[str, Any]:
    """
    バイナリ形式から受付情報をデコードする（48バイト固定）
    
    Args:
        data: バイナリデータ（48バイト）
    
    Returns:
        受付情報の辞書
    """
    if len(data) < RECEPTION_TOTAL_BYTES:
        logger.warning(f"Invalid data length: {len(data)}, expected at least {RECEPTION_TOTAL_BYTES} bytes")
        return {}
    
    result: Dict[str, Any] = {}
    
    # 氏名（24バイト）
    name_bytes = data[0:RECEPTION_NAME_BYTES]
    name_end = name_bytes.find(0)
    if name_end >= 0:
        name_bytes = name_bytes[:name_end]
    result["name"] = name_bytes.decode("utf-8", errors="ignore")
    
    # アレルギー（21バイト）
    allergy_offset = RECEPTION_NAME_BYTES
    allergy_bytes = data[allergy_offset:allergy_offset + RECEPTION_ALLERGY_BYTES]
    allergy_end = allergy_bytes.find(0)
    if allergy_end >= 0:
        allergy_bytes = allergy_bytes[:allergy_end]
    result["allergy"] = allergy_bytes.decode("utf-8", errors="ignore")
    
    # アレルギー溢れフラグ（1ビット）
    result["allergy_overflow"] = True if data[RECEPTION_ALLERGY_FLAG_INDEX] & 0x01 else False

    # 配慮項目フラグ（1バイト）
    flags = data[RECEPTION_VULNERABILITY_INDEX]
    result["vulnerabilities"] = {
        "eld": 1 if flags & (1 << 0) else 0,
        "inf": 1 if flags & (1 << 1) else 0,
        "prg": 1 if flags & (1 << 2) else 0,
        "dis": 1 if flags & (1 << 3) else 0,
        "for": 1 if flags & (1 << 4) else 0,
    }
    
    # クイズ可否フラグ（1バイト、インデックス47）
    result["quiz_clearance_flags"] = data[RECEPTION_QUIZ_FLAGS_INDEX] & 0x1F
    
    return result


def inspect_reception_data_bytes(data: bytes) -> Dict[str, Any]:
    """
    受付データ48バイトをデバッグ用に点検する。
    """
    if len(data) < RECEPTION_TOTAL_BYTES:
        return {
            "valid_length": False,
            "length": len(data),
            "expected_length": RECEPTION_TOTAL_BYTES,
            "raw_hex": data.hex(),
        }

    name_bytes = data[0:RECEPTION_NAME_BYTES]
    allergy_bytes = data[RECEPTION_NAME_BYTES:RECEPTION_NAME_BYTES + RECEPTION_ALLERGY_BYTES]

    def inspect_segment(raw: bytes) -> Dict[str, Any]:
        trimmed = raw.split(b"\x00", 1)[0]
        info: Dict[str, Any] = {
            "raw_hex": raw.hex(),
            "trimmed_hex": trimmed.hex(),
            "utf8_valid": True,
            "decoded": "",
        }
        try:
            info["decoded"] = trimmed.decode("utf-8")
        except UnicodeDecodeError as e:
            info["utf8_valid"] = False
            info["decode_error"] = str(e)
            info["decoded_lossy"] = trimmed.decode("utf-8", errors="replace")
        return info

    return {
        "valid_length": True,
        "length": len(data),
        "raw_hex": data.hex(),
        "name": inspect_segment(name_bytes),
        "allergy": inspect_segment(allergy_bytes),
        "allergy_overflow_flag": bool(data[RECEPTION_ALLERGY_FLAG_INDEX] & 0x01),
        "vulnerability_flags": data[RECEPTION_VULNERABILITY_INDEX],
        "quiz_clearance_flags": data[RECEPTION_QUIZ_FLAGS_INDEX] & 0x1F,
    }


def read_reception_data_raw(idm: str) -> Optional[Dict[str, Any]]:
    """
    NFCカードから受付生データを読み取り、デバッグ情報を返す。
    """
    from smartcard.System import readers

    try:
        reader_list = readers()
        if not reader_list:
            logger.warning("No NFC readers found")
            return None

        reader = _select_preferred_reader(reader_list)
        if reader is None:
            logger.warning("No NFC readers found")
            return None
        connection = reader.createConnection()
        connection.connect()

        card_type = detect_card_type(connection)
        header_result = None
        data = None

        if card_type == "felica":
            header_result = read_reception_header_felica(connection)
            data = read_reception_data_felica(connection)
        elif card_type == "mifare_ultralight":
            header_result = read_reception_header_ntag213(connection)
            data = read_reception_data_ntag213(connection)
        elif card_type == "mifare_classic":
            header_result = read_reception_header_mifare_classic(connection)
            data = read_reception_data_mifare_classic(connection)
        else:
            logger.warning(f"Unsupported card type for reception data: {card_type}")
            return None

        if data is None:
            return None

        inspected = inspect_reception_data_bytes(data)
        return {
            "idm": idm,
            "card_type": card_type,
            "header": {
                "reception_flag": header_result[0] if header_result else None,
                "clearance_flags": header_result[1] if header_result else None,
            },
            "decoded": decode_reception_data(data),
            "inspection": inspected,
        }
    except Exception as e:
        logger.error(f"Error reading raw reception data: {e}")
        return None


def write_reception_data(idm: str, resident_data: Dict[str, Any], max_retries: int = 3) -> bool:
    """
    NFCカードに受付情報を書き込む
    
    Args:
        idm: NFCカードのIDm
        resident_data: 受付情報の辞書
        max_retries: 最大リトライ回数
    
    Returns:
        書き込み成功時True、失敗時False
    """
    from smartcard.System import readers
    
    # データをエンコード
    encoded_data = encode_reception_data(resident_data)
    
    # 受付済みフラグを設定
    reception_flag = 0x01
    
    for attempt in range(max_retries):
        try:
            reader_list = readers()
            if not reader_list:
                logger.warning("No NFC readers found")
                if attempt < max_retries - 1:
                    time.sleep(0.2)
                    continue
                return False
            
            reader = _select_preferred_reader(reader_list)
            if reader is None:
                logger.warning("No NFC readers found")
                if attempt < max_retries - 1:
                    time.sleep(0.2)
                    continue
                return False
            connection = reader.createConnection()
            connection.connect()
            
            card_type = detect_card_type(connection)
            
            if card_type == "felica":
                # クリア可否フラグは既存の値を読み取る（なければ0）
                header_result = read_reception_header_felica(connection)
                clearance_flags = header_result[1] if header_result else 0
                
                success_header = write_reception_header_felica(connection, reception_flag, clearance_flags)
                success_data = write_reception_data_felica(connection, encoded_data)
                success = success_header and success_data
            elif card_type == "mifare_ultralight":
                # クリア可否フラグは既存の値を読み取る（なければ0）
                header_result = read_reception_header_ntag213(connection)
                clearance_flags = header_result[1] if header_result else 0
                
                success_header = write_reception_header_ntag213(connection, reception_flag, clearance_flags)
                success_data = write_reception_data_ntag213(connection, encoded_data)
                success = success_header and success_data
            elif card_type == "mifare_classic":
                header_result = read_reception_header_mifare_classic(connection)
                clearance_flags = header_result[1] if header_result else 0
                
                success_header = write_reception_header_mifare_classic(connection, reception_flag, clearance_flags)
                success_data = write_reception_data_mifare_classic(connection, encoded_data)
                success = success_header and success_data
            else:
                logger.warning(f"Unsupported card type for reception data: {card_type}")
                return False
            
            if success:
                logger.info(f"Successfully wrote reception data to {card_type} card")
                return True
            elif attempt < max_retries - 1:
                logger.info(f"Write attempt {attempt + 1} failed, retrying...")
        except Exception as e:
            logger.error(f"Error writing reception data (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                continue
    
    logger.error(f"Failed to write reception data after {max_retries} attempts")
    return False


def read_reception_data(idm: str) -> Optional[Dict[str, Any]]:
    """
    NFCカードから受付情報を読み取る
    
    Args:
        idm: NFCカードのIDm
    
    Returns:
        受付情報の辞書、失敗時None
    """
    from smartcard.System import readers
    
    try:
        reader_list = readers()
        if not reader_list:
            logger.warning("No NFC readers found")
            return None
        
        reader = _select_preferred_reader(reader_list)
        if reader is None:
            logger.warning("No NFC readers found")
            return None
        connection = reader.createConnection()
        connection.connect()
        
        card_type = detect_card_type(connection)
        
        if card_type == "felica":
            data = read_reception_data_felica(connection)
        elif card_type == "mifare_ultralight":
            data = read_reception_data_ntag213(connection)
        elif card_type == "mifare_classic":
            data = read_reception_data_mifare_classic(connection)
        else:
            logger.warning(f"Unsupported card type for reception data: {card_type}")
            return None
        
        if data:
            return decode_reception_data(data)
        return None
    except Exception as e:
        logger.error(f"Error reading reception data: {e}")
        return None


# ============================================================================
# クリア可否フラグ管理機能
# ============================================================================

def write_booth_clearance_flags(idm: str, booth_flags: List[bool], max_retries: int = 3) -> bool:
    """
    5つの試練のクリア可否を1bitずつ記録する（ヘッダー領域のみ更新、データ領域は触らない）
    
    Args:
        idm: NFCカードのIDm
        booth_flags: 5つの試練のクリア可否フラグのリスト（True=クリア済み）
        max_retries: 最大リトライ回数
    
    Returns:
        書き込み成功時True、失敗時False
    """
    from smartcard.System import readers
    
    if len(booth_flags) != 5:
        logger.error(f"Invalid booth_flags length: {len(booth_flags)}, expected 5")
        return False
    
    # 5bitのフラグを1バイトに変換
    clearance_flags = 0
    for i, flag in enumerate(booth_flags):
        if flag:
            clearance_flags |= (1 << i)
    
    for attempt in range(max_retries):
        try:
            reader_list = readers()
            if not reader_list:
                logger.warning("No NFC readers found")
                if attempt < max_retries - 1:
                    time.sleep(0.2)
                    continue
                return False
            
            reader = _select_preferred_reader(reader_list)
            if reader is None:
                if attempt < max_retries - 1:
                    time.sleep(0.2)
                    continue
                return False
            connection = reader.createConnection()
            connection.connect()
            
            card_type = detect_card_type(connection)
            
            # ヘッダー領域のみを更新（データ領域は触らない）
            # 既存の受付フラグを読み取り、クリア可否フラグだけ更新
            success = False
            if card_type == "mifare_ultralight":
                header_result = read_reception_header_ntag213(connection)
                reception_flag = header_result[0] if header_result else 0x01
                success = write_reception_header_ntag213(connection, reception_flag, clearance_flags)
            elif card_type == "felica":
                header_result = read_reception_header_felica(connection)
                reception_flag = header_result[0] if header_result else 0x01
                success = write_reception_header_felica(connection, reception_flag, clearance_flags)
            elif card_type == "mifare_classic":
                header_result = read_reception_header_mifare_classic(connection)
                reception_flag = header_result[0] if header_result else 0x01
                success = write_reception_header_mifare_classic(connection, reception_flag, clearance_flags)
            else:
                logger.warning(f"Unsupported card type: {card_type}")
                return False
            
            if success:
                logger.info("Successfully wrote clearance flags to card header")
                return True
            elif attempt < max_retries - 1:
                logger.info(f"Write attempt {attempt + 1} failed, retrying...")
                time.sleep(0.2)
        except Exception as e:
            logger.error(f"Error writing clearance flags (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(0.2)
                continue
    
    logger.error(f"Failed to write clearance flags after {max_retries} attempts")
    return False


def read_booth_clearance_flags(idm: str) -> Optional[List[bool]]:
    """
    クリア可否フラグを読み取る（ヘッダー領域から直接読み取る）
    
    Args:
        idm: NFCカードのIDm
    
    Returns:
        5つの試練のクリア状態のリスト（True=クリア済み）、読み取り失敗時はNone
    """
    from smartcard.System import readers
    
    try:
        reader_list = readers()
        if not reader_list:
            logger.warning("No NFC readers found")
            return None
        
        reader = _select_preferred_reader(reader_list)
        if reader is None:
            logger.warning("No NFC readers found")
            return None
        connection = reader.createConnection()
        connection.connect()
        
        card_type = detect_card_type(connection)
        
        header_result = None
        if card_type == "mifare_ultralight":
            header_result = read_reception_header_ntag213(connection)
        elif card_type == "felica":
            header_result = read_reception_header_felica(connection)
        elif card_type == "mifare_classic":
            header_result = read_reception_header_mifare_classic(connection)
        else:
            logger.warning(f"Unsupported card type: {card_type}")
            return None
        
        if header_result is None:
            logger.warning("Failed to read reception header for clearance flags")
            return None
        
        # ヘッダーの2バイト目がクリア可否フラグ
        clearance_flags = header_result[1]
        booth_flags = []
        for i in range(5):
            booth_flags.append((clearance_flags & (1 << i)) != 0)
        return booth_flags
    except Exception as e:
        logger.error(f"Error reading clearance flags: {e}")
        return None


def set_booth_cleared(idm: str, booth_id: int, max_retries: int = 3) -> bool:
    """
    指定された試練のクリアフラグを設定する
    
    Args:
        idm: NFCカードのIDm
        booth_id: 試練ID（1-5）
        max_retries: 最大リトライ回数
    
    Returns:
        書き込み成功時True、失敗時False
    """
    if booth_id < 1 or booth_id > 5:
        logger.error(f"Invalid booth_id: {booth_id}, must be 1-5")
        return False
    
    # 既存のフラグを読み取る（リトライ付き）
    current_flags = None
    for attempt in range(max_retries):
        current_flags = read_booth_clearance_flags(idm)
        if current_flags is not None:
            break
        logger.warning(f"Retry reading clearance flags (attempt {attempt + 1}/{max_retries})")
        import time
        time.sleep(0.3)
    
    # 読み取り失敗時は既存フラグを保持するため、書き込みを中止しない
    # 代わりに空のフラグから開始（最悪ケースでも指定ブースのクリアは記録される）
    if current_flags is None:
        logger.warning(f"Could not read existing flags, will only set booth {booth_id}")
        current_flags = [False] * 5
    
    # 指定された試練のフラグを設定
    current_flags[booth_id - 1] = True
    
    # フラグを書き込む
    return write_booth_clearance_flags(idm, current_flags, max_retries)


# ============================================================================
# カードデータ削除機能（セキュリティ対策）
# ============================================================================

def erase_card_data(idm: str, max_retries: int = 3) -> bool:
    """
    NFCカードのユーザーデータを完全に消去する（セキュリティ対策）
    
    以下の領域を初期化します:
    - クイズ進捗（ページ0x14）: クリア数を0に
    - 受付ヘッダー（ページ0x15）: 受付フラグとクリア可否フラグを0に
    - 受付データ（ページ0x16-0x27）: 全て0で上書き
    
    システム領域（ページ0-3）は絶対に書き込みません。
    
    Args:
        idm: NFCカードのIDm
        max_retries: 最大リトライ回数
    
    Returns:
        消去成功時True、失敗時False
    """
    from smartcard.System import readers
    
    for attempt in range(max_retries):
        try:
            reader_list = readers()
            if not reader_list:
                logger.warning("No NFC readers found")
                if attempt < max_retries - 1:
                    time.sleep(0.2)
                    continue
                return False
            
            reader = _select_preferred_reader(reader_list)
            if reader is None:
                if attempt < max_retries - 1:
                    time.sleep(0.2)
                    continue
                return False
            connection = reader.createConnection()
            connection.connect()
            
            card_type = detect_card_type(connection)
            
            success = False
            if card_type == "mifare_ultralight":
                success = _erase_card_data_ntag(connection)
            elif card_type == "felica":
                success = _erase_card_data_felica(connection)
            elif card_type == "mifare_classic":
                success = _erase_card_data_mifare_classic(connection)
            else:
                logger.warning(f"Unsupported card type for erase: {card_type}")
                return False
            
            if success:
                logger.info(f"Successfully erased card data for {card_type} card")
                return True
            elif attempt < max_retries - 1:
                logger.info(f"Erase attempt {attempt + 1} failed, retrying...")
                time.sleep(0.2)
        except Exception as e:
            logger.error(f"Error erasing card data (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(0.2)
                continue
    
    logger.error(f"Failed to erase card data after {max_retries} attempts")
    return False


def _erase_card_data_ntag(card_connection: CardConnection) -> bool:
    """
    NTAG213/NTAG215のユーザーデータを消去する
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        消去成功時True、失敗時False
    """
    try:
        # クイズ進捗を消去（ページ0x14）
        write_apdu = [0xFF, 0xD6, 0x00, QUIZ_PAGE, 0x04, 0x00, 0x00, 0x00, 0x00]
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to erase quiz page, SW: {hex(sw1)} {hex(sw2)}")
            return False
        
        # 受付ヘッダーを消去（ページ0x15）
        write_apdu = [0xFF, 0xD6, 0x00, RECEPTION_PAGE_HEADER, 0x04, 0x00, 0x00, 0x00, 0x00]
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to erase reception header, SW: {hex(sw1)} {hex(sw2)}")
            return False
        
        # 受付データを消去（ページ0x16-0x27、12ページ）
        for page in range(RECEPTION_PAGE_DATA_START, RECEPTION_PAGE_DATA_END + 1):
            write_apdu = [0xFF, 0xD6, 0x00, page, 0x04, 0x00, 0x00, 0x00, 0x00]
            response, sw1, sw2 = card_connection.transmit(write_apdu)
            if sw1 != 0x90 or sw2 != 0x00:
                logger.warning(f"Failed to erase page {hex(page)}, SW: {hex(sw1)} {hex(sw2)}")
                return False
        
        logger.info("Successfully erased NTAG card data")
        return True
    except Exception as e:
        logger.error(f"Error erasing NTAG card data: {e}")
        return False


def _erase_card_data_felica(card_connection: CardConnection) -> bool:
    """
    FeliCaカードのユーザーデータを消去する
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        消去成功時True、失敗時False
    """
    try:
        # クイズ進捗を消去（ブロック0）
        write_data = [0x00] * 16
        write_apdu = [0xFF, 0xD6, 0x00, QUIZ_BLOCK_NUMBER, 0x10] + write_data
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to erase FeliCa quiz block, SW: {hex(sw1)} {hex(sw2)}")
            return False
        
        # 受付ヘッダーを消去（ブロック1）
        write_apdu = [0xFF, 0xD6, 0x00, RECEPTION_BLOCK_HEADER_NUM, 0x10] + write_data
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to erase FeliCa reception header, SW: {hex(sw1)} {hex(sw2)}")
            return False
        
        # 受付データを消去（ブロック2-4）
        for block in range(RECEPTION_BLOCK_DATA_START_NUM, RECEPTION_BLOCK_DATA_END_NUM + 1):
            write_apdu = [0xFF, 0xD6, 0x00, block, 0x10] + write_data
            response, sw1, sw2 = card_connection.transmit(write_apdu)
            if sw1 != 0x90 or sw2 != 0x00:
                logger.warning(f"Failed to erase FeliCa block {block}, SW: {hex(sw1)} {hex(sw2)}")
                return False
        
        logger.info("Successfully erased FeliCa card data")
        return True
    except Exception as e:
        logger.error(f"Error erasing FeliCa card data: {e}")
        return False


def _erase_card_data_mifare_classic(card_connection: CardConnection) -> bool:
    """
    Mifare Classicカードのユーザーデータを消去する
    
    Args:
        card_connection: カード接続オブジェクト
    
    Returns:
        消去成功時True、失敗時False
    """
    try:
        # Load Keys
        load_key_apdu = [0xFF, 0x82, 0x00, 0x00, 0x06, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
        response, sw1, sw2 = card_connection.transmit(load_key_apdu)
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning("Failed to load key for Mifare Classic")
            return False
        
        # Authenticate
        auth_apdu = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, QUIZ_SECTOR, 0x60, 0x00]
        response, sw1, sw2 = card_connection.transmit(auth_apdu)
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to authenticate Mifare Classic sector {QUIZ_SECTOR}")
            return False
        
        write_data = [0x00] * 16
        
        # クイズ進捗を消去（ブロック56）
        write_apdu = [0xFF, 0xD6, 0x00, QUIZ_BLOCK, 0x10] + write_data
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to erase Mifare Classic quiz block, SW: {hex(sw1)} {hex(sw2)}")
            return False
        
        # 受付ヘッダーを消去（ブロック57）
        write_apdu = [0xFF, 0xD6, 0x00, RECEPTION_BLOCK_HEADER, 0x10] + write_data
        response, sw1, sw2 = card_connection.transmit(write_apdu)
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Failed to erase Mifare Classic reception header, SW: {hex(sw1)} {hex(sw2)}")
            return False
        
        # 受付データを消去（ブロック58-60）
        for block in range(RECEPTION_BLOCK_DATA_START, RECEPTION_BLOCK_DATA_END + 1):
            write_apdu = [0xFF, 0xD6, 0x00, block, 0x10] + write_data
            response, sw1, sw2 = card_connection.transmit(write_apdu)
            if sw1 != 0x90 or sw2 != 0x00:
                logger.warning(f"Failed to erase Mifare Classic block {block}, SW: {hex(sw1)} {hex(sw2)}")
                return False
        
        logger.info("Successfully erased Mifare Classic card data")
        return True
    except Exception as e:
        logger.error(f"Error erasing Mifare Classic card data: {e}")
        return False
