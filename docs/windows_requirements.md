# Windows環境での必要要件と追加モジュール一覧

この一覧は、リポジトリ内の`README.md`/`docs/setup_windows.md`/各`package.json`/`backend/requirements.txt`に基づき、Windowsの未構築環境を想定して整理しています。

## 必要環境（Windows未構築環境の前提）

- **OS**: Windows
- **Runtime**:
  - **Python**: 3.11以上
  - **Node.js**: LTS（フロントエンド/受付システムを動かす場合）
  - **npm**: Node.js同梱
- **Hardware**:
  - **NFCリーダー**: Sony RC-S380 等（PaSoRi）
  - **NFCカード**: FeliCa / Mifare Classic / Mifare Ultralight

## 追加モジュール（Python: バックエンド/NFC）

`backend/requirements.txt` より

- `fastapi>=0.100.0`
- `uvicorn[standard]>=0.20.0`
- `sqlalchemy>=2.0.0`
- `pydantic>=2.0.0`
- `pyscard>=2.0.0`
- `websockets>=11.0`

## 追加モジュール（Node.js: Electronフロントエンド/受付）

`frontend/package.json` / `reception/package.json` より

- `electron@^28.0.0`

## 参考インストールコマンド（Windows）

- Python依存（uvを使用する場合・推奨）:

```bat
cd backend
uv sync
```

- Python依存（pip/venvを使用する場合）:

```bat
cd backend
python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
call deactivate.bat
```

- Electron依存（フロントエンド/受付）:

```bat
cd frontend
npm install

cd ..\reception
npm install
```

## Windows未構築環境からの全インストール手順（コマンド例）

以下はWindowsに何も入っていない想定で、**インストールからプロジェクト依存の導入まで**を一括で実行するためのコマンド例です。  
ネットワーク接続が必要です。

### 1. 事前ツールのインストール（winget）

```bat
REM Python 3.11 (or later)
winget install -e --id Python.Python.3.11

REM Node.js LTS (includes npm)
winget install -e --id OpenJS.NodeJS.LTS
```

### 2. Python依存のセットアップ

**uvを使用する場合（推奨）**:

```bat
cd /d C:\path\to\PicoRESQ\backend
uv sync
```

**pip/venvを使用する場合**:

```bat
cd /d C:\path\to\PicoRESQ\backend
python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
call deactivate.bat
```

### 3. Electron依存のセットアップ（フロントエンド/受付）

```bat
cd /d C:\path\to\PicoRESQ\frontend
npm install

cd ..\reception
npm install
```

### 4. まとめて自動セットアップ（代替）

```bat
cd /d C:\path\to\PicoRESQ
scripts\setup.bat
```
