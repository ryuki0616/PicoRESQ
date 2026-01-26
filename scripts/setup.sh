#!/bin/bash
# PicoRESQ クイズシステム セットアップスクリプト (macOS/Linux用)

set -e  # エラーが発生したら終了

# カラー出力
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

# OS 判定
OS_NAME="$(uname -s)"
IS_LINUX=false
IS_DARWIN=false
IS_WSL=false
case "$OS_NAME" in
    Linux*) IS_LINUX=true ;;
    Darwin*) IS_DARWIN=true ;;
esac
if [ "$IS_LINUX" = true ]; then
    if grep -qiE "(microsoft|wsl)" /proc/version /proc/sys/kernel/osrelease 2>/dev/null; then
        IS_WSL=true
    fi
fi

command_exists() {
    command -v "$1" &> /dev/null
}

install_linux_dependencies() {
    print_header "Linux/WSL 依存関係の確認"
    if ! command_exists apt-get; then
        print_warning "apt-get が見つかりません。Linux依存の自動インストールをスキップします。"
        return 0
    fi

    print_info "Linux/WSL のシステム依存をインストールしますか？ (y/n)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        print_warning "システム依存の自動インストールをスキップしました。"
        return 0
    fi

    local sudo_cmd=""
    if [ "$(id -u)" -ne 0 ]; then
        if command_exists sudo; then
            sudo_cmd="sudo"
        else
            print_error "sudo が見つかりません。root権限で再実行してください。"
            return 1
        fi
    fi

    print_info "apt-get を更新中..."
    $sudo_cmd apt-get update

    print_info "NFC/ビルド/GUI 依存をインストール中..."
    $sudo_cmd apt-get install -y \
        python3-venv \
        build-essential \
        pcscd \
        libpcsclite-dev \
        libusb-1.0-0-dev \
        libgtk-3-0 \
        libnss3 \
        libxss1 \
        libasound2t64 \
        libatk-bridge2.0-0 \
        libatspi2.0-0 \
        libdrm2 \
        libgbm1 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libx11-xcb1 \
        libcups2

    if [ "$IS_WSL" = true ]; then
        print_warning "WSL検出: GUIはWSLgが必要です（Windows 11推奨）。"
        print_warning "NFCリーダーはWindows側でUSBIPDのアタッチが必要です。"
    fi
}

install_nodejs_linux() {
    if command_exists node; then
        return 0
    fi
    if ! command_exists apt-get; then
        return 0
    fi

    print_warning "Node.jsがインストールされていません。"
    print_info "Node.js LTS を自動インストールしますか？ (y/n)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        print_warning "Node.js の自動インストールをスキップしました。"
        return 0
    fi

    if ! command_exists curl; then
        print_error "curl が見つかりません。Node.js の自動インストールを中止します。"
        return 1
    fi

    local sudo_cmd=""
    if [ "$(id -u)" -ne 0 ]; then
        if command_exists sudo; then
            sudo_cmd="sudo"
        else
            print_error "sudo が見つかりません。root権限で再実行してください。"
            return 1
        fi
    fi

    print_info "NodeSource から Node.js LTS をインストール中..."
    curl -fsSL https://deb.nodesource.com/setup_lts.x | $sudo_cmd -E bash -
    $sudo_cmd apt-get install -y nodejs
}

# メイン処理
print_header "PicoRESQ クイズシステム セットアップ"
print_warning "Dockerは使用しません（NFCリーダーが動作しない可能性があるため）"

# Linux/WSL 依存関係
if [ "$IS_LINUX" = true ]; then
    install_linux_dependencies
fi

# uvのインストールチェック
print_info "uvのインストールを確認中..."
if command -v uv &> /dev/null; then
    UV_VERSION=$(uv --version)
    print_success "uv $UV_VERSION を確認しました。"
    USE_UV=true
else
    print_warning "uvがインストールされていません。"
    print_info "uvをインストールしますか？ (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        print_info "uvをインストール中..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        if [ $? -eq 0 ]; then
            export PATH="$HOME/.cargo/bin:$PATH"
            if command -v uv &> /dev/null; then
                print_success "uvのインストールが完了しました。"
                USE_UV=true
            else
                print_warning "uvのインストールは完了しましたが、PATHに追加されていません。"
                print_info "pip/venvを使用して続行します..."
                USE_UV=false
            fi
        else
            print_error "uvのインストールに失敗しました。"
            print_info "pip/venvを使用して続行します..."
            USE_UV=false
        fi
    else
        print_info "pip/venvを使用して続行します..."
        USE_UV=false
    fi
fi

# Pythonのバージョンチェック
if [ "$USE_UV" = false ]; then
    print_info "Pythonのバージョンを確認中..."
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        print_error "Pythonがインストールされていません。"
        exit 1
    fi

    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
        print_error "Python 3.11以上が必要です。現在のバージョン: $PYTHON_VERSION"
        exit 1
    fi
    print_success "Python $PYTHON_VERSION を確認しました。"
else
    print_info "uvがPythonのバージョンを管理します。"
fi

# バックエンドのセットアップ
print_header "バックエンド (Python) のセットアップ"

# スクリプトはscripts/ディレクトリから実行されるため、プロジェクトルートに移動
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

cd backend

