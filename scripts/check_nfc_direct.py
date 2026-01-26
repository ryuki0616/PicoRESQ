#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PicoRESQ NFCリーダー直接確認スクリプト（サーバー不要）

バックエンドサーバーを起動せずに、直接NFCリーダーの接続状態を確認し、
macOSのポップアップで表示します。
"""

import sys
import subprocess
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

def check_nfc_readers():
    """NFCリーダーを直接チェック"""
    try:
        from smartcard.System import readers
        
        reader_list = readers()
        reader_count = len(reader_list) if reader_list else 0
        
        return {
            "available": reader_count > 0,
            "count": reader_count,
            "readers": [str(r) for r in reader_list] if reader_list else [],
            "error": None
        }
    except ImportError:
        return {
            "available": False,
            "count": 0,
            "readers": [],
            "error": "pyscardモジュールがインストールされていません"
        }
    except Exception as e:
        return {
            "available": False,
            "count": 0,
            "readers": [],
            "error": str(e)
        }

def show_popup(title, message, icon="note"):
    """
    macOSのポップアップを表示
    
    Args:
        title: ポップアップのタイトル
        message: ポップアップのメッセージ
        icon: アイコンタイプ ("note", "caution", "stop")
    """
    script = f'''
    display dialog "{message}" with title "{title}" buttons {{"OK"}} default button "OK" with icon {icon}
    '''
    
    try:
        subprocess.run(
            ['osascript', '-e', script],
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError as e:
        print_error(f"ポップアップの表示に失敗しました: {e}")
    except FileNotFoundError:
        print_warning("osascriptが見つかりません。macOSでのみ動作します。")
        print_info(f"{title}: {message}")

def main():
    """メイン処理"""
    print_header("NFCリーダー直接確認（サーバー不要）")
    
    print_info("NFCリーダーを直接チェック中...")
    status = check_nfc_readers()
    
    print("")
    print("=" * 60)
    print("NFCリーダー状態")
    print("=" * 60)
    print("")
    
    # 結果を構築
    if status["error"]:
        print_error(f"エラー: {status['error']}")
        message = f"エラーが発生しました:\n{status['error']}"
        show_popup("NFCリーダー確認", message, "stop")
        sys.exit(1)
    
    if status["available"]:
        print_success("NFCリーダーが利用可能です")
        print_info(f"検出されたリーダー数: {status['count']}台")
        
        # リーダー詳細
        readers = status["readers"]
        if readers:
            print("\n検出されたリーダー:")
            reader_list_text = ""
            for i, reader in enumerate(readers, 1):
                print(f"  {i}. {reader}")
                reader_list_text += f"{i}. {reader}\n"
            
            # ポップアップ表示
            message = f"NFCリーダーが検出されました！\n\n検出されたリーダー数: {status['count']}台\n\n{reader_list_text}"
            show_popup("NFCリーダー確認", message, "note")
        else:
            print_warning("リーダーの詳細情報が取得できませんでした")
            show_popup("NFCリーダー確認", "NFCリーダーは検出されましたが、詳細情報が取得できませんでした。", "caution")
    else:
        print_error("NFCリーダーが見つかりません")
        
        message = "NFCリーダーが見つかりませんでした。\n\n確認事項:\n• NFCリーダーがUSBポートに接続されているか\n• リーダーのドライバーがインストールされているか\n• macOSの場合: PC/SCドライバーがインストールされているか"
        show_popup("NFCリーダー確認", message, "caution")
    
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
