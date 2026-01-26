#!/bin/bash
# PicoRESQ - NFCカードのみ運用 起動スクリプト（macOS/Linux用）
#
# 使い方:
#   ./scripts/start_card_only.sh status
#   ./scripts/start_card_only.sh read
#   ./scripts/start_card_only.sh write --name "山田太郎" --address "東京都" --tel "090..." --family-count 3 --care-needed 0
#   ./scripts/start_card_only.sh write-cleared --count 2

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if command -v uv &> /dev/null && [ -f "backend/pyproject.toml" ]; then
  # すでに別の仮想環境が有効になっているとuvが警告を出すため、ここでは無効化しておく
  unset VIRTUAL_ENV
  # backend の uv 環境で実行（pyscard 等の依存を確実に拾う）
  cd backend
  uv sync
  uv run python ../scripts/card_only.py "$@"
elif [ -f "backend/venv/bin/activate" ]; then
  # pip/venv の場合
  source backend/venv/bin/activate
  python scripts/card_only.py "$@"
elif [ -f "backend/.venv/bin/activate" ]; then
  # uv が作る .venv が存在するが uv コマンドが無い場合
  source backend/.venv/bin/activate
  python scripts/card_only.py "$@"
else
  # 最後の手段（pyscard が無い可能性あり）
  python3 scripts/card_only.py "$@"
fi

