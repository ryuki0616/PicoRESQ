# PicoRESQ クイズシステム

NFC防災クイズのための**オフライン運用**を前提としたシステムです。受付システム（PicoCERA）で作成したNFCカードを使用し、カードの物理メモリにクリア情報を記録します。バックエンドはコードを保持しますが、運用時は起動しません。

## 機能概要

- **NFCカード検知**: カードをかざすと自動的にクイズが開始
- **5つの試練**: 防災に関する5つのクイズブース
- **進捗管理**: NFCカードの物理メモリにクリア数を記録
- **オフライン運用**: サーバーなしでNFCカードの読み書きが可能

## システム要件

- **OS**: Windows (推奨), macOS, Linux
- **Runtime**:
  - Python 3.11+
  - Node.js (LTS)
- **Hardware**:
  - NFCリーダー (Sony RC-S380等 / PaSoRi)
  - NFCカード（FeliCa、Mifare Classic、Mifare Ultralight対応）

## Dockerについて

NFCリーダーが動作しない可能性があるため、**Dockerは使用しません**。  
セットアップ・起動は本README内の手順を使用してください。

## クイックスタート

1. 環境診断（依存関係の自動判定）
```bash
python scripts/doctor.py
```

2. セットアップ（自動）
```bash
python scripts/setup.py
```

3. 起動
```bash
./scripts/start_reception.sh   # macOS/Linux
scripts\\start_reception.bat   # Windows
```
```bash
./scripts/start_frontend.sh    # macOS/Linux
scripts\\start_frontend.bat    # Windows
```

## ディレクトリ構造

```
PicoRESQ/
├── README.md              # プロジェクトのメインドキュメント
├── rules.md               # コーディング規約
├── .gitignore             # Git除外設定
├── scripts/               # スクリプト
│   ├── setup.sh           # セットアップスクリプト (macOS/Linux用)
│   ├── setup.bat          # セットアップスクリプト (Windows用)
│   ├── setup.py           # セットアップスクリプト (Python版・クロスプラットフォーム)
│   ├── card_only.py       # NFCカードのみ運用（サーバー不要）
│   ├── start_card_only.sh # NFCカードのみ運用 起動 (macOS/Linux用)
│   ├── start_card_only.bat # NFCカードのみ運用 起動 (Windows用)
│   ├── start_backend.sh   # バックエンド起動スクリプト (macOS/Linux用)
│   ├── start_backend.bat  # バックエンド起動スクリプト (Windows用)
│   ├── start_backend.py   # バックエンド起動スクリプト (Python版)
│   ├── start_frontend.sh  # フロントエンド起動スクリプト (macOS/Linux用)
│   ├── start_frontend.bat # フロントエンド起動スクリプト (Windows用)
│   ├── start_frontend.py  # フロントエンド起動スクリプト (Python版)
│   ├── start_reception.sh # 受付システム起動スクリプト (macOS/Linux用)
│   ├── start_reception.bat # 受付システム起動スクリプト (Windows用)
│   └── start_reception.py # 受付システム起動スクリプト (Python版)
├── backend/               # Python/FastAPI バックエンド
│   ├── main.py            # FastAPIサーバー + クイズAPI
│   ├── nfc_reader.py      # NFCリーダー（カード読み取り）
│   ├── nfc_writer.py      # NFC書き込み機能
│   ├── quiz_data.json     # クイズ問題データ（JSON形式）
│   ├── quiz_data.py       # クイズデータ読み込みユーティリティ
│   ├── pyproject.toml     # Python Project Config (uv使用時)
│   └── requirements.txt   # Python Dependencies (pip/venv使用時)
├── frontend/              # Electron フロントエンド（クイズシステム）
    ├── main.js            # Electron メインプロセス
    ├── renderer.js        # レンダラープロセス（クイズロジック + API通信）
    ├── index.html         # クイズUI
    ├── style.css          # スタイル
    └── package.json       # Electron 依存関係
└── reception/            # Electron フロントエンド（受付システム）
    ├── main.js            # Electron メインプロセス
    ├── renderer.js        # レンダラープロセス（受付ロジック + API通信）
    ├── index.html         # 受付UI
    ├── style.css          # スタイル
    └── package.json       # Electron 依存関係
```

## ドキュメント

- ドキュメント一覧: `docs/README.md`
- 要件定義: `requirements.md`
- 一般向け説明: `public_overview.md`
- コーディング規約: `rules.md`

## 生成物（コミットしないもの）と運用方針