if [ "$USE_UV" = true ]; then
    # uvを使用する場合（純正機能）
    print_info "uvを使用してセットアップします..."
    
    # pyproject.tomlの確認
    if [ ! -f "pyproject.toml" ]; then
        print_error "pyproject.toml が見つかりません: backend/pyproject.toml"
        exit 1
    fi
    
    print_info "依存関係を同期中（uv sync）..."
    uv sync
    if [ $? -eq 0 ]; then
        print_success "バックエンドの依存関係のインストールが完了しました。"
        print_info "仮想環境は .venv に作成されました。"
    else
        print_error "依存関係のインストールに失敗しました。"
        exit 1
    fi
else
    # 従来のpip/venvを使用する場合
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt が見つかりません: backend/requirements.txt"
        exit 1
    fi
    
    print_info "pip/venvを使用してセットアップします..."
    
    # 仮想環境の作成（既に存在する場合はスキップ）
    if [ ! -d "venv" ]; then
        print_info "仮想環境を作成中..."
        $PYTHON_CMD -m venv venv
        if [ $? -eq 0 ]; then
            print_success "仮想環境を作成しました。"
        else
            print_error "仮想環境の作成に失敗しました。"
            exit 1
        fi
    else
        print_info "仮想環境は既に存在します。"
    fi
    
    # 仮想環境を有効化
    print_info "仮想環境を有効化中..."
    source venv/bin/activate
    
    print_info "依存関係をインストール中..."
    pip install -r requirements.txt
    if [ $? -eq 0 ]; then
        print_success "バックエンドの依存関係のインストールが完了しました。"
    else
        print_error "依存関係のインストールに失敗しました。"
        exit 1
    fi
    
    # 仮想環境を無効化
    deactivate
fi

cd "$PROJECT_ROOT"

# フロントエンドのセットアップ
print_header "フロントエンド (Electron) のセットアップ"

# Node.jsのチェック
print_info "Node.jsのインストールを確認中..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    print_success "Node.js $NODE_VERSION を確認しました。"
    SKIP_FRONTEND=false
else
    if [ "$IS_LINUX" = true ]; then
        install_nodejs_linux || true
    fi
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node --version)
        print_success "Node.js $NODE_VERSION を確認しました。"
        SKIP_FRONTEND=false
    else
        print_warning "Node.jsがインストールされていません。"
        print_warning "Node.js LTS版をインストールしてください: https://nodejs.org/"
        SKIP_FRONTEND=true
    fi
fi

if [ "$SKIP_FRONTEND" = false ]; then
    cd frontend
    
    # 依存関係の確認
    if [ ! -d "node_modules" ]; then
        print_warning "依存関係が見つかりません。"
        print_info "依存関係をインストール中..."
        npm install
        if [ $? -eq 0 ]; then
            print_success "フロントエンドの依存関係のインストールが完了しました。"
        else
            print_error "依存関係のインストールに失敗しました。"
            exit 1
        fi
    else
        print_info "依存関係は既にインストールされています。"
    fi
    
    cd "$PROJECT_ROOT"
else
    print_warning "フロントエンドのセットアップをスキップしました。"
fi

# 受付システムのセットアップ
print_header "受付システム (Electron) のセットアップ"
if [ "$SKIP_FRONTEND" = false ]; then
    cd reception
    
    # 依存関係の確認
    if [ ! -d "node_modules" ]; then
        print_warning "依存関係が見つかりません。"
        print_info "依存関係をインストール中..."
        npm install
        if [ $? -eq 0 ]; then
            print_success "受付システムの依存関係のインストールが完了しました。"
        else
            print_error "受付システムの依存関係のインストールに失敗しました。"
            exit 1
        fi
    else
        print_info "依存関係は既にインストールされています。"
    fi
    
    cd "$PROJECT_ROOT"
else
    print_warning "受付システムのセットアップをスキップしました。"
fi

# 完了メッセージ
print_header "セットアップ完了"
print_success "すべてのセットアップが完了しました！"
echo ""
echo "次のステップ:"
if [ "$USE_UV" = true ]; then
    echo "1. バックエンドを起動:"
    echo "   ./scripts/start_backend.sh"
    echo ""
    echo "   【uvの純正機能について】"
    echo "   - uv sync: 依存関係をインストール・同期"
    echo "   - uv run: 仮想環境内でコマンドを実行（自動的に仮想環境を使用）"
    echo "   - uv add <package>: 新しいパッケージを追加"
    echo "   - uv remove <package>: パッケージを削除"
else
    echo "1. バックエンドを起動:"
    echo "   ./scripts/start_backend.sh"
    echo ""
    echo "   または手動で:"
    echo "   cd backend"
    echo "   source venv/bin/activate"
    echo "   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"
fi
echo ""
echo "2. フロントエンドを起動:"
echo "   ./scripts/start_frontend.sh"
echo ""
echo "3. 受付システムを起動:"
echo "   ./scripts/start_reception.sh"
echo ""
echo "（バックエンド/DBなしでカードだけ運用する場合）"
echo "0. NFCカードのみ運用:"
echo "   ./scripts/start_card_only.sh status"
echo "   ./scripts/start_card_only.sh write --name \"山田太郎\" --address \"東京都\" --tel \"090...\" --family-count 3 --care-needed 0"
echo "   ./scripts/start_card_only.sh read"
echo ""
echo "詳細は README.md を参照してください。"
echo ""
