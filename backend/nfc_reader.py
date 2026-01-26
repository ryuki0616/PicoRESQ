"""
NFCリーダー - カード検知とIDm/UID取得

既存のPicoCERAシステムから移植したNFCリーダー機能です。
"""
import threading
import time
import logging
from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.util import toHexString

logger = logging.getLogger("uvicorn")


class NFCReader(CardObserver):
    """
    NFCカード検知とIDm/UID取得を行うクラス
    
    PC/SC APIを使用してNFCカードを監視し、検知時にコールバック関数を実行します。
    """
    
    def __init__(self, on_tag_detected, on_tag_removed=None):
        """
        NFCReaderの初期化
        
        Args:
            on_tag_detected: カード検知時に呼ばれるコールバック関数（idm: strを受け取る）
            on_tag_removed: カード離脱時に呼ばれるコールバック関数（idm: strを受け取る、オプション）
        """
        self.on_tag_detected = on_tag_detected
        self.on_tag_removed = on_tag_removed
        self.monitor = None
        self.is_running = False
        self.current_card_idm = None  # 現在検知されているカードのIDmを保持

    def start(self) -> None:
        """NFCリーダーを起動する"""
        if self.is_running:
            logger.info("NFC Reader is already running")
            return
        try:
            from smartcard.System import readers
            reader_list = readers()
            if not reader_list:
                logger.error("No NFC readers found. Please connect an NFC reader.")
                print("\n⚠️  NFCリーダーが見つかりません。")
                print("   リーダーが接続されているか確認してください。")
                return
            
            logger.info(f"Found {len(reader_list)} NFC reader(s): {[str(r) for r in reader_list]}")
            print(f"\n✓ NFCリーダーを検出しました: {reader_list[0]}")
            
            self.monitor = CardMonitor()
            self.monitor.addObserver(self)
            self.is_running = True
            logger.info("NFC Reader (PC/SC) started successfully")
            print("✓ NFCリーダーが起動しました。カードをかざしてください。")
        except Exception as e:
            logger.error(f"Failed to start NFC Reader: {e}")
            import traceback
            logger.error(traceback.format_exc())
            print(f"\n✗ NFCリーダーの起動に失敗しました: {e}")
            print("   リーダーのドライバーがインストールされているか確認してください。")

    def stop(self) -> None:
        """NFCリーダーを停止する"""
        if self.monitor:
            self.monitor.deleteObserver(self)
            self.monitor = None
        self.is_running = False
        logger.info("NFC Reader stopped")

    def update(self, observable, actions) -> None:
        """
        カード検知・離脱時のコールバック
        
        Args:
            observable: 監視対象
            actions: カードの追加・削除アクション
        """
        (addedcards, removedcards) = actions
        
        # カード検知時の処理
        for card in addedcards:
            try:
                logger.debug(f"Card added: {card}")
                card.connection = card.createConnection()
                card.connection.connect()
                
                # Get UID/IDm (Standard Get Data command)
                apdu = [0xFF, 0xCA, 0x00, 0x00, 0x00]
                response, sw1, sw2 = card.connection.transmit(apdu)
                
                if sw1 == 0x90 and sw2 == 0x00:
                    uid = toHexString(response).replace(' ', '')
                    logger.info(f"Tag detected: {uid}")
                    print(f"\n✓ カードを検知しました: {uid}")
                    self.current_card_idm = uid  # 現在のカードIDmを保存
                    self.on_tag_detected(uid)
                else:
                    logger.warning(f"Tag detected but failed to get UID (SW: {hex(sw1)} {hex(sw2)})")
                    print(f"\n⚠️  カードを検知しましたが、IDmの取得に失敗しました (SW: {hex(sw1)} {hex(sw2)})")
                    
            except Exception as e:
                logger.error(f"Error processing tag: {e}")
                import traceback
                logger.error(traceback.format_exc())
                print(f"\n✗ カード処理エラー: {e}")
        
        # カード離脱時の処理
        for card in removedcards:
            try:
                if self.current_card_idm and self.on_tag_removed:
                    logger.info(f"Tag removed: {self.current_card_idm}")
                    print(f"\n✓ カードが離れました: {self.current_card_idm}")
                    removed_idm = self.current_card_idm
                    self.current_card_idm = None  # カードIDmをクリア
                    self.on_tag_removed(removed_idm)
            except Exception as e:
                logger.error(f"Error processing tag removal: {e}")
                import traceback
                logger.error(traceback.format_exc())
                print(f"\n✗ カード離脱処理エラー: {e}")