このプロジェクトは、セットアップや実行により以下の**生成物**が作られます。これらは `.gitignore` で除外し、基本的に**コミットしません**。

- **Python仮想環境**: `backend/.venv/`（uv） / `backend/venv/`（pip/venv）
- **Node依存**: `frontend/node_modules/`, `reception/node_modules/`
- **SQLite DB**: `*.db`（例: `backend/pico_resq.db`）

困ったときの整理（例）:

```bash
# Python依存を作り直す（uv）
cd backend
uv sync

# Node依存を作り直す
cd ../frontend && npm install
cd ../reception && npm install
```

## セットアップ

### 自動セットアップ（推奨）

セットアップスクリプトを使用すると、バックエンド、フロントエンド、受付システムの依存関係を自動的にインストールできます。

#### macOS / Linux

```bash
# シェルスクリプトを使用
./scripts/setup.sh

# または Python スクリプトを使用
python3 scripts/setup.py
```

### 環境診断（依存関係の自動判定）

```bash
python scripts/doctor.py
```

**注意**: 
- `setup.sh`と`setup.bat`は`uv`（高速なPythonパッケージマネージャー）の使用をサポートしています。`uv`がインストールされていない場合、自動的にインストールを提案します。
- セットアップスクリプトは、バックエンド、フロントエンド、受付システムのすべての依存関係を自動的にインストールします。

#### Windows

```cmd
REM バッチファイルを使用
scripts\setup.bat

REM または Python スクリプトを使用
python scripts\setup.py
```

### 手動セットアップ

#### バックエンドのセットアップ

**uvを使用する場合（推奨）**:

```bash
cd backend
uv sync
```

## オフライン運用（バックエンド非起動）

受付システムとクイズシステムは、**サーバーを起動せず**に動かせます。  
NFC読み書きは `scripts/nfc_cli.py` を内部で呼び出して行います。

### 1) NFC依存の準備（必須）
NFC読み書きには `pyscard` が必要です。バックエンドの依存だけ入れておけばOKです。

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

Windowsの場合:

