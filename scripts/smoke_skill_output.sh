#!/usr/bin/env bash
set -euo pipefail

STRICT=0
if [[ "${1:-}" == "--strict" ]]; then
  STRICT=1
  shift
fi

if [[ "${1:-}" == "" ]]; then
  INPUT="$(cat)"
else
  if [[ ! -f "$1" ]]; then
    echo "[FAIL] output file not found: $1"
    exit 1
  fi
  INPUT="$(cat "$1")"
fi

if [[ -z "${INPUT//[[:space:]]/}" ]]; then
  echo "[FAIL] empty output"
  exit 1
fi

errors=()
warnings=()

contains() {
  local pattern="$1"
  grep -qiE "$pattern" <<<"$INPUT"
}

if contains 'NO_REPLY'; then
  errors+=("contains NO_REPLY")
fi

if contains 'Pre-compaction memory flush|Store durable memories now|Current time:'; then
  errors+=("contains memory-flush maintenance prompt")
fi

if ! contains '/home/wgj/openclaw-finance/charts/[^[:space:]]+\.png'; then
  errors+=("missing chart path under /home/wgj/openclaw-finance/charts/")
fi

if contains '^Here is the analysis report'; then
  warnings+=("contains English opener")
fi

title_count="$( (grep -Eo '[0-9]{6}[[:space:]]+分析报告' <<<"$INPUT" || true) | wc -l | tr -d ' ' )"
if [[ "${title_count}" -gt 1 ]]; then
  warnings+=("duplicate title '<code> 分析报告'")
fi

if ! contains '仅供研究，不构成投资建议'; then
  warnings+=("missing risk disclaimer")
fi

if [[ "${#errors[@]}" -gt 0 ]]; then
  echo "[FAIL] skill output smoke check failed:"
  for item in "${errors[@]}"; do
    echo "  - ${item}"
  done
  if [[ "${#warnings[@]}" -gt 0 ]]; then
    echo "[WARN] additional findings:"
    for item in "${warnings[@]}"; do
      echo "  - ${item}"
    done
  fi
  exit 1
fi

if [[ "${#warnings[@]}" -gt 0 ]]; then
  echo "[PASS-WARN] skill output smoke passed with warnings:"
  for item in "${warnings[@]}"; do
    echo "  - ${item}"
  done
  if [[ "${STRICT}" -eq 1 ]]; then
    exit 2
  fi
else
  echo "[PASS] skill output smoke passed"
fi
