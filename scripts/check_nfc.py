#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PicoRESQ NFCリーダー接続確認スクリプト

バックエンドサーバーが起動している状態で、NFCリーダーの接続状態を確認します。
"""

import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

# カラー出力用のANSIエスケープコード
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    """ヘッダーを表示"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")

def print_success(text):
    """成功メッセージを表示"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")

def print_error(text):
    """エラーメッセージを表示"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

def print_warning(text):
    """警告メッセージを表示"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")

def print_info(text):
    """情報メッセージを表示"""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")

def check_nfc_status(api_url="http://localhost:8000"):
    """NFCリーダーの状態を確認"""
    try:
        url = f"{api_url}/api/system/nfc-status"
        req = urllib.request.Request(url)
        
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read().decode('utf-8')
            return json.loads(data)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ConnectionRefusedError) or "Connection refused" in str(e):
            print_error("バックエンドサーバーに接続できません。")
            print_info("バックエンドサーバーが起動しているか確認してください:")
            print_info("  python3 scripts/start_backend.py")
        else:
            print_error(f"接続エラー: {e}")
        return None
    except urllib.error.HTTPError as e:
        print_error(f"HTTPエラー: {e.code} {e.reason}")
        return None
    except Exception as e:
        print_error(f"リクエストエラー: {e}")
        return None

def main():
    """メイン処理"""
    print_header("NFCリーダー接続状態確認")
    
    print_info("バックエンドサーバーに接続中...")
    status = check_nfc_status()
    
    if status is None:
        sys.exit(1)
    
    print("")
    print("=" * 60)
    print("NFCリーダー状態")
    print("=" * 60)
    print("")
    
    # リーダーの利用可能性
    if status.get("nfc_reader_available"):
        print_success("NFCリーダーが利用可能です")
        print_info(f"検出されたリーダー数: {status.get('reader_count', 0)}台")
        
        # リーダー詳細
        readers = status.get("readers", [])
        if readers:
            print("\n検出されたリーダー:")
            for i, reader in enumerate(readers, 1):
                print(f"  {i}. {reader}")
        else:
            print_warning("リーダーの詳細情報が取得できませんでした")
        
        # リーダーの動作状態
        if status.get("is_running"):
            print_success("リーダーは動作中です")
        else:
            print_warning("リーダーは停止しています")
        
        # 現在検知中のカード
        current_card = status.get("current_card_idm")
        if current_card:
            print_info(f"現在検知中のカード: {current_card}")
        else:
            print_info("現在検知中のカード: なし")
    else:
        print_error("NFCリーダーが見つかりません")
        
        error = status.get("error")
        if error:
            print_error(f"エラー詳細: {error}")
        
        print("")
        print_warning("対処方法:")
        print("  1. NFCリーダーがUSBポートに接続されているか確認してください")
        print("  2. リーダーのドライバーが正しくインストールされているか確認してください")
        print("  3. バックエンドサーバーを再起動してください")
    
    print("")
    print("=" * 60)
    print("")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n確認を中断しました。")
        sys.exit(0)
    except Exception as e:
        print_error(f"予期しないエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
