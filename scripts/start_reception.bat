@echo off
REM PicoRESQ 受付システム - Electron起動スクリプト (Windows用)

chcp 65001 >nul
setlocal enabledelayedexpansion
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo.
echo ============================================================
echo PicoRESQ 受付システム (Electron) 起動
echo ============================================================
echo.
echo [情報] このシステムはPicoCERAの受付システムを使用しています。
echo [情報] NFCカードの読み書きはローカルで行います（バックエンド不要）。
echo.

REM スクリプトはscripts/ディレクトリから実行されるため、プロジェクトルートに移動
cd /d "%~dp0\.."

REM NFC CLI 用のPythonを指定（未設定なら backend\venv を優先）
if "%PICORESQ_PYTHON%"=="" (
    if exist "backend\venv\Scripts\python.exe" (
        set "PICORESQ_PYTHON=%cd%\backend\venv\Scripts\python.exe"
    ) else if exist "backend\venv\bin\python" (
        set "PICORESQ_PYTHON=%cd%\backend\venv\bin\python"
    )
)
if not "%PICORESQ_PYTHON%"=="" (
    echo [情報] PICORESQ_PYTHON=%PICORESQ_PYTHON%
) else (
    echo [警告] PICORESQ_PYTHON が未設定です（python3 を使用します）
)

REM Node.jsの確認
where node >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [エラー] Node.jsがインストールされていません。
    echo Node.js LTS版をインストールしてください: https://nodejs.org/
    pause
    exit /b 1
)

node --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "tokens=*" %%i in ('node --version') do set NODE_VERSION=%%i
    echo [成功] Node.js %NODE_VERSION% を確認しました。
)

REM npmの確認
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [エラー] npmがインストールされていません。
    echo Node.jsと一緒にインストールされるはずです。Node.jsの再インストールを確認してください。
    pause
    exit /b 1
)

REM receptionディレクトリに移動
cd reception

REM 依存関係の確認
if not exist "node_modules" (
    echo [警告] 依存関係が見つかりません。
    echo [情報] 依存関係をインストール中...
    call npm install
    if %ERRORLEVEL% EQU 0 (
        echo [成功] 依存関係のインストールが完了しました。
    ) else (
        echo [エラー] 依存関係のインストールに失敗しました。
        pause
        exit /b 1
    )
) else (
    echo [情報] 依存関係は既にインストールされています。
)

REM Electronアプリケーション起動
echo [情報] 受付システム (Electron) を起動します...
echo [情報] 停止するにはアプリケーションを閉じてください
echo.

call npm start

pause
