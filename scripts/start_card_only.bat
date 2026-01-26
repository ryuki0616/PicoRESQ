@echo off
REM PicoRESQ - NFCカードのみ運用 起動スクリプト（Windows用）
REM
REM 使い方:
REM   scripts\start_card_only.bat status
REM   scripts\start_card_only.bat read
REM   scripts\start_card_only.bat write --name "山田太郎" --address "東京都" --tel "090..." --family-count 3 --care-needed 0
REM   scripts\start_card_only.bat write-cleared --count 2

cd /d "%~dp0\.."
if exist "backend\.venv\Scripts\python.exe" (
  cd backend
  uv sync
  uv run python ..\scripts\card_only.py %*
  exit /b %errorlevel%
)

if exist "backend\venv\Scripts\python.exe" (
  call backend\venv\Scripts\activate.bat
  python scripts\card_only.py %*
  exit /b %errorlevel%
)

python scripts\card_only.py %*