```cmd
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**補足**: 起動スクリプトは `backend/venv`、`backend/.venv` の順に自動検出します。

独自のPythonを使う場合は `PICORESQ_PYTHON` を指定してください。

```bash
export PICORESQ_PYTHON="/path/to/python"  # macOS/Linux
```

```cmd
set PICORESQ_PYTHON=C:\path\to\python.exe  # Windows
```

### 2) 受付システムの起動（NFC読み取り/書き込み）
```bash
./scripts/start_reception.sh   # macOS/Linux
```
```cmd
scripts\start_reception.bat   # Windows
```

### 3) クイズシステムの起動（オフライン）
```bash
./scripts/start_frontend.sh    # macOS/Linux
```
```cmd
scripts\start_frontend.bat    # Windows
```

### 4) クイズ結果ログ
クイズの正解ログは以下に保存されます（JSON Lines形式）。

```
PicoRESQ/quiz_logs/YYYY-MM-DD.jsonl
```

### 読み取りエラーとクイズ進捗

- 一時的な通信失敗は「未受付」「未クリア」と区別し、カードを置いたまま再試行します。
  「未受付」は、受付情報を正常に読み取った結果、氏名が未登録だった場合に表示します。
- 受付とクイズは、カードの受付ヘッダーにある5ブース分のクリアフラグを共通で参照します。
  両画面のクリア数は、このフラグのうちクリア済みの数です。
- クイズは、クリア情報の書き込みと読み戻しによる確認が成功してからクリアを表示します。
  保存・確認に失敗した場合は、カードを置いたまま、もう一度回答してください。
- 既存の進捗が読み取れない場合は更新を中止し、過去のクリア情報を上書きしません。
- 受付・クイズが呼び出すNFC CLIは、リーダー操作をアプリ間で直列化します。
  RC-S300ではT=1を使い、接続終了時にカードの電源を落とさず次の読み取りにつなげます。

**従来のpip/venvを使用する場合**:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# または
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

**重要**: 受付システムを使用する場合、`sqlalchemy`と`pydantic`が必要です。これらは`requirements.txt`と`pyproject.toml`に含まれています。

## バックエンド（開発/保守用）

運用時はバックエンドを起動しません。開発・保守でAPIが必要な場合のみ起動してください。

```bash
./scripts/start_backend.sh
```

## NFCカードのみ運用（バックエンド/DBなし）

バックエンド（FastAPI）やデータベースを起動せずに、NFCカードにだけデータを保存したい場合は
`scripts/card_only.py` を使用してください。

推奨（起動ラッパー）:

```bash
./scripts/start_card_only.sh status
./scripts/start_card_only.sh read
```

### 1) リーダー/カード検知確認

```bash
python3 scripts/card_only.py status
```

### 2) 受付データの書き込み（カードのみ）

```bash
python3 scripts/card_only.py write --name "山田太郎" --address "東京都" --tel "09012345678" --family-count 3 --care-needed 0
```

JSONファイルから書く場合:

```bash
python3 scripts/card_only.py write --json ./resident.json
```

### 3) 読み取り（カードのみ）

```bash
python3 scripts/card_only.py read
```

### 4) クイズ進捗（クリア数）の書き込み（カードのみ）

```bash
python3 scripts/card_only.py write-cleared --count 2
```

## 起動の順序（オフライン）

バックエンドは起動せず、**受付 → クイズ**の順で起動します（どちらからでも動きます）。

## 使い方

### 受付システム

受付システムはPicoCERAの実装を使用し、**NFCカードに直接**避難者情報を書き込みます。

1. 受付システム（Electron）を起動
2. **新規登録（書き込み）タブ**:
   - 避難者情報を入力（氏名、アレルギー、配慮項目など）
   - 「カードに書き込む」ボタンをクリック
   - NFCカードをリーダーにかざす
   - カードへの書き込み完了
3. **受付（読み取り）タブ**:
   - 登録済みのNFCカードをリーダーにかざす
   - カード内の避難者情報を表示
   - 受付完了とカード情報が表示される

### クイズシステム（ユーザー画面）

1. クイズシステム（Electron）を起動
2. NFCカードをリーダーにかざす
3. クイズが開始される
4. 正解すると、カードにクリア数が記録される
5. 5つすべてクリアすると、認定証が表示される

### 管理者画面

**重要**: 管理者画面にアクセスするには、管理者カードが必要です。

1. 管理者カードをリーダーにかざす
2. ホーム画面の左上に「⚙️」ボタンが表示される
3. 「⚙️」ボタンをクリックして管理者画面に入る
4. 管理者画面で試練（ブース）1-5から選択
5. 選択した試練が画面に表示される
6. 「選択を解除」ボタンで選択を解除可能
7. 「ユーザー画面に切り替え」ボタンで通常画面に戻る

**管理者画面の機能**:
- 試練（ブース）番号の選択
- 選択中の試練の表示
- 選択の解除
- ユーザー画面との切り替え

**管理者カードの作成**:

管理者カードを作成するには、`create_admin_card.py`スクリプトを使用します：

**重要**: 仮想環境を有効化してから実行してください。

**uvを使用する場合（推奨）**:
```bash
cd backend
uv run python create_admin_card.py
```

**仮想環境を使用する場合**:
```bash
cd backend
source venv/bin/activate  # macOS/Linux
# または
venv\Scripts\activate  # Windows
python create_admin_card.py
```

スクリプトを実行すると、以下の操作が可能です：
1. **管理者カードを追加**: NFCカードをかざして管理者カードとして登録
2. **管理者カードを削除**: NFCカードをかざして管理者カードから削除
3. **登録済み管理者カードの一覧表示**: 現在登録されている管理者カードのリストを表示

管理者カードの情報は`backend/admin_cards.json`に保存されます。

## NFCリーダーの接続確認

NFCリーダーが正しく接続されているか確認するには、以下のいずれかの方法を使用できます：

### 方法1: 直接確認（推奨）

バックエンド不要でNFCリーダーを確認できます：

```bash
./backend/venv/bin/python scripts/nfc_cli.py detect
```
```cmd
backend\venv\Scripts\python.exe scripts\nfc_cli.py detect
```

**確認内容**:
- NFCリーダーの検出状態
- 現在検知中のカード（あれば）

### 方法2: 直接確認（macOS専用）

バックエンドサーバーを起動せずに、直接NFCリーダーを確認し、macOSのポップアップで結果を表示：

```bash
python3 scripts/check_nfc_direct.py
```

**特徴**:
- バックエンドサーバーが起動していなくても動作
- macOSのポップアップダイアログで結果を表示
- リーダーの検出状態と詳細を表示

**注意**: `check_nfc_direct.py`はmacOSでのみ動作します（`osascript`を使用）。

## 注意事項

- 受付システム（PicoCERA）で作成したカードを使用できます
- カードのシステム領域は一切変更しません
- 受付システムのデータ領域とは完全に分離された領域を使用します
