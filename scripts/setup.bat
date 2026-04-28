@echo off
REM PicoRESQ クイズシステム セットアップスクリプト (Windows用)

chcp 65001 >nul
setlocal enabledelayedexpansion
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM スクリプトはscripts/ディレクトリから実行されるため、プロジェクトルートに移動
cd /d "%~dp0\.."

echo.
echo ============================================================
echo PicoRESQ クイズシステム セットアップ
echo ============================================================
echo.
echo [注意] Dockerは使用しません（NFCリーダーが動作しない可能性があるため）
echo.

REM Pythonのバージョンチェック
echo [情報] Pythonのバージョンを確認中...
python --version >nul 2>&1
if errorlevel 1 (
    echo [エラー] Pythonがインストールされていません。
    echo Python 3.11以上をインストールしてください: https://www.python.org/
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [成功] Python %PYTHON_VERSION% を確認しました。

REM バックエンドのセットアップ
echo.
echo ============================================================
echo バックエンド (Python) のセットアップ
echo ============================================================
echo.

REM uvの確認
where uv >nul 2>&1
if %errorlevel%==0 (
    echo [情報] uvがインストールされています。uvを使用してセットアップします。
    cd backend
    
    REM pyproject.tomlの確認
    if not exist "pyproject.toml" (
        echo [エラー] pyproject.toml が見つかりません: backend\pyproject.toml
        cd ..
        exit /b 1
    )
    
    echo [情報] 依存関係を同期中（uv sync）...
    uv sync
    if errorlevel 1 (
        echo [エラー] 依存関係のインストールに失敗しました。
        cd ..
        exit /b 1
    )
    cd ..
    echo [成功] バックエンドの依存関係のインストールが完了しました。
    echo [情報] 仮想環境は .venv に作成されました。
) else (
    echo [情報] uvがインストールされていません。pip/venvを使用します。
    
    if not exist "backend\requirements.txt" (
        echo [エラー] requirements.txt が見つかりません: backend\requirements.txt
        exit /b 1
    )
    
    REM 仮想環境の作成（既に存在する場合はスキップ）
    if not exist "backend\venv" (
        echo [情報] 仮想環境を作成中...
        cd backend
        python -m venv venv
        if errorlevel 1 (
            echo [エラー] 仮想環境の作成に失敗しました。
            cd ..
            exit /b 1
        )
        cd ..
        echo [成功] 仮想環境を作成しました。
    ) else (
        echo [情報] 仮想環境は既に存在します。
    )
    
    echo [情報] 依存関係をインストール中...
    cd backend
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [エラー] 依存関係のインストールに失敗しました。
        cd ..
        exit /b 1
    )
    call deactivate.bat
    cd ..
    echo [成功] バックエンドの依存関係のインストールが完了しました。
)

REM フロントエンドのセットアップ
echo.
echo ============================================================
echo フロントエンド (Electron) のセットアップ
echo ============================================================
echo.

REM Node.jsのチェック
echo [情報] Node.jsのインストールを確認中...
node --version >nul 2>&1
if errorlevel 1 (
    echo [警告] Node.jsがインストールされていません。
    echo [警告] Node.js LTS版をインストールしてください: https://nodejs.org/
    set SKIP_FRONTEND=true
) else (
    for /f %%i in ('node --version') do set NODE_VERSION=%%i
    echo [成功] Node.js !NODE_VERSION! を確認しました。
    set SKIP_FRONTEND=false
)

if "!SKIP_FRONTEND!"=="false" (
    cd frontend
    
    REM 依存関係の確認
    if not exist "node_modules" (
        echo [警告] 依存関係が見つかりません。
        echo [情報] 依存関係をインストール中...
        call npm install
        if errorlevel 1 (
            echo [エラー] 依存関係のインストールに失敗しました。
            cd ..
            exit /b 1
        )
        echo [成功] フロントエンドの依存関係のインストールが完了しました。
    ) else (
        echo [情報] 依存関係は既にインストールされています。
    )
    
    cd ..
    
    REM 受付システムのセットアップ
    echo.
    echo ============================================================
    echo 受付システム (Electron) のセットアップ
    echo ============================================================
    echo.
    
    cd reception
    
    REM 依存関係の確認
    if not exist "node_modules" (
        echo [警告] 依存関係が見つかりません。
        echo [情報] 依存関係をインストール中...
        call npm install
        if errorlevel 1 (
            echo [エラー] 依存関係のインストールに失敗しました。
            cd ..
            exit /b 1
        )
        echo [成功] 受付システムの依存関係のインストールが完了しました。
    ) else (
        echo [情報] 依存関係は既にインストールされています。
    )
    
    cd ..
) else (
    echo [警告] フロントエンドのセットアップをスキップしました。
    echo [警告] 受付システムのセットアップをスキップしました。
)

REM 完了メッセージ
echo.
echo ============================================================
echo セットアップ完了
echo ============================================================
echo.
echo [成功] すべてのセットアップが完了しました！
echo.
echo 次のステップ:
echo 0. NFCカードのみ運用（バックエンド/DBなし）: scripts\start_card_only.bat status
echo 1. バックエンドを起動: scripts\start_backend.bat
echo 2. フロントエンドを起動: scripts\start_frontend.bat
echo 3. 受付システムを起動: scripts\start_reception.bat
echo.
echo 詳細は README.md を参照してください。
echo.

pause
