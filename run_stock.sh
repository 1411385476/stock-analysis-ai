#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: run_stock.sh <symbol>"
  exit 1
fi

SYMBOL="$1"
ROOT_DIR="/home/wgj/openclaw-finance"
PYTHON_BIN="$ROOT_DIR/venv312/bin/python"
SCRIPT_PATH="$ROOT_DIR/stock_analyzer.py"

# De-duplicate near-identical repeated requests from TUI.
# Example: "分析002739" sent twice in a short window should not rerun full analysis.
CACHE_DIR="${OPENCLAW_STOCK_CACHE_DIR:-/tmp/openclaw-stock-cache}"
CACHE_TTL_SEC="${OPENCLAW_STOCK_CACHE_TTL_SEC:-300}"
SANITIZED_SYMBOL="${SYMBOL//[^A-Za-z0-9._-]/_}"
LOCK_FILE="$CACHE_DIR/${SANITIZED_SYMBOL}.lock"
CACHE_FILE="$CACHE_DIR/${SANITIZED_SYMBOL}.out"
STAMP_FILE="$CACHE_DIR/${SANITIZED_SYMBOL}.ts"

# Fast-path defaults; can still be overridden by caller env.
export OPENCLAW_HISTORY_PROVIDERS="${OPENCLAW_HISTORY_PROVIDERS:-akshare,yfinance}"
export OPENCLAW_YF_SOCKET_TIMEOUT_SEC="${OPENCLAW_YF_SOCKET_TIMEOUT_SEC:-8}"

is_cache_fresh() {
  if [[ ! -f "$STAMP_FILE" || ! -f "$CACHE_FILE" ]]; then
    return 1
  fi

  local now ts
  now="$(date +%s)"
  ts="$(cat "$STAMP_FILE" 2>/dev/null || echo 0)"

  if [[ ! "$ts" =~ ^[0-9]+$ ]]; then
    return 1
  fi

  (( now - ts <= CACHE_TTL_SEC ))
}

run_analysis() {
  timeout 90s "$PYTHON_BIN" "$SCRIPT_PATH" "$SYMBOL" --no-llm --backtest
}

mkdir -p "$CACHE_DIR"
if command -v flock >/dev/null 2>&1; then
  exec 200>"$LOCK_FILE"
  flock -x 200
else
  LOCK_DIR_FALLBACK="$CACHE_DIR/${SANITIZED_SYMBOL}.lockdir"
  while ! mkdir "$LOCK_DIR_FALLBACK" 2>/dev/null; do
    sleep 0.1
  done
  trap 'rmdir "$LOCK_DIR_FALLBACK" >/dev/null 2>&1 || true' EXIT
fi

if is_cache_fresh; then
  cat "$CACHE_FILE"
  exit 0
fi

TMP_FILE="$(mktemp "$CACHE_DIR/${SANITIZED_SYMBOL}.XXXXXX.out")"

cd "$ROOT_DIR"
set +e
run_analysis | tee "$TMP_FILE"
STATUS="${PIPESTATUS[0]}"
set -e

if [[ "$STATUS" -eq 0 ]]; then
  mv "$TMP_FILE" "$CACHE_FILE"
  date +%s >"$STAMP_FILE"
else
  rm -f "$TMP_FILE"
fi

exit "$STATUS"
