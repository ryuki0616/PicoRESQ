#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PicoRESQ クイズシステム - フロントエンド起動スクリプト (Python版・クロスプラットフォーム)
"""

import os
import sys
import subprocess
import platform
from pathlib import Path
from typing import Optional

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

def check_nodejs():
    """Node.jsのインストールをチェック"""
    print_info("Node.jsのインストールを確認中...")
    try:
        result = subprocess.run(
            ['node', '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()
        print_success(f"Node.js {version} を確認しました。")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("Node.jsがインストールされていません。")
        print_warning("Node.js LTS版をインストールしてください: https://nodejs.org/")
        return False

def check_npm():
    """npmのインストールをチェック"""
    print_info("npmのインストールを確認中...")
    try:
        result = subprocess.run(
            ['npm', '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()
        print_success(f"npm {version} を確認しました。")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("npmがインストールされていません。")
        print_warning("Node.jsと一緒にインストールされるはずです。Node.jsの再インストールを確認してください。")
        return False

def check_dependencies(frontend_dir):
    """依存関係の確認とインストール"""
    node_modules_dir = frontend_dir / 'node_modules'
    
    if not node_modules_dir.exists():
        print_warning("依存関係が見つかりません。")
        print_info("依存関係をインストール中...")
        
        try:
            result = subprocess.run(
                ['npm', 'install'],
                cwd=frontend_dir,
                check=True,
                capture_output=False
            )
            print_success("依存関係のインストールが完了しました。")
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"依存関係のインストールに失敗しました: {e}")
            return False
    else:
        print_info("依存関係は既にインストールされています。")
        return True

def resolve_python_path(project_root: Path) -> Optional[str]:
    """NFC CLI 用のPythonパスを解決"""
    env_python = os.environ.get("PICORESQ_PYTHON")
    if env_python:
        return env_python
    venv_python = project_root / 'backend' / 'venv' / 'bin' / 'python'
    if venv_python.exists():
        return str(venv_python)
    venv_python_win = project_root / 'backend' / 'venv' / 'Scripts' / 'python.exe'
    if venv_python_win.exists():
        return str(venv_python_win)
    for candidate in (
        project_root / 'backend' / '.venv' / 'bin' / 'python',
        project_root / 'backend' / '.venv' / 'Scripts' / 'python.exe',
    ):
        if candidate.exists():
            return str(candidate)
    return None

def start_app(frontend_dir):
    """Electronアプリケーションを起動"""
    print_info("Electronアプリケーションを起動します...")
    print_info("停止するには Ctrl+C を押すか、アプリケーションを閉じてください")
    print("")
    
    try:
        # npm startを使用してアプリケーションを起動
        subprocess.run(
            ['npm', 'start'],
            cwd=frontend_dir,
            check=True
        )
    except KeyboardInterrupt:
        print("\n\nアプリケーションを停止しました。")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print_error(f"アプリケーションの起動に失敗しました: {e}")
        sys.exit(1)

def main():
    """メイン処理"""
    print_header("PicoRESQ フロントエンド (Electron) 起動")
    
    # スクリプトはscripts/ディレクトリから実行されるため、プロジェクトルートに移動
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    frontend_dir = project_root / 'frontend'

    python_path = resolve_python_path(project_root)
    if python_path:
        os.environ["PICORESQ_PYTHON"] = python_path
        print_info(f"PICORESQ_PYTHON={python_path}")
    else:
        print_warning("PICORESQ_PYTHON が未設定です（python3 を使用します）")
    
    if not frontend_dir.exists():
        print_error(f"frontendディレクトリが見つかりません: {frontend_dir}")
        sys.exit(1)
    
    # バージョンチェック
    if not check_nodejs():
        sys.exit(1)
    
    if not check_npm():
        sys.exit(1)
    
    # 依存関係の確認
    if not check_dependencies(frontend_dir):
        sys.exit(1)
    
    # アプリケーション起動
    start_app(frontend_dir)

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
