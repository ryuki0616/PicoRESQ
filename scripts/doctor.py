#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PicoRESQ 環境診断スクリプト（依存関係の自動判定）
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str) -> None:
    """ヘッダーを表示"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(text: str) -> None:
    """成功メッセージを表示"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text: str) -> None:
    """エラーメッセージを表示"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text: str) -> None:
    """警告メッセージを表示"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_info(text: str) -> None:
    """情報メッセージを表示"""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def find_backend_python(backend_dir: Path) -> Path | None:
    """バックエンドの仮想環境Pythonを探索する"""
    candidates = [
        backend_dir / '.venv' / 'bin' / 'python',
        backend_dir / '.venv' / 'Scripts' / 'python.exe',
        backend_dir / 'venv' / 'bin' / 'python',
        backend_dir / 'venv' / 'Scripts' / 'python.exe',
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def check_python_module(python_path: Path, module: str) -> bool:
    """指定Pythonでモジュールがimportできるか確認する"""
    try:
        result = subprocess.run(
            [str(python_path), '-c', f'import {module}'],
            capture_output=True,
            check=False,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_command(name: str) -> bool:
    """コマンドが存在するかを確認する"""
    return shutil.which(name) is not None


def main() -> int:
    """メイン処理"""
    print_header("PicoRESQ 環境診断")

    project_root = Path(__file__).resolve().parent.parent
    backend_dir = project_root / 'backend'
    frontend_dir = project_root / 'frontend'
    reception_dir = project_root / 'reception'

    print_info(f"OS: {platform.system()} {platform.release()}")
    print_info(f"Python: {sys.version.split()[0]}")
    print_info(f"Project: {project_root}")

    issues: list[str] = []

    # Python バージョン
    if sys.version_info < (3, 11):
        print_error("Python 3.11以上が必要です")
        issues.append("Python 3.11以上が必要です")
    else:
        print_success("Python 3.11以上を確認しました")

    # uv
    if check_command('uv'):
        print_success("uv を検出しました")
    else:
        print_warning("uv が見つかりません（任意）")

    # Node.js / npm
    node_ok = check_command('node')
    npm_ok = check_command('npm')
    if node_ok:
        print_success("Node.js を検出しました")
    else:
        print_warning("Node.js が見つかりません（フロント起動に必要）")
        issues.append("Node.js が未インストールです")
    if npm_ok:
        print_success("npm を検出しました")
    else:
        print_warning("npm が見つかりません（依存関係のインストールに必要）")
        issues.append("npm が未インストールです")

    # backend 依存（pyscard）
    backend_python = find_backend_python(backend_dir)
    if backend_python:
        if check_python_module(backend_python, 'smartcard'):
            print_success("pyscard（smartcard）を検出しました")
        else:
            print_warning("pyscard がバックエンド環境に見つかりません")
            issues.append("pyscard が未インストールです")
    else:
        print_warning("バックエンドの仮想環境が見つかりません")

    # node_modules
    if (frontend_dir / 'node_modules').exists():
        print_success("frontend/node_modules を検出しました")
    else:
        print_warning("frontend/node_modules が見つかりません")
        issues.append("frontend の依存関係が未インストールです")

    if (reception_dir / 'node_modules').exists():
        print_success("reception/node_modules を検出しました")
    else:
        print_warning("reception/node_modules が見つかりません")
        issues.append("reception の依存関係が未インストールです")

    print_header("推奨アクション")
    if issues:
        print_warning("未解決の項目があります")
        for item in issues:
            print_warning(f"- {item}")
    else:
        print_success("必須項目は満たされています")

    print_info("まずは自動セットアップを実行してください")
    print("  python scripts/setup.py")

    if not check_command('node') or not check_command('npm'):
        print_info("Node.js LTS の導入: https://nodejs.org/")

    if backend_python is None:
        print_info("バックエンド仮想環境作成（pip）")
        print("  cd backend")
        print("  python -m venv venv")
        print("  venv\\Scripts\\activate  # Windows")
        print("  source venv/bin/activate  # macOS/Linux")
        print("  pip install -r requirements.txt")

    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
