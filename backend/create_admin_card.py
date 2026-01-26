#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管理者カード作成スクリプト

NFCカードをかざして、管理者カードとして登録します。

使用方法:
    仮想環境を有効化してから実行してください:
    
    # uvを使用する場合
    cd backend
    uv run python create_admin_card.py
    
    # または仮想環境を使用する場合
    cd backend
    source venv/bin/activate  # macOS/Linux
    # または
    venv\Scripts\activate  # Windows
    python create_admin_card.py
"""

import json
import sys
from pathlib import Path

try:
    from smartcard.CardMonitoring import CardMonitor, CardObserver
    from smartcard.util import toHexString
except ImportError:
    print("エラー: pyscardパッケージがインストールされていません。")
    print("\n以下のいずれかの方法でインストールしてください:")
    print("\n1. uvを使用する場合:")
    print("   cd backend")
    print("   uv sync")
    print("   uv run python create_admin_card.py")
    print("\n2. pipを使用する場合:")
    print("   cd backend")
    print("   source venv/bin/activate  # macOS/Linux")
    print("   # または venv\\Scripts\\activate  # Windows")
    print("   pip install pyscard")
    print("   python create_admin_card.py")
    sys.exit(1)

import time

ADMIN_CARDS_FILE = Path(__file__).parent / "admin_cards.json"


class AdminCardCreator(CardObserver):
    """管理者カード作成用のNFCリーダー"""
    
    def __init__(self):
        self.card_idm = None
        self.card_detected = False
        
    def update(self, observable, actions):
        """カード検知時のコールバック"""
        (addedcards, removedcards) = actions
        
        for card in addedcards:
            try:
                card.connection = card.createConnection()
                card.connection.connect()
                
                # Get UID/IDm (Standard Get Data command)
                apdu = [0xFF, 0xCA, 0x00, 0x00, 0x00]
                response, sw1, sw2 = card.connection.transmit(apdu)
                
                if sw1 == 0x90 and sw2 == 0x00:
                    uid = toHexString(response).replace(' ', '')
                    self.card_idm = uid
                    self.card_detected = True
                    print(f"\n✓ カードを検知しました: {uid}")
                else:
                    print(f"\n✗ カードの読み取りに失敗しました (SW: {hex(sw1)} {hex(sw2)})")
                    
            except Exception as e:
                print(f"\n✗ エラー: {e}")


def load_admin_cards():
    """管理者カードリストを読み込む"""
    try:
        if ADMIN_CARDS_FILE.exists():
            with open(ADMIN_CARDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("admin_card_ids", [])
        return []
    except Exception as e:
        print(f"エラー: 管理者カードリストの読み込みに失敗しました: {e}")
        return []


def save_admin_cards(admin_card_ids):
    """管理者カードリストを保存する"""
    try:
        data = {
            "admin_card_ids": admin_card_ids,
            "description": "管理者カードのIDm/UIDリスト。このリストに含まれるカードのみが管理者画面にアクセスできます。"
        }
        with open(ADMIN_CARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"エラー: 管理者カードリストの保存に失敗しました: {e}")
        return False


def add_admin_card(card_idm):
    """管理者カードを追加する"""
    admin_cards = load_admin_cards()
    card_idm_upper = card_idm.upper()
    
    if card_idm_upper in [card.upper() for card in admin_cards]:
        print(f"⚠ このカードは既に管理者カードとして登録されています: {card_idm}")
        return False
    
    admin_cards.append(card_idm_upper)
    
    if save_admin_cards(admin_cards):
        print(f"✓ 管理者カードとして登録しました: {card_idm_upper}")
        return True
    else:
        return False


def remove_admin_card(card_idm):
    """管理者カードを削除する"""
    admin_cards = load_admin_cards()
    card_idm_upper = card_idm.upper()
    
    if card_idm_upper not in [card.upper() for card in admin_cards]:
        print(f"⚠ このカードは管理者カードとして登録されていません: {card_idm}")
        return False
    
    admin_cards = [card for card in admin_cards if card.upper() != card_idm_upper]
    
    if save_admin_cards(admin_cards):
        print(f"✓ 管理者カードから削除しました: {card_idm_upper}")
        return True
    else:
        return False


def list_admin_cards():
    """登録されている管理者カードのリストを表示"""
    admin_cards = load_admin_cards()
    
    if not admin_cards:
        print("\n登録されている管理者カードはありません。")
    else:
        print(f"\n登録されている管理者カード ({len(admin_cards)}枚):")
        for i, card_id in enumerate(admin_cards, 1):
            print(f"  {i}. {card_id}")


def main():
    """メイン処理"""
    print("=" * 60)
    print("管理者カード作成ツール")
    print("=" * 60)
    print("\n操作を選択してください:")
    print("  1. 管理者カードを追加（カードをかざす）")
    print("  2. 管理者カードを削除（カードをかざす）")
    print("  3. 登録済み管理者カードの一覧表示")
    print("  4. 終了")
    
    try:
        choice = input("\n選択 (1-4): ").strip()
        
        if choice == "1":
            print("\n管理者カードとして登録するNFCカードをかざしてください...")
            creator = AdminCardCreator()
            monitor = CardMonitor()
            monitor.addObserver(creator)
            
            # カード検知を待つ（最大30秒）
            timeout = 30
            start_time = time.time()
            while not creator.card_detected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            monitor.deleteObserver(creator)
            
            if creator.card_detected and creator.card_idm:
                add_admin_card(creator.card_idm)
            else:
                print("\n✗ カードが検知されませんでした。タイムアウトしました。")
                
        elif choice == "2":
            print("\n管理者カードから削除するNFCカードをかざしてください...")
            creator = AdminCardCreator()
            monitor = CardMonitor()
            monitor.addObserver(creator)
            
            # カード検知を待つ（最大30秒）
            timeout = 30
            start_time = time.time()
            while not creator.card_detected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            monitor.deleteObserver(creator)
            
            if creator.card_detected and creator.card_idm:
                remove_admin_card(creator.card_idm)
            else:
                print("\n✗ カードが検知されませんでした。タイムアウトしました。")
                
        elif choice == "3":
            list_admin_cards()
            
        elif choice == "4":
            print("\n終了します。")
            sys.exit(0)
        else:
            print("\n✗ 無効な選択です。")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n中断されました。")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
