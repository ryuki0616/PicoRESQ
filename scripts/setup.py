#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PicoRESQ クイズシステム セットアップスクリプト (Python版・クロスプラットフォーム)
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

def check_python_version():
    """Pythonのバージョンをチェック"""
    print_info("Pythonのバージョンを確認中...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 11):
        print_error(f"Python 3.11以上が必要です。現在のバージョン: {version.major}.{version.minor}.{version.micro}")
        return False
    print_success(f"Python {version.major}.{version.minor}.{version.micro} を確認しました。")
    return True

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

def install_backend_dependencies():
    """バックエンドの依存関係をインストール"""
    print_header("バックエンド (Python) のセットアップ")
    
    # スクリプトはscripts/ディレクトリから実行されるため、プロジェクトルートに移動
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    backend_dir = project_root / 'backend'
    requirements_file = backend_dir / 'requirements.txt'
    
    if not requirements_file.exists():
        print_error(f"requirements.txt が見つかりません: {requirements_file}")
        return False
    
    # 仮想環境の作成
    venv_dir = backend_dir / 'venv'
    if not venv_dir.exists():
        print_info("仮想環境を作成中...")
        try:
            subprocess.run(
                [sys.executable, '-m', 'venv', str(venv_dir)],
                cwd=backend_dir,
                check=True
            )
            print_success("仮想環境を作成しました。")
        except subprocess.CalledProcessError as e:
            print_error(f"仮想環境の作成に失敗しました: {e}")
            return False
    else:
        print_info("仮想環境は既に存在します。")
    
    # 依存関係のインストール
    print_info(f"依存関係をインストール中: {requirements_file}")
    
    try:
        if platform.system() == 'Windows':
            pip_cmd = str(venv_dir / 'Scripts' / 'pip.exe')
        else:
            pip_cmd = str(venv_dir / 'bin' / 'pip')
        
        cmd = [pip_cmd, 'install', '-r', str(requirements_file)]
        result = subprocess.run(
            cmd,
            cwd=backend_dir,
            check=True,
            capture_output=False
        )
        print_success("バックエンドの依存関係のインストールが完了しました。")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"依存関係のインストールに失敗しました: {e}")
        return False

def install_frontend_dependencies():
    """フロントエンドの依存関係をインストール"""
    print_header("フロントエンド (Electron) のセットアップ")
    
    # スクリプトはscripts/ディレクトリから実行されるため、プロジェクトルートに移動
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    frontend_dir = project_root / 'frontend'
    package_json = frontend_dir / 'package.json'
    
    if not package_json.exists():
        print_error(f"package.json が見つかりません: {package_json}")
        return False
    
    node_modules_dir = frontend_dir / 'node_modules'
    
    if not node_modules_dir.exists():
        print_info("依存関係をインストール中...")
        try:
            subprocess.run(
                ['npm', 'install'],
                cwd=frontend_dir,
                check=True,
                capture_output=False
            )
            print_success("フロントエンドの依存関係のインストールが完了しました。")
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"依存関係のインストールに失敗しました: {e}")
            return False
    else:
        print_info("依存関係は既にインストールされています。")
        return True

def install_reception_dependencies():
    """受付システムの依存関係をインストール"""
    print_header("受付システム (Electron) のセットアップ")
    
    # スクリプトはscripts/ディレクトリから実行されるため、プロジェクトルートに移動
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    reception_dir = project_root / 'reception'
    package_json = reception_dir / 'package.json'
    
    if not package_json.exists():
        print_error(f"package.json が見つかりません: {package_json}")
        return False
    
    node_modules_dir = reception_dir / 'node_modules'
    
    if not node_modules_dir.exists():
        print_info("依存関係をインストール中...")
        try:
            subprocess.run(
                ['npm', 'install'],
                cwd=reception_dir,
                check=True,
                capture_output=False
            )
            print_success("受付システムの依存関係のインストールが完了しました。")
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"依存関係のインストールに失敗しました: {e}")
            return False
    else:
        print_info("依存関係は既にインストールされています。")
        return True

def main():
    """メイン処理"""
    print_header("PicoRESQ クイズシステム セットアップ")
    print_warning("Dockerは使用しません（NFCリーダーが動作しない可能性があるため）")
    
    # システム情報を表示
    print_info(f"OS: {platform.system()} {platform.release()}")
    print_info(f"Python: {sys.version}")
    
    # バージョンチェック
    if not check_python_version():
        sys.exit(1)
    
    # バックエンドのセットアップ
    if not install_backend_dependencies():
        print_error("バックエンドのセットアップに失敗しました。")
        sys.exit(1)
    
    # フロントエンドのセットアップ
    if check_nodejs():
        if not install_frontend_dependencies():
            print_warning("フロントエンドのセットアップに失敗しました。")
        
        # 受付システムのセットアップ
        if not install_reception_dependencies():
            print_warning("受付システムのセットアップに失敗しました。")
    else:
        print_warning("Node.jsがインストールされていないため、フロントエンドと受付システムのセットアップをスキップします。")
    
    # 完了メッセージ
    print_header("セットアップ完了")
    print_success("すべてのセットアップが完了しました！")
    print("\n次のステップ:")
    print("0. NFCカードのみ運用（バックエンド/DBなし）: python scripts/card_only.py status")
    print("1. バックエンドを起動: python scripts/start_backend.py")
    print("2. フロントエンドを起動: python scripts/start_frontend.py")
    print("3. 受付システムを起動: python scripts/start_reception.py")
    print("\n詳細は README.md を参照してください。\n")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nセットアップが中断されました。")
        sys.exit(1)
    except Exception as e:
        print_error(f"予期しないエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
