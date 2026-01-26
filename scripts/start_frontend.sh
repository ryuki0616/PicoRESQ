#!/bin/bash
# PicoRESQ クイズシステム - フロントエンド起動スクリプト (macOS/Linux用)

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

# スクリプトはscripts/ディレクトリから実行されるため、プロジェクトルートに移動
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

print_header "PicoRESQ フロントエンド (Electron) 起動"

# NFC CLI 用のPythonを指定（未設定なら backend/venv を優先）
if [ -z "$PICORESQ_PYTHON" ]; then
    if [ -x "$PROJECT_ROOT/backend/venv/bin/python" ]; then
        export PICORESQ_PYTHON="$PROJECT_ROOT/backend/venv/bin/python"
    elif [ -x "$PROJECT_ROOT/backend/venv/Scripts/python.exe" ]; then
        export PICORESQ_PYTHON="$PROJECT_ROOT/backend/venv/Scripts/python.exe"
    fi
fi
if [ -n "$PICORESQ_PYTHON" ]; then
    print_info "PICORESQ_PYTHON=$PICORESQ_PYTHON"
else
    print_warning "PICORESQ_PYTHON が未設定です（python3 を使用します）"
fi

# Node.jsの確認
if ! command -v node &> /dev/null; then
    print_error "Node.jsがインストールされていません。"
    print_info "Node.js LTS版をインストールしてください: https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node --version)
print_success "Node.js $NODE_VERSION を確認しました。"

# npmの確認
if ! command -v npm &> /dev/null; then
    print_error "npmがインストールされていません。"
    print_info "Node.jsと一緒にインストールされるはずです。Node.jsの再インストールを確認してください。"
    exit 1
fi

# frontendディレクトリに移動
cd frontend

# 依存関係の確認
if [ ! -d "node_modules" ]; then
    print_warning "依存関係が見つかりません。"
    print_info "依存関係をインストール中..."
    npm install
    if [ $? -eq 0 ]; then
        print_success "依存関係のインストールが完了しました。"
    else
        print_error "依存関係のインストールに失敗しました。"
        exit 1
    fi
else
    print_info "依存関係は既にインストールされています。"
fi

# Electronアプリケーション起動
print_info "Electronアプリケーションを起動します..."
print_info "停止するには Ctrl+C を押すか、アプリケーションを閉じてください"
echo ""

npm start
