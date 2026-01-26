#!/usr/bin/env python3
"""
NFCリーダーの動作確認用テストスクリプト

このスクリプトを実行すると、NFCリーダーが正しく動作しているか確認できます。
"""
import sys
import time
from pathlib import Path

# プロジェクトのルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

try:
    from smartcard.System import readers
    from smartcard.CardMonitoring import CardMonitor, CardObserver
    from smartcard.util import toHexString
except ImportError as e:
    print(f"\n✗ 必要なライブラリがインストールされていません: {e}")
    print("   仮想環境をアクティベートして、以下のコマンドを実行してください:")
    print("   uv sync")
    sys.exit(1)


class TestCardObserver(CardObserver):
    """テスト用のカードオブザーバー"""
    
    def __init__(self):
        self.card_detected = False
        self.card_idm = None
    
    def update(self, observable, actions):
        """カード検知時のコールバック"""
        (addedcards, removedcards) = actions
        
        # カード検知時の処理
        for card in addedcards:
            try:
                print("\n✓ カードを検知しました！")
                card.connection = card.createConnection()
                card.connection.connect()
                
                # Get UID/IDm (Standard Get Data command)
                apdu = [0xFF, 0xCA, 0x00, 0x00, 0x00]
                response, sw1, sw2 = card.connection.transmit(apdu)
                
                if sw1 == 0x90 and sw2 == 0x00:
                    uid = toHexString(response).replace(' ', '')
                    self.card_idm = uid
                    self.card_detected = True
                    print(f"   IDm/UID: {uid}")
                else:
                    print(f"   ⚠️  IDmの取得に失敗しました (SW: {hex(sw1)} {hex(sw2)})")
                    
            except Exception as e:
                print(f"   ✗ エラー: {e}")
                import traceback
                traceback.print_exc()
        
        # カード離脱時の処理
        for card in removedcards:
            if self.card_detected:
                print(f"\n✓ カードが離れました: {self.card_idm}")
                self.card_detected = False
                self.card_idm = None


def main():
    """メイン処理"""
    print("=" * 60)
    print("NFCリーダー動作確認テスト")
    print("=" * 60)
    
    # リーダーの検出
    print("\n1. NFCリーダーの検出中...")
    try:
        reader_list = readers()
        if not reader_list:
            print("\n✗ NFCリーダーが見つかりませんでした。")
            print("\n確認事項:")
            print("  - NFCリーダーがUSBポートに接続されているか")
            print("  - リーダーのドライバーがインストールされているか")
            print("  - macOSの場合: PC/SCドライバーがインストールされているか")
            print("  - Linuxの場合: pcscdサービスが起動しているか (sudo systemctl start pcscd)")
            return 1
        
        print(f"✓ {len(reader_list)}台のNFCリーダーを検出しました:")
        for i, reader in enumerate(reader_list, 1):
            print(f"   {i}. {reader}")
    
    except Exception as e:
        print(f"\n✗ リーダーの検出中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # カードモニターの起動
    print("\n2. カードモニターを起動中...")
    try:
        observer = TestCardObserver()
        monitor = CardMonitor()
        monitor.addObserver(observer)
        print("✓ カードモニターが起動しました")
        print("\n" + "=" * 60)
        print("カードをリーダーにかざしてください...")
        print("(終了するには Ctrl+C を押してください)")
        print("=" * 60)
        
        # カード検知を待機
        while True:
            time.sleep(0.5)
            if observer.card_detected:
                print("\n✓ カードが正常に検知されました！")
                print(f"   IDm/UID: {observer.card_idm}")
                print("\nカードを離すと、再度検知待機状態になります。")
    
    except KeyboardInterrupt:
        print("\n\nテストを終了します...")
        monitor.deleteObserver(observer)
        return 0
    except Exception as e:
        print(f"\n✗ カードモニターの起動中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
