# Windowsセットアップ手順（setup.bat準拠）

この手順は `scripts/setup.bat` の内容に沿って、Windows環境での準備をコマンド付きで整理したものです。

## 必要な環境

- **OS**: Windows (推奨)
- **Runtime**:
  - Python 3.11+
  - Node.js (LTS、フロントエンド利用時)
- **Hardware**:
  - NFCリーダー (Sony RC-S380等 / PaSoRi)
  - NFCカード（FeliCa、Mifare Classic、Mifare Ultralight対応）

## 前提

- Dockerは使用しません（NFCリーダーの動作問題を避けるため）
- Python 3.11以上が必要です
- フロントエンドを使う場合は Node.js LTS が必要です

## 自動セットアップ（推奨）

プロジェクトルートから実行します。

```bat
cd /d C:\path\to\PicoRESQ
scripts\setup.bat
```

## 手動セットアップ（スクリプトと同等）

### 1. Pythonの確認

```bat
python --version
```

### 2. バックエンドのセットアップ

**uvを使用する場合（推奨）**:

```bat
cd backend
uv sync
cd ..
```

補足:
- `uv`がインストールされている場合、自動的に使用されます
- 仮想環境は `backend\.venv` に作成されます
- `backend\pyproject.toml` が必要です

**pip/venvを使用する場合**:

```bat
cd backend
python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
call deactivate.bat
cd ..
```

補足:
- `backend\venv` が既にある場合は作成をスキップできます
- `backend\requirements.txt` が必要です

### 3. フロントエンドのセットアップ（Node.jsがある場合のみ）

```bat
node --version
cd frontend
npm install
cd ..
```

補足:
- `frontend\node_modules` が既にある場合は `npm install` をスキップできます
- Node.js がない場合はフロントエンドはスキップしてください

### 4. 受付システムのセットアップ（Node.jsがある場合のみ）

```bat
cd reception
npm install
cd ..
```

補足:
- `reception\node_modules` が既にある場合は `npm install` をスキップできます
- Node.js がない場合は受付システムはスキップしてください

## 次のステップ

```bat
scripts\start_card_only.bat status
scripts\start_backend.bat
scripts\start_frontend.bat
scripts\start_reception.bat
```
