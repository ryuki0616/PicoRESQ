#!/bin/bash
# PicoRESQ 受付・クイズの同時起動（Linux用）

set -eu
set +m

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

for command_name in flock setsid; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "エラー: $command_name が必要です（Ubuntuでは util-linux に含まれます）。" >&2
        exit 1
    fi
done

# 同じ利用者・プロジェクトで統一起動スクリプトを重ねて実行しない。
read -r project_id _ < <(printf '%s' "$PROJECT_ROOT" | cksum)
lock_path="${TMPDIR:-/tmp}/picoresq-start-$(id -u)-${project_id}.lock"
exec 9>"$lock_path"
if ! flock -n 9; then
    echo "受付・クイズの同時起動スクリプトは、すでに実行中です。" >&2
    exit 1
fi

app_pids=()

cleanup() {
    # 起動したアプリのプロセスグループだけを停止する。
    trap '' INT TERM
    local app_pid
    for app_pid in "${app_pids[@]}"; do
        kill -TERM -- "-$app_pid" 2>/dev/null || true
    done
    if [ "${#app_pids[@]}" -gt 0 ]; then
        sleep 1
    fi
    for app_pid in "${app_pids[@]}"; do
        kill -KILL -- "-$app_pid" 2>/dev/null || true
        wait "$app_pid" 2>/dev/null || true
    done
    # 待機中の別プロセスと同じファイルを使うため、ロックファイルは削除しない。
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "受付とクイズを起動します（バックエンドは起動しません）。"
echo "Ctrl+C、または片方のアプリを閉じると、両方を終了します。"

# 既存スクリプトで同じPython環境を検出し、それぞれ独立したグループで起動する。
setsid bash "$SCRIPT_DIR/start_reception.sh" &
app_pids+=("$!")
setsid bash "$SCRIPT_DIR/start_frontend.sh" &
app_pids+=("$!")

exit_status=0
wait -n "${app_pids[@]}" || exit_status=$?
echo "一方のアプリが終了したため、残りのアプリも停止します。"
exit "$exit_status"
