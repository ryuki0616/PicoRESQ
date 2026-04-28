@echo off
REM PicoRESQ クイズシステム - バックエンド起動スクリプト (Windows用)

chcp 65001 >nul
setlocal enabledelayedexpansion
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM スクリプトはscripts/ディレクトリから実行されるため、プロジェクトルートに移動
cd /d "%~dp0\.."

echo.
echo ============================================================
echo PicoRESQ バックエンドサーバー起動
echo ============================================================
echo.

REM backendディレクトリに移動
cd backend

REM 依存関係の確認
if not exist "venv" (
    echo [警告] 仮想環境が見つかりません。
    echo [情報] セットアップスクリプトを実行してください: scripts\setup.bat
    exit /b 1
)

REM サーバー起動
echo [情報] バックエンドサーバーを起動します...
echo [情報] サーバーURL: http://127.0.0.1:8000
echo [情報] APIドキュメント: http://127.0.0.1:8000/docs
echo [情報] 停止するには Ctrl+C を押してください
echo.

call venv\Scripts\activate.bat
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
