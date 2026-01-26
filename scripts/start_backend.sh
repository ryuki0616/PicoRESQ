#!/bin/bash
# PicoRESQ クイズシステム - バックエンド起動スクリプト (macOS/Linux用)

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

print_header "PicoRESQ バックエンドサーバー起動"

# uvの確認
if command -v uv &> /dev/null; then
    USE_UV=true
else
    USE_UV=false
fi

# backendディレクトリに移動
cd backend

# 依存関係の確認
if [ "$USE_UV" = true ]; then
    print_info "依存関係を確認中..."
    uv sync
    if [ $? -eq 0 ]; then
        print_success "依存関係の確認が完了しました。"
    else
        print_error "依存関係の確認に失敗しました。"
        exit 1
    fi
else
    if [ ! -d "venv" ]; then
        print_warning "仮想環境が見つかりません。"
        print_info "セットアップスクリプトを実行してください: ./scripts/setup.sh"
        exit 1
    fi
fi

# サーバー起動
print_info "バックエンドサーバーを起動します..."
print_info "サーバーURL: http://127.0.0.1:8000"
print_info "APIドキュメント: http://127.0.0.1:8000/docs"
print_info "停止するには Ctrl+C を押してください"
echo ""

if [ "$USE_UV" = true ]; then
    uv run python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
else
    source venv/bin/activate
    python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
fi
