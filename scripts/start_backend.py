#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PicoRESQ クイズシステム - バックエンド起動スクリプト (Python版・クロスプラットフォーム)
"""

import os
import sys
import subprocess
import platform
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
    UNDERLINE = '\033[4m'

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

def check_uv():
    """uvのインストールをチェック"""
    print_info("uvのインストールを確認中...")
    try:
        result = subprocess.run(
            ['uv', '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()
        print_success(f"uv {version} を確認しました。")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def check_dependencies(backend_dir):
    """依存関係の確認とインストール"""
    use_uv = check_uv()
    
    if use_uv:
        # uvを使用する場合、依存関係を自動的にインストール
        print_info("uvを使用して依存関係を確認中...")
        try:
            result = subprocess.run(
                ['uv', 'sync'],
                cwd=backend_dir,
                capture_output=True,
                text=True,
                check=True
            )
            print_success("依存関係の確認が完了しました。")
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"依存関係のインストールに失敗しました: {e}")
            print_info("手動でインストールしてください: cd backend && uv sync")
            return False
    else:
        # 仮想環境を使用する場合
        venv_dir = backend_dir / '.venv'
        venv_dir_alt = backend_dir / 'venv'
        
        if venv_dir.exists() or venv_dir_alt.exists():
            print_info("仮想環境が見つかりました。")
            # 依存関係がインストールされているか確認
            requirements_file = backend_dir / 'requirements.txt'
            if requirements_file.exists():
                print_info("依存関係を確認中...")
                # 簡単なチェック: sqlalchemyがインストールされているか
                try:
                    if venv_dir.exists():
                        python_cmd = venv_dir / 'bin' / 'python'
                    else:
                        python_cmd = venv_dir_alt / 'bin' / 'python'
                    
                    result = subprocess.run(
                        [str(python_cmd), '-c', 'import sqlalchemy'],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode != 0:
                        print_warning("sqlalchemyが見つかりません。依存関係をインストールしてください。")
                        print_info("手動でインストール: cd backend && source .venv/bin/activate && pip install -r requirements.txt")
                        return False
                except Exception:
                    pass
            
            return True
        else:
            print_warning("仮想環境が見つかりません。")
            print_info("セットアップスクリプトを実行してください: python scripts/setup.py")
            return False

def start_server(backend_dir):
    """バックエンドサーバーを起動"""
    print_info("バックエンドサーバーを起動します...")
    print_info("サーバーURL: http://127.0.0.1:8000")
    print_info("APIドキュメント: http://127.0.0.1:8000/docs")
    print_info("停止するには Ctrl+C を押してください")
    print("")
    
    use_uv = check_uv()
    
    try:
        if use_uv:
            # uv runを使用
            subprocess.run(
                ['uv', 'run', 'python', '-m', 'uvicorn', 'main:app', '--reload', '--host', '0.0.0.0', '--port', '8000'],
                cwd=backend_dir,
                check=True
            )
        else:
            # 仮想環境を使用
            if platform.system() == 'Windows':
                python_cmd = backend_dir / 'venv' / 'Scripts' / 'python.exe'
            else:
                python_cmd = backend_dir / 'venv' / 'bin' / 'python'
            
            subprocess.run(
                [str(python_cmd), '-m', 'uvicorn', 'main:app', '--reload', '--host', '0.0.0.0', '--port', '8000'],
                cwd=backend_dir,
                check=True
            )
    except KeyboardInterrupt:
        print("\n\nサーバーを停止しました。")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print_error(f"サーバーの起動に失敗しました: {e}")
        sys.exit(1)

def main():
    """メイン処理"""
    print_header("PicoRESQ バックエンドサーバー起動")
    
    # スクリプトはscripts/ディレクトリから実行されるため、プロジェクトルートに移動
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    backend_dir = project_root / 'backend'
    
    # 依存関係の確認
    if not check_dependencies(backend_dir):
        sys.exit(1)
    
    # サーバー起動
    start_server(backend_dir)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nサーバーを停止しました。")
        sys.exit(0)
    except Exception as e:
        print_error(f"予期しないエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
