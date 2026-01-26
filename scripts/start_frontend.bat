@echo off
REM PicoRESQ クイズシステム - フロントエンド起動スクリプト (Windows用)

setlocal enabledelayedexpansion

REM スクリプトはscripts/ディレクトリから実行されるため、プロジェクトルートに移動
cd /d "%~dp0\.."

echo.
echo ============================================================
echo PicoRESQ フロントエンド (Electron) 起動
echo ============================================================
echo.

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
if errorlevel 1 (
    echo [エラー] Node.jsがインストールされていません。
    echo [情報] Node.js LTS版をインストールしてください: https://nodejs.org/
    exit /b 1
)

for /f %%i in ('node --version') do set NODE_VERSION=%%i
echo [成功] Node.js !NODE_VERSION! を確認しました。

REM npmの確認
where npm >nul 2>&1
if errorlevel 1 (
    echo [エラー] npmがインストールされていません。
    echo [情報] Node.jsと一緒にインストールされるはずです。Node.jsの再インストールを確認してください。
    exit /b 1
)

REM frontendディレクトリに移動
cd frontend

REM 依存関係の確認
if not exist "node_modules" (
    echo [警告] 依存関係が見つかりません。
    echo [情報] 依存関係をインストール中...
    call npm install
    if errorlevel 1 (
        echo [エラー] 依存関係のインストールに失敗しました。
        exit /b 1
    )
    echo [成功] 依存関係のインストールが完了しました。
) else (
    echo [情報] 依存関係は既にインストールされています。
)

REM Electronアプリケーション起動
echo [情報] Electronアプリケーションを起動します...
echo [情報] 停止するには Ctrl+C を押すか、アプリケーションを閉じてください
echo.

call npm start
